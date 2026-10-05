"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

FIXTURES = REPO_ROOT / "fixtures"


@pytest.fixture(scope="session")
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def pdf_fixtures_ready(fixtures: Path):
    """Generate PDF plan fixtures when PyMuPDF is available; else skip."""
    try:
        import fitz  # noqa: F401
    except ImportError:
        pytest.skip("PyMuPDF not installed — PDF vector-geometry tests skipped (pip install pymupdf)")
    from tools import make_pdf_fixtures

    rc = make_pdf_fixtures.main()
    assert rc == 0
    return fixtures / "pdf"


@pytest.fixture(scope="session")
def photo_fixtures_ready(fixtures: Path):
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        pytest.skip("Pillow not installed — photo tests skipped (pip install Pillow)")
    from tools import make_photo_fixtures

    rc = make_photo_fixtures.main()
    assert rc == 0
    return fixtures / "photos"


@pytest.fixture()
def empty_project(tmp_path: Path) -> Path:
    (tmp_path / "input" / "plans").mkdir(parents=True)
    (tmp_path / "input" / "specs").mkdir(parents=True)
    (tmp_path / "input" / "quotes").mkdir(parents=True)
    (tmp_path / "input" / "tickets").mkdir(parents=True)
    (tmp_path / "input" / "supplier_quotes").mkdir(parents=True)
    (tmp_path / "input" / "photos").mkdir(parents=True)
    (tmp_path / "input" / "weather").mkdir(parents=True)
    (tmp_path / "working").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "audit").mkdir()
    return tmp_path


def run_script(module, argv: list[str]) -> int:
    """Run a script module end-to-end through its CLI runner with argv."""
    script_id = module.__name__.split(".")[-1]
    parser = module.build_parser(script_id, "test", module.add_extra_args)
    return module.run_lifecycle(parser, script_id, module.pipeline, argv=argv)
