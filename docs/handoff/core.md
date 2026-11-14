# Handoff — CORE
<!-- Overwrite this file at every handoff. Max 25 lines. Facts only. -->

Updated: 2026-11-14 · Branch: main · Last commit: see `git log` (v1: Q1 + Q2 real)

## Done since last handoff
- v0: FastAPI app core/app/api.py; every contract endpoint answers its example request with the example's status and top-level shape; Citation/ReasoningStep/Error validated in pytest and smoke.
- v1 real: GET /aircraft/{id}/status and GET /ads/{ad_id}/affected-aircraft from data/golden (5 ADs) + italian-fleet.csv + demo-aircraft.csv + demo-logbooks.csv. 404 AIRCRAFT_NOT_FOUND / AD_NOT_FOUND. Titles from INDEX.md Subject; source_url from SOURCES.csv; every golden quote is checked against its .txt at startup (fails loudly).
- Serial rules: OCR `l72S`→`172S`; `172S-NNNNN`→`172SNNNNN`, `172R-NNNNN`→`172NNNNN` (only these two); any other unclear serial → QUESTION "serial unclear: <raw>". Conditions match logbook `fact`/`value` against golden `conditions[].fact`/`applies_when` (new columns/keys).
- Tested: DEMO-01 red, 02 green, 03 green, 04 amber (MOD question, 14 days, high), 05 green; EI-* no_records; EI-GWY KAP 140 question.

## Next 3 steps (v2)
1. (a) Demo state starts with FAA:2012-02-02 NOT loaded, so the live ingest turns DEMO-01 green → red (demo moment 2). Today it is loaded at startup (DEMO-01 red).
2. (b) Golden additions, drafted by Claude, checked by Niccolò against the text: FAA 2006-12-07, 2006-20-09, 2012-19-01 — needed for aircraft → engine → AD inference, Q3, and DEMO-03's ECi question (DEMO-03 is green until then).
3. Real /fleet, /questions, /demo/reset counts from the store; deadline arithmetic (today: no record = overdue).

## Contract
change proposed: Question.deadline/days_left/urgency nullable (real aircraft have no ARC date); due.overdue null for real aircraft; source_url = SOURCES.csv blob URLs (examples show /ad/US-… pages); no example for GET /proposals and POST /proposals/{id}/reject (v0 returns {"proposals": []} / {"proposal_id", "status": "REJECTED"}).

## Tests
0 → 130 passed (`python -m pytest core`) · smoke test: pass

## How to run what I built
```
.venv\Scripts\python -m uvicorn app.api:app --app-dir core --port 8000
.venv\Scripts\python -m pytest core
.venv\Scripts\python scripts\smoke.py
```
