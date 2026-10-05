"""Shared data contracts (value envelope, records, project JSON).

Every important value carries the evidence envelope defined in
00-DESKTOP-ARCHITECTURE section 6.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# --- evidence state machine -------------------------------------------------
# EXTRACTED -> NORMALIZED -> VALIDATED -> VERIFIED (may stop at any earlier state)

EXTRACTED = "EXTRACTED"
NORMALIZED = "NORMALIZED"
VALIDATED = "VALIDATED"
VERIFIED = "VERIFIED"

STATES = (EXTRACTED, NORMALIZED, VALIDATED, VERIFIED)
_STATE_RANK = {EXTRACTED: 0, NORMALIZED: 1, VALIDATED: 2, VERIFIED: 3}

STATE_TRANSITIONS = {
    EXTRACTED: (NORMALIZED, VALIDATED, VERIFIED),
    NORMALIZED: (VALIDATED, VERIFIED),
    VALIDATED: (VERIFIED,),
    VERIFIED: (),
}


@dataclass
class ValueEnvelope:
    """The mandatory envelope for any important value."""

    value: Any
    unit: Optional[str] = None
    source_file: Optional[str] = None
    source_page: Optional[int] = None
    source_region: Optional[str] = None
    method: str = "manual"
    confidence: float = 0.0
    state: str = EXTRACTED
    verified: bool = False
    quoted_context: Optional[str] = None
    notes: Optional[str] = None

    def with_state(self, state: str) -> "ValueEnvelope":
        return dataclasses.replace(self, state=state)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceRef:
    """A single physical source and its exact version."""

    doc_id: str
    path: str
    sha256: str
    page: Optional[int] = None
    region: Optional[str] = None
    mtime: Optional[str] = None


@dataclass
class TakeoffRecord:
    """S02 required takeoff record contract."""

    area_id: str
    sheet: str
    surface: str
    quantity: float
    unit: str = "sq_ft"
    thickness: Optional[float] = None
    thickness_unit: Optional[str] = "in"
    source_file: Optional[str] = None
    source_page: Optional[int] = None
    method: str = "dimension_derived"
    confidence: float = 0.0
    state: str = EXTRACTED
    calc: Optional[dict] = None  # AsphaltCosts engine result
    flags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReviewItem:
    """A single human-review entry."""

    item_id: str
    reason: str
    detail: str
    confidence: float
    record: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReviewQueue:
    """Human-review queue. Users should see a compact summary, never a full
    AI reasoning trace."""

    items: list[ReviewItem] = field(default_factory=list)
    _seq: int = 0

    def add(self, reason: str, detail: str, confidence: float, record: Optional[dict] = None) -> str:
        self._seq += 1
        item_id = f"RV-{self._seq:03d}"
        self.items.append(ReviewItem(item_id, reason, detail, confidence, record))
        return item_id

    def summary_lines(self) -> list[str]:
        from collections import Counter

        counts = Counter(item.reason for item in self.items)
        return [f"{count} {reason}" for reason, count in counts.most_common()]

    def to_dict(self) -> dict:
        return {
            "count": len(self.items),
            "summary": self.summary_lines(),
            "items": [asdict(i) for i in self.items],
        }


def envelope(**kwargs) -> ValueEnvelope:
    return ValueEnvelope(**kwargs)
