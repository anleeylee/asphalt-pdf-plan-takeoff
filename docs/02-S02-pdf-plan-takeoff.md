# S02 — PDF Paving Plan Takeoff Skill

## 1. Purpose

Convert civil/site/paving plan PDFs into a reviewable paving quantity takeoff, then send verified quantities to the AsphaltCosts calculation engine.

## 2. User / scenario

**Primary user:** paving estimator / PM.  
**Scenario:** receives a plan set and needs asphalt/base/milling areas and pavement sections without manually reading every sheet.

## 3. Input types

- vector PDFs
- scanned PDFs
- image-heavy PDF plan sets
- optional user-supplied scale

## 4. Output

```text
raw_extractions.json
paving_areas.json
pavement_sections.json
takeoff.csv
review_queue.json
```

## 5. Extraction workflow

```text
PDF
↓
page classification
↓
sheet/title-block detection
↓
text + dimension extraction
↓
scale extraction
↓
candidate paving regions
↓
label mapping
↓
geometry measurement
↓
validation
↓
human review queue
```

## 6. AI responsibilities

AI can:

- classify sheets;
- identify likely asphalt/paving labels;
- interpret notes such as `HMA`, `AC`, `PAVEMENT`, `MILL & OVERLAY`;
- associate dimensions with candidate areas;
- interpret pavement section notes.

AI cannot directly invent area values. Geometry must come from measurable PDF/CAD features or a clearly labeled approximation.

## 7. Geometry modes

P0:

- rectangles
- polygons from vector paths
- dimension-derived rectangles

P1:

- circles
- arcs
- L-shapes
- multiple regions
- split/merge operations

## 8. Required takeoff record

```json
{
  "area_id": "A-001",
  "sheet": "C3.1",
  "surface": "HMA",
  "quantity": 32450,
  "unit": "sq_ft",
  "thickness": 3,
  "thickness_unit": "in",
  "source": {"file":"civil-set.pdf","page":12},
  "method": "vector_geometry",
  "confidence": 0.99,
  "state": "VALIDATED"
}
```

## 9. Critical checks

- sheet scale exists and is internally consistent;
- dimension-derived area agrees with polygon-derived area within configured tolerance;
- no duplicated paving polygon;
- no overlap double-counting unless explicitly allowed;
- paving labels agree with specification when available;
- units are explicit.

## 10. Human review triggers

- confidence < 0.90;
- scale ambiguous;
- conflicting dimensions;
- plan/spec thickness mismatch;
- candidate area crosses sheet boundaries;
- image-only measurement without calibrated scale.

## 11. AsphaltCosts integration

Only send normalized values after validation:

```text
area
thickness
selected density
order allowance
```

The desktop tool must not reimplement the asphalt tonnage formula.

## 12. Acceptance tests

- 20 known-plan fixture areas within ±0.5% of reference geometry.
- duplicated annotation does not duplicate area.
- scale change is detected.
- unknown scale is rejected or moved to review queue.
