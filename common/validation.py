"""Deterministic schema validation for the evidence envelope and records.

No script is considered production-ready unless it has deterministic schema
validation. This module provides lightweight, dependency-free checks plus the
shared raise-if helpers used across scripts.
"""

from __future__ import annotations

import math
from typing import Any

from .errors import (
    AmbiguousUnitError,
    CalculationValidationFailure,
    DuplicateRecordError,
    InvalidGeometryError,
    LowConfidenceExtractionError,
    MissingScaleError,
    MissingSourceError,
    UnsupportedFileError,
)
from .schemas import STATES, NORMALIZED, VALIDATED, VERIFIED

SUPPORTED_EXTENSIONS = {
    "pdf": "pdf",
    "dxf": "dxf",
    "dwg": "dwg",
    "csv": "csv",
    "txt": "text",
    "md": "text",
    "json": "json",
    "jpg": "image",
    "jpeg": "image",
    "png": "image",
    "heic": "image",
    "heif": "image",
    "xlsx": "spreadsheet",
}


def require_file_exists(path: str) -> str:
    import os

    if not path or not os.path.exists(path):
        raise MissingSourceError(f"Source not found: {path}")
    return path


def require_supported_file(path: str, allowed: set[str] | None = None) -> str:
    import os
    from pathlib import Path

    require_file_exists(path)
    ext = Path(path).suffix.lower().lstrip(".")
    if allowed and ext not in allowed:
        raise UnsupportedFileError(
            f"Unsupported file type: .{ext}", detail=f"Allowed: {sorted(allowed)}"
        )
    return path


def require_scale(scale_ft_per_unit: float | None) -> float:
    if scale_ft_per_unit is None or scale_ft_per_unit <= 0:
        raise MissingScaleError(
            "Measurement scale is missing or ambiguous; stop measuring and request/flag manual calibration."
        )
    return scale_ft_per_unit


def require_unit(unit: str | None) -> str:
    if not unit:
        raise AmbiguousUnitError("Unit is missing; units must be explicit.")
    return unit


def require_confidence(confidence: float, threshold: float = 0.90) -> None:
    if confidence < threshold:
        raise LowConfidenceExtractionError(
            f"Extraction confidence {confidence:.2f} below threshold {threshold:.2f}."
        )


def require_no_duplicate(seen: set, key: str, label: str) -> None:
    if key in seen:
        raise DuplicateRecordError(f"Duplicate {label}: {key}")
    seen.add(key)


def require_valid_geometry(ok: bool, message: str) -> None:
    if not ok:
        raise InvalidGeometryError(message)


def close_to(a: float, b: float, rel_tol: float = 1e-6, abs_tol: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def within_percent(actual: float, reference: float, max_percent: float) -> bool:
    if reference == 0:
        return actual == 0
    return abs(actual - reference) / abs(reference) * 100.0 <= max_percent


def validate_envelope(obj: Any) -> list[str]:
    """Validate a value-envelope dict; return a list of problems (empty = ok)."""
    problems: list[str] = []
    if not isinstance(obj, dict):
        return ["envelope must be a dict"]
    if "value" not in obj:
        problems.append("missing 'value'")
    if "method" not in obj:
        problems.append("missing 'method'")
    state = obj.get("state")
    if state not in STATES:
        problems.append(f"invalid state {state!r}")
    confidence = obj.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        problems.append(f"invalid confidence {confidence!r}")
    if obj.get("verified") and state != VERIFIED:
        problems.append("verified=True requires state=VERIFIED")
    if state == VERIFIED and not obj.get("verified"):
        problems.append("state=VERIFIED requires verified=True")
    return problems


def validate_takeoff_record(rec: dict) -> list[str]:
    problems: list[str] = []
    for key in ("area_id", "sheet", "surface", "quantity", "unit", "method", "confidence", "state"):
        if key not in rec:
            problems.append(f"missing '{key}'")
    return problems


def require_validated(problems: list[str], label: str) -> None:
    if problems:
        raise CalculationValidationFailure(
            f"{label} failed validation: {'; '.join(problems)}"
        )


def state_can_transition(from_state: str, to_state: str) -> bool:
    from .schemas import STATE_TRANSITIONS

    return to_state in STATE_TRANSITIONS.get(from_state, ())


def promote(state: str, verified: bool = False) -> str:
    """Promote one step on the evidence ladder (helper for pipelines)."""
    if verified:
        return VERIFIED
    return {NORMALIZED: VALIDATED}.get(state, state)
