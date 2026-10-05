#!/usr/bin/env python3
"""Generate golden PDF plan fixtures for S02 acceptance tests.

Each PDF draws known rectangles at a known scale (1 in = 20 ft) plus the
plan-annotation text the takeoff script reads. Requires PyMuPDF (fitz).

Fixture reference areas (sq ft):
  sheet C3.1 : 100 ft x 50 ft  = 5,000   (rect at 5 in x 2.5 in page units)
  sheet C3.2 : 200 ft x 60 ft  = 12,000  (rect at 10 in x 3 in page units)
"""

from __future__ import annotations

import sys
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "pdf"

# (sheet_label, width_ft, height_ft, width_in, height_in)
CASES = [
    ("C3.1", 100.0, 50.0, 5.0, 2.5),
    ("C3.2", 200.0, 60.0, 10.0, 3.0),
]


def main() -> int:
    try:
        import pymupdf as fitz  # PyMuPDF
    except ImportError:
        print("PyMuPDF not installed; run: pip install pymupdf", file=sys.stderr)
        return 1

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for sheet, w_ft, h_ft, w_in, h_in in CASES:
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)  # letter
        # rectangle at scale: 1 in on page = 20 ft
        x0, y0 = 72.0, 72.0
        x1, y1 = x0 + w_in * 72.0, y0 + h_in * 72.0
        page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1.5)
        # dimension + label annotations
        page.insert_text(
            fitz.Point(72, 52), f"SHEET {sheet}  PAVING PLAN  SCALE: 1\" = 20'", fontsize=10
        )
        page.insert_text(
            fitz.Point(x0, y0 - 18), f"{w_ft:.0f} FT x {h_ft:.0f} FT  AREA = {w_ft * h_ft:,.0f} SF", fontsize=9
        )
        page.insert_text(fitz.Point(x0, y1 + 16), '3 in HMA', fontsize=9)
        path = FIXTURE_DIR / f"plan_{sheet.replace('.', '')}.pdf"
        doc.save(path)
        doc.close()
        print(f"wrote {path} (area {w_ft * h_ft:,.0f} sq ft)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
