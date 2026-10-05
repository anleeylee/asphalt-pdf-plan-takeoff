"""Audit logging.

Every run writes, per the implementation playbook:

    run_id, script_id, start_time, end_time, input_hashes, model/provider,
    engine_version, warnings, errors, outputs

Logs land in <project>/audit/ as one JSON-lines file per run.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .hashing import sha256_text, stable_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLogger:
    def __init__(self, project_path: str | Path, script_id: str, *, dry_run: bool = False):
        self.project_path = Path(project_path)
        self.script_id = script_id
        self.dry_run = dry_run
        self.run_id = stable_id("run", _now(), script_id)
        self.record: dict = {
            "run_id": self.run_id,
            "script_id": script_id,
            "start_time": _now(),
            "end_time": None,
            "input_hashes": [],
            "model_provider": None,
            "engine_version": None,
            "warnings": [],
            "errors": [],
            "outputs": [],
            "dry_run": dry_run,
        }

    def set_engine(self, engine_version: str) -> None:
        self.record["engine_version"] = engine_version

    def set_model_provider(self, provider: str, model: str | None = None) -> None:
        self.record["model_provider"] = provider if model is None else f"{provider}/{model}"

    def add_input(self, path: str, digest: str) -> None:
        self.record["input_hashes"].append({"path": path, "sha256": digest})

    def warn(self, message: str, **meta) -> None:
        self.record["warnings"].append({"message": message, **meta})

    def error(self, code: str, message: str, **meta) -> None:
        self.record["errors"].append({"code": code, "message": message, **meta})

    def output(self, path: str, fmt: str) -> None:
        self.record["outputs"].append({"path": str(path), "format": fmt})

    def finish(self) -> dict:
        self.record["end_time"] = _now()
        if not self.dry_run:
            audit_dir = self.project_path / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            with open(audit_dir / f"run_{self.run_id}.json", "w", encoding="utf-8") as fh:
                json.dump(self.record, fh, indent=2, ensure_ascii=False)
        return self.record
