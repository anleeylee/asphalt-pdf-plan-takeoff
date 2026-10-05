# Asphalt Desktop Intelligence — Modular Script/Skill Architecture

**Version:** v1.0  
**Date:** 2026-10-05  
**Target:** Windows 11 Pro + Python 3.12+  
**Primary market:** US asphalt / paving workflow  
**Core web engine:** AsphaltCosts.com  
**Principle:** One user + one task + one input family + one output contract per script.

---

## 1. Product boundary

`asphaltcosts.com` remains the web calculation layer. Desktop scripts are not duplicates of the website calculators; they solve tasks that require local files, batch processing, OCR, CAD parsing, project evidence, AI document understanding, or local automation.

Existing web calculator capabilities and the API/MCP/agent integration should be reused rather than reimplemented. The desktop system must call the shared calculation engine whenever a deterministic asphalt quantity or cost calculation is already supported by the web product.

## 2. Modular script map

| ID | Script / Skill | Primary user | Main input | Main output | AI |
|---|---|---|---|---|---|
| S01 | Project Workspace | Any project user | files/project metadata | normalized project workspace | Optional |
| S02 | PDF Plan Takeoff | Estimator / PM | civil/paving PDFs | paving takeoff table | Required/optional |
| S03 | CAD Takeoff | Estimator / engineer | DWG/DXF | geometry quantities | Optional |
| S04 | Specification Checker | Estimator / PM | specification PDFs | structured requirements + conflicts | Required |
| S05 | Quote Comparator | Homeowner / PM / estimator | contractor quotes | comparable quote table + flags | Required |
| S06 | Delivery Ticket Reconciler | Foreman / PM | ticket PDFs/images/CSV | delivered-vs-estimated reconciliation | Required |
| S07 | Supplier Quote Normalizer | Purchaser / estimator | supplier quotes | normalized material price dataset | Required |
| S08 | Weather & Compaction Planner | Superintendent / foreman | weather + project parameters | paving window analysis | Optional + model |
| S09 | Field Photo Analyzer | Foreman / homeowner / PM | site photos | visual condition observations | Required |
| S10 | Estimate Report Builder | Estimator / PM | structured project data | audit-ready estimate/report | Optional |

A separate S11 price-research collector can be added later; it is deliberately not a dependency of the core estimator workflow.

## 3. Shared thin foundation

All scripts share only these utilities:

```text
common/
├── config.py
├── units.py
├── schemas.py
├── provenance.py
├── validation.py
├── hashing.py
├── audit_log.py
├── asphaltcosts_client.py
├── file_manifest.py
└── ai_adapter.py
```

The shared layer must remain small. It cannot contain user-specific workflow logic.

## 4. Standard lifecycle

Every script follows:

```text
DISCOVER
  ↓
INGEST
  ↓
EXTRACT
  ↓
NORMALIZE
  ↓
VALIDATE
  ↓
CALCULATE / CLASSIFY
  ↓
OUTPUT
  ↓
AUDIT
```

## 5. AI boundary

AI may:

- read and classify documents;
- extract candidate values;
- map synonyms to normalized fields;
- compare text and scope;
- explain anomalies;
- generate a human-readable report.

AI may not silently:

- invent a project dimension;
- change a source value without preserving the original;
- replace a deterministic calculator result;
- turn a planning assumption into an engineering fact;
- mark an extracted value as verified without evidence.

## 6. Evidence state machine

Every important value uses:

```text
EXTRACTED
→ NORMALIZED
→ VALIDATED
→ VERIFIED
```

It is valid to remain in an earlier state.

Every value should carry:

```json
{
  "value": 84200,
  "unit": "sq_ft",
  "source_file": "C3.1.pdf",
  "source_page": 12,
  "source_region": null,
  "method": "ai_extraction",
  "confidence": 0.92,
  "state": "EXTRACTED",
  "verified": false
}
```

## 7. Common project folder

```text
Project/
├── project.json
├── input/
│   ├── plans/
│   ├── specs/
│   ├── quotes/
│   ├── tickets/
│   ├── supplier_quotes/
│   ├── photos/
│   └── weather/
├── working/
├── output/
└── audit/
```

## 8. Security / privacy

- Local files stay local by default.
- AI upload requires explicit per-run configuration.
- API keys live in environment variables or Windows Credential Manager, never in source code.
- File hashes are stored so that reports can identify the exact source version used.
- Temporary extracted files are deleted according to a configurable retention policy.

## 9. CLI convention

Every script must support:

```text
--project <path>
--input <path>
--output <path>
--format json|csv|md|xlsx|pdf
--config <path>
--verbose
--dry-run
```

Example:

```powershell
python scripts/s02_pdf_plan_takeoff.py `
  --project .\Project01 `
  --input .\Project01\input\plans\civil-set.pdf `
  --output .\Project01\output\takeoff.json
```

## 10. Quality gates

No script is considered production-ready unless it has:

- deterministic schema validation;
- sample fixtures;
- golden test cases;
- source/provenance output;
- retry/error handling;
- duplicate detection;
- dry-run mode;
- human-review queue for low-confidence extraction;
- machine-readable output;
- human-readable report;
- audit log.
