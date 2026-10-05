"""Configuration loading.

API keys live in environment variables (or Windows Credential Manager in a
deployment), never in source code. Endpoints, authentication and rate limits
are loaded from configuration rather than hardcoded into each script.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS: dict = {
    "asphaltcosts": {
        "base_url": "https://asphaltcosts.com/",
        "api_endpoint": None,          # set when a documented API endpoint exists
        "api_key_env": "ASPHALTCOSTS_API_KEY",
        "timeout_seconds": 20,
        "fallback_to_mirror": True,    # mirror the documented web-engine math when no endpoint
        "max_requests_per_minute": 60,
    },
    "ai": {
        "provider": "heuristic",       # none | heuristic | openai_compatible
        "base_url": None,
        "model": None,
        "api_key_env": "ADI_AI_API_KEY",
        "vision_enabled": False,
    },
    "weather": {
        "source": "manual",            # manual | open_meteo
        "open_meteo_url": "https://api.open-meteo.com/v1/forecast",
    },
    "review": {
        "confidence_threshold": 0.90,  # below this a value enters the human-review queue
    },
    "validation": {
        "area_tolerance_percent": 0.5,      # dimension-vs-polygon agreement
        "ticket_gross_tare_tolerance_tons": 0.5,
        "duplicate_distance": 0.001,        # geometry duplicate tolerance
    },
    "retention": {
        "temp_extract_days": 7,
    },
}

ENV_PREFIX = "ADI_"


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | Path | None = None) -> dict:
    """Load configuration: defaults < file (if any) < environment overrides."""
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        with open(p, "r", encoding="utf-8") as fh:
            cfg = _deep_merge(cfg, json.load(fh))

    # Environment overrides for API keys only (secrets never in files).
    key_map = {
        "asphaltcosts.api_key_env": "ASPHALTCOSTS_API_KEY",
        "ai.api_key_env": "ADI_AI_API_KEY",
    }
    for dotted, env_name in key_map.items():
        env_val = os.environ.get(env_name)
        if env_val:
            section, field = dotted.split(".")
            cfg[section][field] = env_val
    return cfg


def get(cfg: dict, dotted: str, default=None):
    """Read a dotted key from a loaded config dict."""
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def resolve_api_key(cfg: dict, env_var: str) -> str | None:
    value = os.environ.get(env_var)
    if value:
        return value
    # Windows Credential Manager lookup (optional, silent on failure).
    try:
        import win32cred  # type: ignore  # pywin32, optional

        cred = win32cred.CredRead(f"ADI/{env_var}", 1, 0)
        return cred.get("CredentialBlob", b"").decode("utf-8") or None
    except Exception:
        return None
