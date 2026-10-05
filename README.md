# Asphalt PDF Plan Takeoff

**Extract and validate paving quantities from plan PDFs** — area, thickness, tons, order tons and truckloads for asphalt estimating, with evidence-backed confidence and a deterministic calculation engine.

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CLI](https://img.shields.io/badge/CLI-command--line-blue)](#usage)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6)](https://www.microsoft.com/windows)

**English** | [简体中文](./README.zh-CN.md)

---

## What it solves

Manual quantity takeoff from civil and paving plan PDFs is slow and error-prone — estimators trace regions by hand, copy scale notes and re-type numbers into spreadsheets. This tool automates **PDF plan takeoff for asphalt and paving projects**: it classifies sheets, parses text, scale notes and vector drawings, and produces measurable paving regions with confidence and evidence for every value.

Ambiguous scales, conflicting dimensions and uncertain labels are never guessed — they land in a **review queue** for the estimator. Validated quantities are then sent to the [AsphaltCosts.com](https://asphaltcosts.com/) engine for tons, order tons and truckloads.

## Features

- **Plan PDF takeoff** — civil / paving / site-plan PDFs → paving area regions
- **Sheet classification & vector parsing** — text, scale notes and drawing vectors
- **Evidence-backed values** — every quantity carries source page, region, method, confidence and state
- **No silent guesses** — ambiguous scales / conflicting dimensions → review queue
- **Engine integration** — area → compacted volume → tons → order tons → truckloads via the AsphaltCosts engine (or its labeled local mirror)
- **Audit-ready output** — JSON / CSV / Markdown with a calculation record

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
python -m scripts.s02_pdf_plan_takeoff --project ./project --input ./fixtures/pdf
```

Run with `--help` for all options. Every script in this family shares the same CLI convention: `--project <path> --input <path> --output <path> --format json|csv|md|xlsx|pdf --config <path> --verbose --dry-run`.

## Outputs

- `takeoff.json` / `takeoff.csv` — validated area records (area_id, sheet, source, quantity, unit, thickness, method, confidence, state)
- `review_queue.json` — ambiguous scale / low-confidence / conflicting-dimension items
- `summary.md` — plan summary and engine calculation record

## How it works

- **Standard lifecycle** — `DISCOVER → INGEST → EXTRACT → NORMALIZE → VALIDATE → CALCULATE → OUTPUT → AUDIT`
- **Evidence state machine** — every quantity moves `EXTRACTED → NORMALIZED → VALIDATED → VERIFIED`; stopping earlier is valid
- **Deterministic math** — tons, compacted volume, coverage, truckloads and material cost come from the AsphaltCosts web engine, never re-implemented here

## Quality gates

- deterministic schema validation on every record;
- golden sample fixtures with exact expected values (`tests/`);
- review queue: low-confidence values, ambiguous scales and conflicts land in `review_queue.json` / summary — never a silent fix;
- audit log: every run writes `run_id`, timings, input hashes, engine version and outputs to `<project>/audit/`.

## Testing

```bash
python -m pytest -q
```

## Security & privacy

Local files stay local by default. API keys live in environment variables (`ASPHALTCOSTS_API_KEY`, `ADI_AI_API_KEY`) — never in source code. Derived files are written to `working/` or `output/`; source files are never modified.

## License

MIT — see [LICENSE](LICENSE). Part of the [Asphalt Desktop Intelligence](https://github.com/anleeylee/asphalt-desktop-intelligence) toolkit.

## The calculation engine

[**AsphaltCosts.com**](https://asphaltcosts.com/) is the deterministic calculation layer: area → compacted volume → net tons → order tons (allowance applied once) → truckloads → material cost, with sourced planning defaults (145 lb/ft³ FHWA density, editable allowance and truck capacity). This tool feeds measured and validated inputs into that engine (or its labeled local mirror, `asphaltcosts-web-engine/1.0-mirror`) and never re-implements the formulas.
