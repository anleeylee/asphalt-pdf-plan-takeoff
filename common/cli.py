"""Shared CLI conventions and lifecycle runner.

Every script must support:

    --project <path>
    --input <path>
    --output <path>
    --format json|csv|md|xlsx|pdf
    --config <path>
    --verbose
    --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Optional

from .audit_log import AuditLogger
from .config import load_config
from .errors import ADIError

SCRIPT_IDS = {
    "s01": "s01_project_workspace",
    "s02": "s02_pdf_plan_takeoff",
    "s03": "s03_cad_takeoff",
    "s04": "s04_specification_checker",
    "s05": "s05_quote_comparator",
    "s06": "s06_delivery_ticket_reconcile",
    "s07": "s07_supplier_quote_normalizer",
    "s08": "s08_weather_compaction_planner",
    "s09": "s09_field_photo_analyzer",
    "s10": "s10_estimate_report_builder",
}


def build_parser(script_id: str, description: str, extra_args: Callable = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=script_id, description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--project", default=".", help="project workspace path (project.json folder)")
    parser.add_argument("--input", help="input file or folder")
    parser.add_argument("--output", help="output file path or folder (default: <project>/output)")
    parser.add_argument("--format", choices=("json", "csv", "md", "xlsx", "pdf"), default="json")
    parser.add_argument("--config", help="path to a JSON config file")
    parser.add_argument("--verbose", action="store_true", help="print progress to stderr")
    parser.add_argument("--dry-run", action="store_true", help="execute pipeline without writing outputs")
    if extra_args:
        extra_args(parser)
    return parser


def parse_args(parser: argparse.ArgumentParser, argv: list[str] | None = None) -> argparse.Namespace:
    return parser.parse_args(argv)


def log(args: argparse.Namespace, message: str) -> None:
    if getattr(args, "verbose", False):
        print(message, file=sys.stderr)


def resolve_output_path(args: argparse.Namespace, default_name: str) -> Path:
    """--output may be a file path or a folder; default <project>/output/<name>."""
    fmt = args.format or "json"
    if args.output:
        out = Path(args.output)
        if out.suffix:
            return out
        out.mkdir(parents=True, exist_ok=True)
        return out / default_name
    project = Path(args.project)
    folder = project / "output"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / default_name


def run_lifecycle(
    parser: argparse.ArgumentParser,
    script_id: str,
    pipeline: Callable[[argparse.Namespace, dict, AuditLogger], dict],
    argv: list[str] | None = None,
) -> int:
    """Wrap a script pipeline with config + audit + error handling.

    pipeline(args, config, audit) -> outputs dict {name: (path, fmt, data)}
    """
    args = parse_args(parser, argv)
    audit = AuditLogger(args.project, script_id, dry_run=args.dry_run)
    try:
        config = load_config(args.config)
        audit.set_model_provider(config.get("ai", {}).get("provider", "heuristic"))
        log(args, f"[{script_id}] run {audit.run_id} started")
        outputs = pipeline(args, config, audit)
        if not args.dry_run:
            for name, (path, fmt, data) in outputs.items():
                from .outputs import write_output

                final = write_output(path, fmt, data)
                audit.output(final, fmt)
                log(args, f"[{script_id}] wrote {final}")
        record = audit.finish()
        log(args, f"[{script_id}] run {audit.run_id} finished, {len(record['warnings'])} warning(s), {len(record['errors'])} error(s)")
        return 0
    except ADIError as exc:
        audit.error(exc.code, exc.message, detail=exc.detail)
        audit.finish()
        print(f"[{script_id}] error {exc.code} {exc.label}: {exc.message}", file=sys.stderr)
        if exc.detail:
            print(f"  detail: {exc.detail}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        audit.error("E000", str(exc))
        audit.finish()
        print(f"[{script_id}] unexpected error: {exc}", file=sys.stderr)
        return 2
