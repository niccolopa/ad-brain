# Handoff — CORE
<!-- Overwrite this file at every handoff. Max 25 lines. Facts only. -->

Updated: 2026-11-14 · Branch: main · Last commit: see `git log` (v2c: real /fleet and /questions)

## Done since last handoff
- v2a: FAA:2012-02-02 not loaded at startup/reset (`store.NOT_LOADED_AT_RESET`). POST /ads/{id}/ingest reads data/golden (no LLM), re-checks every quote against the .txt; tested: DEMO-01 green → red, ingest twice changes nothing, changed text → rejected_fields and AD not loaded. /demo/reset returns real counts.
- v2b: engine inference (aircraft hasInstalled engine + AD appliesTo engine ⇒ derived appliesTo aircraft), golden `series` rows, `not_evaluated` clauses named in applies_because and reasoning notes, `credited_compliance`, superseded ADs not counted for status. Drafts FAA 2006-12-07 / 2006-20-09 / 2012-19-01 in data/golden/drafts/ (NOT loaded; tests use them as labelled unchecked fixtures). Check table: data/raw/pdf/golden-check-2.md (git-ignored, local only).
- v2c: GET /fleet (8 aircraft, one-line reason) and GET /questions (sorted urgency → days_left; unknown aircraft_id → 404) from the store.

## Next 3 steps
1. Niccolò checks the drafts against golden-check-2.md, fills checked_by, moves them to data/golden/ → DEMO-03 amber (ECi question), Q3 data ready.
2. Real Q3 /aircraft/{id}/ads/{ad_id}/supersession (chain + credited compliance), then /ads/{id} detail.
3. Actions + action log (RecordCompliance, ProposeAction 202, role check 403) — demo moment 4.

## Contract
change proposed: AffectedAircraft.via adds "installed_engine"; ingest `source` = "golden" in demo mode; Question deadline/days_left/urgency nullable (real aircraft); /fleet lists the 3 real EI-* aircraft too; /questions unknown aircraft_id → 404.

## Tests
146 → 185 passed (`python -m pytest core`) · smoke test: pass

## How to run what I built
```
.venv\Scripts\python -m uvicorn app.api:app --app-dir core --port 8000
.venv\Scripts\python -m pytest core
.venv\Scripts\python scripts\smoke.py
```
