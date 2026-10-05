"""AI boundary adapter.

AI may read/classify documents, extract candidate values, map synonyms,
compare text/scope, explain anomalies and generate human-readable reports.

AI may NOT silently:
  - invent a project dimension;
  - change a source value without preserving the original;
  - replace a deterministic calculator result;
  - turn a planning assumption into an engineering fact;
  - mark an extracted value as verified without evidence.

This adapter ships with a deterministic heuristic backend so the tools run
offline and honestly. An OpenAI-compatible backend can be enabled through
configuration (env key ADI_AI_API_KEY). Whatever the backend, candidates are
returned with confidence and state=EXTRACTED and are never VERIFIED here.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .config import get as cfg_get
from .errors import APIError
from .schemas import EXTRACTED

# ---------------------------------------------------------------- heuristics

# Synonym maps used by the heuristic backend (kept tiny, deterministic).
MATERIAL_SYNONYMS = {
    "hma": "HMA",
    "hot mix": "HMA",
    "hot mix asphalt": "HMA",
    "ac": "AC",
    "asphalt concrete": "AC",
    "asphalt": "ASPHALT",
    "blacktop": "ASPHALT",
    "mill": "MILL",
    "milling": "MILL",
    "base": "BASE",
    "aggregate base": "BASE",
    "tack": "TACK",
    "tack coat": "TACK",
    "striping": "STRIPING",
    "sealcoat": "SEALCOAT",
    "seal coat": "SEALCOAT",
    "curb": "CURB",
    "sidewalk": "SIDEWALK",
}

REQUIREMENT_TONE = [
    ("shall", "REQUIRED", 0.97),
    ("must", "REQUIRED", 0.97),
    ("required", "REQUIRED", 0.96),
    ("will be", "REQUIRED", 0.9),
    ("should", "RECOMMENDED", 0.85),
    ("recommended", "RECOMMENDED", 0.9),
    ("may", "OPTIONAL", 0.7),
    ("may be", "OPTIONAL", 0.72),
    ("typical", "EXAMPLE", 0.6),
    ("for example", "EXAMPLE", 0.6),
    ("for reference", "REFERENCE ONLY", 0.6),
    ("reference only", "REFERENCE ONLY", 0.6),
]


class HeuristicExtractor:
    """Deterministic rule-based candidate extraction shared by several scripts."""

    def map_material(self, text: str) -> Optional[dict]:
        lowered = text.lower()
        for key, normalized in MATERIAL_SYNONYMS.items():
            if key in lowered:
                return {
                    "field": "surface_material",
                    "value": normalized,
                    "raw": text.strip(),
                    "confidence": 0.8,
                    "method": "heuristic_synonym",
                }
        return None

    def classify_requirement(self, sentence: str) -> dict:
        lowered = sentence.lower()
        for keyword, classification, confidence in REQUIREMENT_TONE:
            if keyword in lowered:
                return {"classification": classification, "confidence": confidence}
        return {"classification": "UNCLASSIFIED", "confidence": 0.4}

    def extract_candidates(self, text: str, context: str | None = None) -> list[dict]:
        """Run all heuristic rules over a text block.

        Returns candidate dicts; each candidate stays EXTRACTED.
        """
        from . import units

        candidates: list[dict] = []

        area = units.parse_area(text)
        if area:
            candidates.append(self._candidate("area", area[0], area[1], 0.85, "regex_area"))

        thickness = units.parse_thickness(text)
        if thickness:
            candidates.append(
                self._candidate("thickness", thickness[0], thickness[1], 0.85, "regex_thickness")
            )

        density = units.parse_density(text)
        if density:
            candidates.append(
                self._candidate("density", density[0], density[1], 0.85, "regex_density")
            )

        mass = units.parse_mass(text)
        if mass:
            candidates.append(self._candidate("mass", mass[0], mass[1], 0.85, "regex_mass"))

        material = self.map_material(text)
        if material:
            candidates.append(material)

        return candidates

    def _candidate(self, field, value, unit, confidence, method) -> dict:
        return {
            "field": field,
            "value": value,
            "unit": unit,
            "confidence": confidence,
            "method": method,
            "state": EXTRACTED,
            "verified": False,
        }


class AIAdapter:
    """Pluggable AI backend facade.

    provider (config "ai.provider"):
      - "none"       -> extraction disabled
      - "heuristic"  -> deterministic rules (default, offline)
      - "openai_compatible" -> HTTP API, enabled only when an API key exists
    """

    def __init__(self, config: dict):
        self.config = config
        self.provider = cfg_get(config, "ai.provider", "heuristic")
        self.model = cfg_get(config, "ai.model")
        self.api_key = os.environ.get(cfg_get(config, "ai.api_key_env", "ADI_AI_API_KEY")) or ""
        self.vision_enabled = bool(cfg_get(config, "ai.vision_enabled", False))
        self.base_url = cfg_get(config, "ai.base_url")
        self.heuristic = HeuristicExtractor()

    @property
    def available(self) -> bool:
        return self.provider == "heuristic" or (
            self.provider == "openai_compatible" and bool(self.api_key)
        )

    def extract_candidates(self, text: str, context: str | None = None) -> list[dict]:
        if self.provider == "heuristic":
            return self.heuristic.extract_candidates(text, context)
        if self.provider == "openai_compatible" and self.api_key:
            return self._llm_extract(text, context)
        return []

    def analyze_image(self, image_path: str) -> Optional[dict]:
        """Vision hook. Returns None when vision is not configured (callers
        then route the item to the human review queue — never to a verdict)."""
        if not self.vision_enabled or not self.api_key:
            return None
        return self._llm_vision(image_path)

    # -- openai-compatible plumbing -----------------------------------------

    def _llm_extract(self, text: str, context: str | None) -> list[dict]:
        prompt = {
            "task": "extract_candidates",
            "instructions": (
                "Return JSON list of candidates {field,value,unit,confidence,raw}."
                "Never invent values not present in the text. Values are candidates only."
            ),
            "context": context or "",
            "text": text[:6000],
        }
        result = self._post(prompt)
        try:
            return self._normalize_llm(json.loads(result))
        except Exception:
            return []

    def _llm_vision(self, image_path: str) -> dict:
        raise APIError("Vision backend requires an image-capable endpoint configuration.")

    def _post(self, payload: dict) -> str:
        import requests

        url = self.base_url or "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model or "gpt-4o-mini",
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                }
            ],
            "temperature": 0.0,
        }
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise APIError(f"AI adapter request failed: {exc}") from exc

    def _normalize_llm(self, data: Any) -> list[dict]:
        if isinstance(data, dict):
            data = data.get("candidates", [])
        out = []
        for item in data or []:
            if isinstance(item, dict) and "value" in item:
                out.append(
                    {
                        "field": item.get("field"),
                        "value": item["value"],
                        "unit": item.get("unit"),
                        "confidence": min(0.99, float(item.get("confidence", 0.5))),
                        "method": "ai_extraction",
                        "state": EXTRACTED,
                        "verified": False,
                        "raw": item.get("raw"),
                    }
                )
        return out
