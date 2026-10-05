"""Unit handling and conversion for the asphalt workflow.

Pure conversions only — deterministic quantity/cost formulas live in the
AsphaltCosts client (the shared calculation engine), never here.
"""

from __future__ import annotations

import re

from .errors import AmbiguousUnitError

# --- linear / area conversions to a canonical US basis --------------------

LENGTH_TO_FT = {
    "in": 1 / 12.0,
    "inch": 1 / 12.0,
    "inches": 1 / 12.0,
    "ft": 1.0,
    "foot": 1.0,
    "feet": 1.0,
    "'": 1.0,
    "yd": 3.0,
    "yard": 3.0,
    "yards": 3.0,
    "mi": 5280.0,
    "mile": 5280.0,
    "mm": 1 / 304.8,
    "cm": 1 / 30.48,
    "m": 1 / 0.3048,
    "meter": 1 / 0.3048,
    "meters": 1 / 0.3048,
}

AREA_TO_SQFT = {
    "sq_ft": 1.0,
    "sqft": 1.0,
    "sf": 1.0,
    "ft2": 1.0,
    "ft\u00b2": 1.0,
    "square_ft": 1.0,
    "square_feet": 1.0,
    "sq_m": 10.7639104167,
    "sq_meter": 10.7639104167,
    "sq_meters": 10.7639104167,
    "m2": 10.7639104167,
    "m\u00b2": 10.7639104167,
    "sq_yd": 9.0,
    "sq_yard": 9.0,
    "sq_yards": 9.0,
    "yd2": 9.0,
    "acre": 43560.0,
    "acres": 43560.0,
}

THICKNESS_TO_IN = {
    "in": 1.0,
    "inch": 1.0,
    "inches": 1.0,
    '"': 1.0,
    "cm": 1 / 2.54,
    "centimeter": 1 / 2.54,
    "centimeters": 1 / 2.54,
    "mm": 1 / 25.4,
    "ft": 12.0,
}

DENSITY_TO_PCF = {
    "lb/ft3": 1.0,
    "lb/ft\u00b3": 1.0,
    "pcf": 1.0,
    "lb/ft^3": 1.0,
    "kg/m3": 1 / 16.018463374,
    "kg/m\u00b3": 1 / 16.018463374,
    "t/m3": 1000 / 16.018463374,
    "ton/m3": 1000 / 16.018463374,
}

MASS_TO_US_TON = {
    "us_ton": 1.0,
    "ton": 1.0,
    "tons": 1.0,
    "short_ton": 1.0,
    "short_tons": 1.0,
    "lb": 1 / 2000.0,
    "lbs": 1 / 2000.0,
    "pound": 1 / 2000.0,
    "pounds": 1 / 2000.0,
    "metric_ton": 1.102311310924388,
    "metric_tons": 1.102311310924388,
    "t": 1.102311310924388,
    "tonne": 1.102311310924388,
    "tonnes": 1.102311310924388,
    "kg": 1 / 907.18474,
    "kilograms": 1 / 907.18474,
}


def normalize_length(value: float, unit: str) -> float:
    unit = unit.strip().lower()
    if unit not in LENGTH_TO_FT:
        raise AmbiguousUnitError(f"Unsupported length unit: {unit!r}")
    return value * LENGTH_TO_FT[unit]


def normalize_area(value: float, unit: str) -> float:
    unit = unit.strip().lower()
    if unit not in AREA_TO_SQFT:
        raise AmbiguousUnitError(f"Unsupported area unit: {unit!r}")
    return value * AREA_TO_SQFT[unit]


def normalize_thickness(value: float, unit: str) -> float:
    unit = unit.strip().lower()
    if unit not in THICKNESS_TO_IN:
        raise AmbiguousUnitError(f"Unsupported thickness unit: {unit!r}")
    return value * THICKNESS_TO_IN[unit]


def normalize_density(value: float, unit: str) -> float:
    unit = unit.strip().lower()
    if unit not in DENSITY_TO_PCF:
        raise AmbiguousUnitError(f"Unsupported density unit: {unit!r}")
    return value * DENSITY_TO_PCF[unit]


def normalize_mass(value: float, unit: str) -> float:
    unit = unit.strip().lower()
    if unit not in MASS_TO_US_TON:
        raise AmbiguousUnitError(f"Unsupported mass unit: {unit!r}")
    return value * MASS_TO_US_TON[unit]


# --- parse helpers for free text -----------------------------------------

_NUM = r"[\d,]+(?:\.\d+)?"

_AREA_PATTERNS = [
    (re.compile(rf"({_NUM})\s*(?:sq\s*ft|square\s*feet|SF|ft2|ft\u00b2)\b", re.I), "sq_ft"),
    (re.compile(rf"({_NUM})\s*(?:sq\s*m|square\s*meters|m2|m\u00b2)\b", re.I), "sq_m"),
    (re.compile(rf"({_NUM})\s*(?:sq\s*yd|square\s*yards|yd2)\b", re.I), "sq_yd"),
    (re.compile(rf"({_NUM})\s*(?:acres?)\b", re.I), "acre"),
]

_THICKNESS_PATTERNS = [
    (re.compile(rf"({_NUM})\s*(?:in|inch|inches|\")\b", re.I), "in"),
    (re.compile(rf"({_NUM})\s*(?:cm|centimeters?)\b", re.I), "cm"),
]

_DENSITY_PATTERNS = [
    (re.compile(rf"({_NUM})\s*(?:lb/ft3|lb/ft\u00b3|pcf)\b", re.I), "lb/ft3"),
    (re.compile(rf"({_NUM})\s*(?:kg/m3|kg/m\u00b3)\b", re.I), "kg/m3"),
]

_MASS_PATTERNS = [
    (re.compile(rf"({_NUM})\s*(?:us\s*tons?|short\s*tons?)\b", re.I), "us_ton"),
    (re.compile(rf"({_NUM})\s*(?:metric\s*tons?|tonnes?)\b", re.I), "metric_ton"),
    (re.compile(rf"({_NUM})\s*(?:lbs?|pounds?)\b", re.I), "lb"),
    (re.compile(rf"({_NUM})\s*(?:kgs?)\b", re.I), "kg"),
    (re.compile(rf"({_NUM})\s*tons?\b", re.I), "us_ton"),
    (re.compile(rf"({_NUM})\s*t\b", re.I), "metric_ton"),
]


def _parse_num(text: str) -> float:
    return float(text.replace(",", ""))


def parse_area(text: str):
    """Return (value, unit) for the first area mention, or None."""
    for pattern, unit in _AREA_PATTERNS:
        m = pattern.search(text)
        if m:
            return _parse_num(m.group(1)), unit
    return None


def parse_thickness(text: str):
    for pattern, unit in _THICKNESS_PATTERNS:
        m = pattern.search(text)
        if m:
            return _parse_num(m.group(1)), unit
    return None


def parse_density(text: str):
    for pattern, unit in _DENSITY_PATTERNS:
        m = pattern.search(text)
        if m:
            return _parse_num(m.group(1)), unit
    return None


def parse_mass(text: str):
    for pattern, unit in _MASS_PATTERNS:
        m = pattern.search(text)
        if m:
            return _parse_num(m.group(1)), unit
    return None


def format_sqft(value: float) -> str:
    return f"{value:,.1f}"
