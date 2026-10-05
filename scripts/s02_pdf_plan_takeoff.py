#!/usr/bin/env python3
"""S02 — PDF Paving Plan Takeoff.

Convert civil/site/paving plan PDFs into a reviewable paving quantity takeoff,
then send verified quantities to the AsphaltCosts calculation engine.

Geometry must come from measurable PDF features (vector rects) or a clearly
labeled approximation (dimension-derived rectangles). AI may classify sheets,
labels and notes but can never invent area values.

Outputs: raw_extractions.json, paving_areas.json, pavement_sections.json,
takeoff.csv, takeoff.json, review_queue.json, summary.md
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.ai_adapter import AIAdapter  # noqa: E402
from common.asphaltcosts_client import AsphaltCostsClient  # noqa: E402
from common.cli import build_parser, log, parse_args, resolve_output_path, run_lifecycle  # noqa: E402
from common.config import get as cfg_get  # noqa: E402
from common.errors import ADIError, MissingScaleError, UnsupportedFileError  # noqa: E402
from common.outputs import _table_to_markdown  # noqa: E402
from common.pdftext import PDFText, drawing_rects, page_drawings  # noqa: E402
from common.schemas import ReviewQueue, TakeoffRecord  # noqa: E402
from common.units import normalize_area  # noqa: E402
from common.validation import require_scale, within_percent  # noqa: E402

SHEET_RE = re.compile(r"\b([A-Z]\d+(?:\.\d+)?)\b")
SCALE_PATTERNS = [
    re.compile(r'1"?\s*=\s*(\d+(?:\.\d+)?)\s*[\'’]', re.I),          # 1" = 20'
    re.compile(r"scale\s*[:=]\s*1\s*:\s*(\d+(?:\.\d+)?)", re.I),       # SCALE: 1:20
    re.compile(r"scale\s*[:=]\s*(\d+(?:\.\d+)?)\s*ft\s*per\s*inch", re.I),
]
DIMENSION_RE = re.compile(
    r"(\d[\d,]*)\s*(?:ft|feet|\'|’)\s*[x×]\s*(\d[\d,]*)\s*(?:ft|feet|\'|’)", re.I
)
AREA_NOTE_RE = re.compile(
    r"(?:area|ar\.|sq\s*ft|sf)\s*[:=]\s*(\d[\d,]*)\s*(?:sf|sq\s*ft|ft2)?", re.I
)
THICKNESS_NOTE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:in|inch|inches|\")\s*(?:hma|ac|asphalt|overlay|mill)", re.I
)


def add_extra_args(parser):
    parser.add_argument("--scale", help='scale override, e.g. "1in=20ft", "1:20", or "20" (ft per inch)')
    parser.add_argument("--density", type=float, default=145.0, help="compacted density lb/ft3 (default 145)")
    parser.add_argument("--allowance", type=float, default=0.05, help="order allowance (default 0.05)")
    parser.add_argument("--truck-capacity", dest="truck_capacity", type=float, default=20.0, help="truck capacity tons")
    parser.add_argument("--spec", help="optional spec_requirements.json for plan/spec conflict check")


def parse_scale(text: str, override: str | None) -> float | None:
    """Return scale in ft per drawing inch, or None when missing/ambiguous."""
    if override:
        m = re.match(r"1\s*in\s*=\s*(\d+(?:\.\d+)?)\s*ft", override, re.I)
        if m:
            return float(m.group(1))
        m = re.match(r"1\s*:\s*(\d+(?:\.\d+)?)", override)
        if m:
            return float(m.group(1))
        try:
            return float(override)
        except ValueError:
            raise MissingScaleError(f"Unrecognized --scale format: {override!r}")
    for pattern in SCALE_PATTERNS:
        m = pattern.search(text)
        if m:
            return float(m.group(1))
    return None


def parse_sheet(text: str) -> str | None:
    m = SHEET_RE.search(text)
    return m.group(1) if m else None


def collect_candidates(pdf: PDFText, scale: float | None) -> tuple[list[dict], ReviewQueue]:
    """Return (candidate regions, review queue)."""
    candidates: list[dict] = []
    review = ReviewQueue()

    for page_idx, page_text in enumerate(pdf.page_texts, start=1):
        sheet = parse_sheet(page_text) or f"P{page_idx}"
        # --- vector rects (measurable geometry, needs a scale) ---
        drawings = page_drawings(pdf.path, page_idx - 1) if pdf.engine == "pymupdf" else []
        for (x0, y0, x1, y1) in drawing_rects(drawings):
            w_pts, h_pts = abs(x1 - x0), abs(y1 - y0)
            if w_pts < 5 or h_pts < 5:
                continue  # annotations/borders, not regions
            area_sqft = None
            method = "vector_geometry"
            confidence = 0.9
            if scale:
                area_sqft = (w_pts / 72.0 * scale) * (h_pts / 72.0 * scale)
                confidence = 0.99
            else:
                review.add(
                    "image-only measurement without calibrated scale",
                    f"rect ({w_pts:.0f}x{h_pts:.0f} pts) on {sheet} p{page_idx}",
                    0.5,
                )
                method = "vector_geometry_unscaled"
            candidates.append(
                {
                    "area_id": f"A-{len(candidates) + 1:03d}",
                    "sheet": sheet,
                    "surface": "HMA",
                    "quantity": area_sqft,
                    "unit": "sq_ft",
                    "source_file": str(pdf.path),
                    "source_page": page_idx,
                    "method": method,
                    "confidence": confidence,
                    "state": "EXTRACTED",
                    "thickness": None,
                    "geometry": {"kind": "rect", "w_pts": w_pts, "h_pts": h_pts},
                }
            )
        # --- dimension-derived rectangles (labeled approximation) ---
        for m in DIMENSION_RE.finditer(page_text):
            try:
                w_ft = float(m.group(1).replace(",", ""))
                h_ft = float(m.group(2).replace(",", ""))
            except ValueError:
                continue
            candidates.append(
                {
                    "area_id": f"A-{len(candidates) + 1:03d}",
                    "sheet": sheet,
                    "surface": "HMA",
                    "quantity": w_ft * h_ft,
                    "unit": "sq_ft",
                    "source_file": str(pdf.path),
                    "source_page": page_idx,
                    "method": "dimension_derived",
                    "confidence": 0.8,
                    "state": "EXTRACTED",
                    "thickness": None,
                    "geometry": {"kind": "rect", "w_ft": w_ft, "h_ft": h_ft},
                }
            )
        # --- direct area notes ---
        for m in AREA_NOTE_RE.finditer(page_text):
            try:
                area = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            candidates.append(
                {
                    "area_id": f"A-{len(candidates) + 1:03d}",
                    "sheet": sheet,
                    "surface": "HMA",
                    "quantity": area,
                    "unit": "sq_ft",
                    "source_file": str(pdf.path),
                    "source_page": page_idx,
                    "method": "annotation_note",
                    "confidence": 0.75,
                    "state": "EXTRACTED",
                    "thickness": None,
                    "geometry": {"kind": "note"},
                }
            )
    return candidates, review


def extract_sections(pdf: PDFText, ai: AIAdapter) -> list[dict]:
    """Pavement sections from notes like '3 in HMA' / 'MILL & OVERLAY 1.5 in'."""
    sections: list[dict] = []
    for page_idx, page_text in enumerate(pdf.page_texts, start=1):
        for m in THICKNESS_NOTE_RE.finditer(page_text):
            thickness = float(m.group(1))
            # find the material label near the thickness match
            window = page_text[max(0, m.start() - 60) : m.end() + 60]
            material = ai.heuristic.map_material(window)
            sections.append(
                {
                    "section_id": f"SEC-{len(sections) + 1:03d}",
                    "sheet": parse_sheet(page_text) or f"P{page_idx}",
                    "thickness": thickness,
                    "thickness_unit": "in",
                    "surface": material["value"] if material else "HMA",
                    "source_file": str(pdf.path),
                    "source_page": page_idx,
                    "quoted_context": window.strip(),
                    "confidence": 0.8,
                    "state": "EXTRACTED",
                }
            )
    return sections


def resolve_thickness(candidates: list[dict], sections: list[dict]) -> None:
    """Associate the nearest section thickness to each candidate by page."""
    by_page: dict[int, list[dict]] = {}
    for s in sections:
        by_page.setdefault(s["source_page"], []).append(s)
    for cand in candidates:
        page_sections = by_page.get(cand["source_page"], [])
        if page_sections:
            cand["thickness"] = page_sections[0]["thickness"]
            cand["thickness_unit"] = "in"


def reconcile_duplicates(candidates: list[dict]) -> tuple[list[dict], ReviewQueue]:
    """Merge representations of the same region so a duplicated annotation
    never double-counts the same area (acceptance: duplicated annotation does
    not duplicate area). Same page + same quantity within tolerance = same
    region; the highest-confidence method wins."""
    review = ReviewQueue()
    tol = 0.005  # 0.5%
    groups: dict[tuple, list[dict]] = {}
    for cand in candidates:
        q = cand.get("quantity")
        key = (cand["source_page"], round(q or 0.0, 0))
        if q is None:
            key = (cand["source_page"], "unmeasurable")
        groups.setdefault(key, []).append(cand)

    keep: list[dict] = []
    for key, group in groups.items():
        if len(group) == 1:
            keep.append(group[0])
            continue
        # different methods / annotations describing the same area
        if key[1] != "unmeasurable":
            ref = max(g["quantity"] for g in group)
            if all(within_percent(g["quantity"], ref, tol * 100) for g in group):
                best = max(group, key=lambda g: g["confidence"])
                keep.append(best)
                review.add(
                    "overlapping representation merged",
                    f"{len(group)} candidate(s) describe the same area on page {key[0]}; kept {best['area_id']}",
                    0.9,
                    best,
                )
                continue
        keep.extend(group)
    return keep, review


def plan_spec_conflicts(takeoff: list[dict], spec_path: str | None) -> list[dict]:
    if not spec_path:
        return []
    conflicts = []
    spec_data = {}
    if spec_path and Path(spec_path).exists():
        try:
            with open(spec_path, "r", encoding="utf-8") as fh:
                spec_data = json.load(fh)
        except (OSError, ValueError):
            return []
    spec_thickness = None
    for req in spec_data.get("requirements", []):
        if req.get("field") == "thickness" and req.get("classification") in ("REQUIRED", "RECOMMENDED"):
            try:
                spec_thickness = float(req["value"])
            except (TypeError, ValueError):
                pass
    if spec_thickness is None:
        return []
    for rec in takeoff:
        if rec.get("thickness") and abs(float(rec["thickness"]) - spec_thickness) > 1e-9:
            conflicts.append(
                {
                    "conflict_id": f"CF-{len(conflicts) + 1:03d}",
                    "mode": "PLAN vs SPEC",
                    "field": "thickness",
                    "plan_value": rec["thickness"],
                    "spec_value": spec_thickness,
                    "unit": "in",
                    "status": "REVIEW REQUIRED",
                    "source": rec["area_id"],
                }
            )
    return conflicts


def pipeline(args, config, audit):
    from common.hashing import sha256_file

    input_path = Path(args.input or ".")
    files = [input_path] if input_path.is_file() else sorted(input_path.rglob("*.pdf")) if input_path.is_dir() else []
    if not files:
        raise UnsupportedFileError(f"No PDF plan files found under {input_path}")

    ai = AIAdapter(config)
    audit.set_model_provider(ai.provider, ai.model)
    client = AsphaltCostsClient(config)
    audit.set_engine(client.engine_version)

    raw_extractions: list[dict] = []
    all_candidates: list[dict] = []
    all_sections: list[dict] = []
    combined_review = ReviewQueue()

    for f in files:
        digest = sha256_file(f)
        audit.add_input(str(f), digest)
        log(args, f"[S02] processing {f.name}")
        pdf = PDFText(f)
        text = pdf.full_text()
        scale = parse_scale(text, args.scale)
        if scale is None and not args.scale:
            combined_review.add(
                "scale missing or ambiguous",
                f"{f.name}: no scale text and no --scale override; vector measurement stopped",
                0.0,
            )
        candidates, review = collect_candidates(pdf, scale)
        sections = extract_sections(pdf, ai)
        raw_extractions.append(
            {
                "source_file": str(f),
                "sha256": digest,
                "engine": pdf.engine,
                "page_count": pdf.page_count,
                "scale_ft_per_inch": scale,
                "sheet_count": len({parse_sheet(t) or f"P{i}" for i, t in enumerate(pdf.page_texts, 1)}),
                "text_chars": len(text),
                "candidates": candidates,
                "sections": sections,
            }
        )
        all_candidates.extend(candidates)
        all_sections.extend(sections)
        for item in review.items:
            combined_review.items.append(item)

    resolve_thickness(all_candidates, all_sections)
    keep, dup_review = reconcile_duplicates(all_candidates)
    for item in dup_review.items:
        combined_review.items.append(item)

    # confidence gate -> review queue
    threshold = cfg_get(config, "review.confidence_threshold", 0.90)
    takeoff_records: list[dict] = []
    for cand in keep:
        if cand["quantity"] is None:
            combined_review.add(
                "unmeasurable quantity",
                f"{cand['area_id']} on {cand['sheet']} (no calibrated scale)",
                cand["confidence"],
                cand,
            )
            continue
        state = "VALIDATED" if cand["confidence"] >= 0.99 else ("NORMALIZED" if cand["confidence"] >= threshold else "EXTRACTED")
        if cand["confidence"] < threshold:
            combined_review.add(
                "low-confidence extraction",
                f"{cand['area_id']} confidence {cand['confidence']:.2f} below {threshold:.2f}",
                cand["confidence"],
                cand,
            )
        rec = TakeoffRecord(
            area_id=cand["area_id"],
            sheet=cand["sheet"],
            surface=cand.get("surface") or "HMA",
            quantity=cand["quantity"],
            unit="sq_ft",
            thickness=cand.get("thickness"),
            thickness_unit=cand.get("thickness_unit", "in"),
            source_file=cand.get("source_file"),
            source_page=cand.get("source_page"),
            method=cand["method"],
            confidence=cand["confidence"],
            state=state,
        ).to_dict()
        # send validated quantities to the AsphaltCosts engine
        if rec["thickness"]:
            calc = client.calculate_quantity(
                rec["quantity"],
                rec["thickness"],
                density_pcf=args.density,
                order_allowance=args.allowance,
                truck_capacity_tons=args.truck_capacity,
                calc_id=f"calc-{rec['area_id']}",
            )
            rec["calc"] = calc
        rec["flags"] = []
        takeoff_records.append(rec)

    conflicts = plan_spec_conflicts(takeoff_records, args.spec)

    engine_version = client.engine_version
    audit.set_engine(engine_version)

    # ------------------------------- outputs -------------------------------
    project_out = Path(args.project) / "output"
    project_out.mkdir(parents=True, exist_ok=True)
    outputs = {}
    outputs["raw_extractions"] = (str(project_out / "raw_extractions.json"), "json", {"engine": pdf.engine, "files": raw_extractions})
    outputs["paving_areas"] = (str(project_out / "paving_areas.json"), "json", takeoff_records)
    outputs["pavement_sections"] = (str(project_out / "pavement_sections.json"), "json", all_sections)
    outputs["takeoff_json"] = (str(project_out / "takeoff.json"), "json", {"takeoff": takeoff_records, "conflicts": conflicts, "engine_version": engine_version})
    outputs["takeoff_csv"] = (str(project_out / "takeoff.csv"), "csv", [
        {k: rec[k] for k in ("area_id", "sheet", "surface", "quantity", "unit", "thickness", "thickness_unit", "method", "confidence", "state")}
        for rec in takeoff_records
    ])
    outputs["review_queue"] = (str(project_out / "review_queue.json"), "json", combined_review.to_dict())
    outputs["summary"] = (str(project_out / "takeoff_summary.md"), "md", _summary_sections(takeoff_records, conflicts, combined_review, engine_version))
    return outputs


def _summary_sections(takeoff, conflicts, review, engine_version) -> list[tuple[str, str]]:
    rows = [
        {
            "area_id": r["area_id"],
            "sheet": r["sheet"],
            "surface": r["surface"],
            "quantity": f"{r['quantity']:,.0f}",
            "unit": r["unit"],
            "thickness": r["thickness"] or "",
            "method": r["method"],
            "confidence": f"{r['confidence']:.2f}",
            "state": r["state"],
        }
        for r in takeoff
    ]
    total_sf = sum(r["quantity"] for r in takeoff)
    sections = [
        ("Takeoff Summary", f"- areas: {len(takeoff)}\n- total area: {total_sf:,.0f} sq ft\n- engine: {engine_version}"),
        ("Paving Areas", _table_to_markdown(rows)),
    ]
    if conflicts:
        sections.append(("Conflicts", _table_to_markdown([
            {"mode": c["mode"], "field": c["field"], "plan": c["plan_value"], "spec": c["spec_value"], "status": c["status"]}
            for c in conflicts
        ])))
    if review.items:
        sections.append(
            (
                "Human Review",
                "\n".join(f"- {line} — see review_queue.json" for line in review.summary_lines()),
            )
        )
    return sections


def main() -> int:
    parser = build_parser("s02_pdf_plan_takeoff", "PDF paving plan takeoff (S02)", add_extra_args)
    return run_lifecycle(parser, "s02_pdf_plan_takeoff", pipeline)


if __name__ == "__main__":
    raise SystemExit(main())
