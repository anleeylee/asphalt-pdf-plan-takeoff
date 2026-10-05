"""File manifest: inventory, classification, duplicates and revisions.

Requirements (S01):
  - recursively inventory files;
  - compute SHA-256 hash, size, timestamp, file type;
  - classify files into plans/specs/quotes/tickets/photos/other;
  - preserve original paths;
  - create stable document IDs;
  - detect revised plan sets and identify likely superseded files.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from .hashing import sha256_file, stable_id

CATEGORIES = (
    "plans",
    "specs",
    "quotes",
    "tickets",
    "supplier_quotes",
    "photos",
    "weather",
    "other",
)

EXT_TO_CATEGORY = {
    ".pdf": None,  # decided by name hints, see keyword map
    ".dxf": "plans",
    ".dwg": "plans",
    ".csv": None,
    ".xlsx": None,
    ".txt": None,
    ".jpg": "photos",
    ".jpeg": "photos",
    ".png": "photos",
    ".heic": "photos",
    ".heif": "photos",
    ".json": None,
}

KEYWORD_MAP = [
    (("plan", "sheet", "c-", "civil", "paving", "takeoff", "layout", "dwg", "dxf"), "plans"),
    (("spec", "addendum", "supplement"), "specs"),
    (("quote", "bid", "proposal", "estimate", "quotation"), "quotes"),
    (("ticket", "delivery", "load", "scale"), "tickets"),
    (("supplier", "price", "pricelist", "rate"), "supplier_quotes"),
    (("photo", "img", "image", "site", "field", "pic"), "photos"),
    (("weather", "forecast"), "weather"),
]


def classify_file(name: str, category_hint: str | None = None) -> str:
    """Classify a file name into one of the manifest categories."""
    if category_hint in CATEGORIES:
        return category_hint
    stem = Path(name).stem.lower().replace("_", " ").replace("-", " ")
    for keywords, category in KEYWORD_MAP:
        if any(kw.strip() in stem for kw in keywords):
            return category
    ext = Path(name).suffix.lower()
    if EXT_TO_CATEGORY.get(ext) in CATEGORIES:
        return EXT_TO_CATEGORY[ext]
    return "other"


class FileManifest:
    """Inventory + classification + revision detection for a set of files."""

    def __init__(self):
        self.documents: list[dict] = []
        self._by_doc_id: dict[str, dict] = {}
        self._by_hash: dict[str, list[str]] = {}

    def ingest(self, paths: list[str | Path] | str | Path, *, category_hint: str | None = None) -> int:
        """Ingest files from one or many paths (files or folders, recursive).

        Returns the number of newly-added documents. Re-ingesting an existing
        doc_id is a no-op (duplicate detection by content hash).
        """
        if isinstance(paths, (str, Path)):
            path_list = [Path(paths)]
        else:
            path_list = [Path(p) for p in paths]

        files: list[Path] = []
        for p in path_list:
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file():
                        files.append(f)
            elif p.is_file():
                files.append(p)

        added = 0
        for f in files:
            digest = sha256_file(f)
            doc_id = stable_id("doc", str(f.resolve()), digest)
            if doc_id in self._by_doc_id:
                continue  # duplicate content / already indexed
            stat = f.stat()
            category = classify_file(f.name, category_hint)
            rec = {
                "doc_id": doc_id,
                "path": str(f),
                "filename": f.name,
                "category": category,
                "sha256": digest,
                "size_bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "version": 1,
                "superseded_by": None,
                "revision_group": self._revision_group(f.name),
            }
            self.documents.append(rec)
            self._by_doc_id[doc_id] = rec
            self._by_hash.setdefault(digest, []).append(doc_id)
            added += 1
        self._detect_revisions()
        return added

    def _revision_group(self, name: str) -> str:
        p = Path(name)
        return stable_id("rev", p.stem.lower())

    def _detect_revisions(self) -> None:
        """Within a revision group, mark all but the newest mtime as superseded."""
        from collections import defaultdict

        groups: dict[str, list[dict]] = defaultdict(list)
        for rec in self.documents:
            groups[rec["revision_group"]].append(rec)
        for recs in groups.values():
            recs_sorted = sorted(recs, key=lambda r: r["mtime"])
            for older in recs_sorted[:-1]:
                older["superseded_by"] = recs_sorted[-1]["doc_id"]
                older["version"] = 1

    def find_duplicates(self) -> list[dict]:
        return [
            {"sha256": digest, "doc_ids": doc_ids}
            for digest, doc_ids in self._by_hash.items()
            if len(doc_ids) > 1
        ]

    def to_dict(self) -> dict:
        return {
            "manifest_version": "1.0",
            "document_count": len(self.documents),
            "documents": self.documents,
            "duplicates": self.find_duplicates(),
        }
