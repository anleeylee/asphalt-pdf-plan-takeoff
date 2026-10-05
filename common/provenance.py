"""Provenance: source register and the evidence state machine.

Every value that matters must be traceable to a physical source version.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .errors import CalculationValidationFailure
from .hashing import sha256_file, stable_id
from .schemas import SourceRef, STATES, VERIFIED
from .validation import state_can_transition


class SourceRegister:
    """Register of physical sources (documents) seen in a run.

    Each source gets a stable doc_id derived from its path + content hash so
    that a revised file becomes a new version while the old one stays intact.
    """

    def __init__(self):
        self._sources: dict[str, SourceRef] = {}  # doc_id -> SourceRef

    def register(self, path: str, page: int | None = None, region: str | None = None) -> SourceRef:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Source not found: {path}")
        digest = sha256_file(p)
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
        doc_id = stable_id("doc", p.resolve(), digest)
        ref = SourceRef(
            doc_id=doc_id,
            path=str(p),
            sha256=digest,
            page=page,
            region=region,
            mtime=mtime,
        )
        self._sources[doc_id] = ref
        return ref

    def get(self, doc_id: str) -> SourceRef | None:
        return self._sources.get(doc_id)

    def all(self) -> list[SourceRef]:
        return list(self._sources.values())

    def to_dict(self) -> dict:
        return {
            "register_version": "1.0",
            "sources": [asdict(r) for r in self.all()],
        }


class EvidenceTracker:
    """Tracks state transitions for a set of envelope records.

    Rules:
      - EXTRACTED -> NORMALIZED -> VALIDATED -> VERIFIED (may stop earlier)
      - VERIFIED may only be reached with explicit verified=True evidence
      - a transition that skips a required hop is recorded, not silently fixed
    """

    def __init__(self):
        self._records: dict[str, dict] = {}
        self._problems: list[dict] = []

    def put(self, key: str, record: dict) -> None:
        if key in self._records:
            self._problems.append({"key": key, "issue": "duplicate record id, original kept"})
            return
        self._records[key] = record

    def transition(self, key: str, to_state: str, *, verified: bool = False) -> dict:
        if key not in self._records:
            raise CalculationValidationFailure(f"Cannot transition unknown record {key!r}")
        rec = self._records[key]
        from_state = rec.get("state", "EXTRACTED")
        if not state_can_transition(from_state, to_state) and from_state != to_state:
            self._problems.append(
                {
                    "key": key,
                    "from": from_state,
                    "to": to_state,
                    "issue": "non-standard transition",
                }
            )
            return rec
        rec["state"] = to_state
        if to_state == VERIFIED:
            rec["verified"] = bool(verified)
        self._records[key] = rec
        return rec

    def all(self) -> list[dict]:
        return list(self._records.values())

    def problems(self) -> list[dict]:
        return list(self._problems)

    def to_dict(self) -> dict:
        return {"records": self.all(), "transition_problems": self.problems()}


def provenance_chain(record: dict) -> dict:
    """Produce the public provenance view of a record."""
    return {
        "source_file": record.get("source_file"),
        "source_page": record.get("source_page"),
        "source_region": record.get("source_region"),
        "method": record.get("method"),
        "confidence": record.get("confidence"),
        "state": record.get("state", "EXTRACTED"),
        "verified": bool(record.get("verified", False)),
    }
