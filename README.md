# Asphalt PDF Plan Takeoff

Extract and validate paving quantities from plan PDFs, then run them through the AsphaltCosts engine.

> &#9888; **All tonnage, coverage and cost math is powered by [AsphaltCosts.com](https://asphaltcosts.com/)**
> — the web asphalt tonnage & cost calculator. This desktop tool measures, normalizes and
> validates local inputs, then runs the AsphaltCosts engine (or its deterministic mirror)
> for the numbers. It never re-implements the formulas.

## What it does

Reads civil/paving plan PDFs, classifies sheets, parses text, scale notes and vector drawings, and produces measurable paving regions with confidence and evidence. Ambiguous scales, conflicting dimensions and uncertain labels go to the review queue instead of being guessed. Validated quantities are sent to the AsphaltCosts engine for tons, order tons and truckloads.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
python -m scripts.s02_pdf_plan_takeoff --project ./project --input ./fixtures/pdf
```

Run with `--help` for all options. Every script in this family shares the same CLI
convention: `--project <path> --input <path> --output <path> --format json|csv|md|xlsx|pdf
--config <path> --verbose --dry-run`.

## Outputs

- `takeoff.json` / `takeoff.csv` — validated area records (area_id, sheet, source, quantity, unit, thickness, method, confidence, state)
- `review_queue.json` — ambiguous scale / low-confidence / conflicting-dimension items
- `summary.md` — plan summary and engine calculation record

## Quality gates

- deterministic schema validation on every record;
- golden sample fixtures with exact expected values (`tests/`);
- review queue: low-confidence values, ambiguous scales and conflicts land in
  `review_queue.json` / summary — never a silent fix;
- audit log: every run writes `run_id`, timings, input hashes, engine version
  and outputs to `<project>/audit/`.

## Testing

```bash
python -m pytest -q
```

## Security & privacy

Local files stay local by default. API keys live in environment variables
(`ASPHALTCOSTS_API_KEY`, `ADI_AI_API_KEY`) — never in source code. Derived files are
written to `working/` or `output/`; source files are never modified.

## License

MIT — see [LICENSE](LICENSE). Part of the Asphalt Desktop Intelligence toolkit.

## The calculation engine

[**AsphaltCosts.com**](https://asphaltcosts.com/) is the deterministic calculation layer: area → compacted volume → net tons → order tons (allowance applied once) → truckloads → material cost, with sourced planning defaults (145 lb/ft³ FHWA density, editable allowance and truck capacity). This tool feeds measured and validated inputs into that engine (or its labeled local mirror, `asphaltcosts-web-engine/1.0-mirror`) and never re-implements the formulas.

