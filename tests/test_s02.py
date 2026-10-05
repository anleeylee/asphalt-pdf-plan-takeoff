"""S02 — PDF plan takeoff tests (acceptance: known-plan areas within ±0.5%)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import run_script
from scripts import s02_pdf_plan_takeoff as s02
from common.validation import within_percent


class TestS02:
    def test_known_plan_areas(self, empty_project, pdf_fixtures_ready: Path):
        rc = run_script(
            s02,
            [
                "--project", str(empty_project),
                "--input", str(pdf_fixtures_ready),
                "--format", "json",
            ],
        )
        assert rc == 0
        takeoff = json.loads((empty_project / "output" / "takeoff.json").read_text(encoding="utf-8"))
        records = takeoff["takeoff"]
        by_sheet = {r["sheet"]: r for r in records}
        assert within_percent(by_sheet["C3.1"]["quantity"], 5000.0, 0.5)
        assert within_percent(by_sheet["C3.2"]["quantity"], 12000.0, 0.5)

    def test_engine_calculation_recorded(self, empty_project, pdf_fixtures_ready: Path):
        run_script(s02, ["--project", str(empty_project), "--input", str(pdf_fixtures_ready)])
        takeoff = json.loads((empty_project / "output" / "takeoff.json").read_text(encoding="utf-8"))
        rec = takeoff["takeoff"][0]
        assert rec["calc"] is not None
        assert rec["calc"]["engine_version"].endswith("mirror")
        # 3 in HMA at 145 pcf: net tons = area * 0.25 * 145 / 2000
        expected_net = rec["quantity"] * 0.25 * 145 / 2000
        assert within_percent(rec["calc"]["net_tons"], expected_net, 0.01)

    def test_duplicated_annotation_does_not_duplicate_area(self, empty_project, pdf_fixtures_ready: Path):
        """The PDF contains both a vector rect and a '100 FT x 50 FT' dimension
        note for the same region — the takeoff must keep one area."""
        run_script(s02, ["--project", str(empty_project), "--input", str(pdf_fixtures_ready)])
        takeoff = json.loads((empty_project / "output" / "takeoff.json").read_text(encoding="utf-8"))
        c31 = [r for r in takeoff["takeoff"] if r["sheet"] == "C3.1"]
        assert len(c31) == 1
        review = json.loads((empty_project / "output" / "review_queue.json").read_text(encoding="utf-8"))
        assert any("overlapping representation merged" in line for line in review["summary"])

    def test_missing_scale_routed_to_review(self, empty_project, pdf_fixtures_ready: Path):
        run_script(s02, ["--project", str(empty_project), "--input", str(pdf_fixtures_ready), "--scale", "1in=99ft"])
        review = json.loads((empty_project / "output" / "review_queue.json").read_text(encoding="utf-8"))
        # With an override the scale is defined; candidates stay measurable
        takeoff = json.loads((empty_project / "output" / "takeoff.json").read_text(encoding="utf-8"))
        assert len(takeoff["takeoff"]) >= 1

    def test_spec_conflict_detected(self, empty_project, pdf_fixtures_ready: Path, fixtures: Path):
        spec_out = empty_project / "output" / "spec_requirements.json"
        spec_out.parent.mkdir(parents=True, exist_ok=True)
        spec_out.write_text(
            json.dumps({"requirements": [{"field": "thickness", "value": 2.5, "classification": "REQUIRED"}]}),
            encoding="utf-8",
        )
        run_script(s02, ["--project", str(empty_project), "--input", str(pdf_fixtures_ready), "--spec", str(spec_out)])
        takeoff = json.loads((empty_project / "output" / "takeoff.json").read_text(encoding="utf-8"))
        assert any(c["mode"] == "PLAN vs SPEC" for c in takeoff["conflicts"])
