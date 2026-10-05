"""PDF text and vector-geometry extraction (shared by S02/S04/S06).

Preferred: PyMuPDF (fitz). Fallback: pdfminer.six for text-only extraction.
Vector geometry (drawing rects/paths) requires PyMuPDF; when it is absent the
caller is expected to degrade to text/dimension-derived modes and to route
image-only measurement to the human-review queue.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .errors import UnsupportedFileError


class PDFText:
    def __init__(self, path: str | Path, *, pages: Optional[list[int]] = None):
        self.path = Path(path)
        self.page_texts: list[str] = []
        self.page_count = 0
        self.engine = None
        self._load(pages)

    def _load(self, pages: Optional[list[int]]) -> None:
        try:
            import pymupdf as fitz  # PyMuPDF (fitz API)

            self.engine = "pymupdf"
            doc = fitz.open(str(self.path))
            self.page_count = doc.page_count
            wanted = pages or list(range(doc.page_count))
            for idx in wanted:
                if 0 <= idx < doc.page_count:
                    self.page_texts.append(doc.load_page(idx).get_text("text"))
            doc.close()
            return
        except ImportError:
            pass
        except Exception:
            self.page_texts = []
            self.page_count = 0
            self.engine = "pymupdf-error"
            # fall through to pdfminer

        try:
            from pdfminer.high_level import extract_text  # type: ignore

            self.engine = "pdfminer"
            text = extract_text(str(self.path))
            self.page_texts = [text]
            self.page_count = 1
            return
        except ImportError:
            raise UnsupportedFileError(
                "PDF text extraction requires PyMuPDF or pdfminer.six "
                "(pip install pymupdf pdfminer.six)."
            )

    def full_text(self) -> str:
        return "\n".join(self.page_texts)


def page_drawings(path: str | Path, page_index: int) -> list[dict]:
    """Return PyMuPDF drawings for one page, or [] if unavailable."""
    try:
        import pymupdf as fitz  # type: ignore
    except ImportError:
        return []
    doc = fitz.open(str(path))
    try:
        page = doc.load_page(page_index)
        return list(page.get_drawings())
    finally:
        doc.close()


def drawing_rects(drawings: list[dict]) -> list[tuple[float, float, float, float]]:
    """Candidate closed rectangles: (x0, y0, x1, y1) in PDF points."""
    rects: list[tuple[float, float, float, float]] = []
    for d in drawings:
        rect = d.get("rect")
        if rect:
            rects.append((rect.x0, rect.y0, rect.x1, rect.y1))
    return rects
