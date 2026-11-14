# Handoff — CORE
<!-- Overwrite this file at every handoff. Max 25 lines. Facts only. -->

Updated: 2026-11-14 13:45 · Branch: main · Last commit: see `git log` (UI placeholder-route list)

## Done since last handoff
- smoke.py starts its own server, exits 2 if port 8000 is busy. README for jurors (diagrams + drift test, keyless quickstart verified from a fresh clone, demo in 6 calls).
- Gateway cost: llm.py logs usage.cost as cost_usd; the 9 old extraction rows have none, so docs/EXTRACTION-REPORT.md estimates those only (≈ $0.43 list price).
- Real GET /ads/{id} for every golden AD: relations, applicability, conditions, not-evaluated, credit, citations (file + occurrence), extraction block (misses: agent vs golden, who decided).

## Next 3 steps (feature freeze 16:00)
1. Matteo + Niccolò apply docs/handoff/contract-proposal.md (§1–§5, all new fields optional) to contract/.
2. UI live mode (VITE_USE_MOCKS=false) checked against Core end to end.
3. Freeze: re-run tests, smoke and the README numbers; handoff.

## Contract: change proposed in docs/handoff/contract-proposal.md (§1 rule_id, §2 evaluations, §3 earlier, §4 extraction, §5 AD detail).

## For the other role (written as GitHub issue text)
- From ui/src/api.ts (live mode): FleetBoard /fleet, AircraftDetail Q1, ADView /ads/{id}, Unknowns /questions are real in Core. **DecisionLedger calls /decisions: still a placeholder** (always q4-decisions.json, filters ignored).
- `resetDemo` and `getSupersession` are defined but no screen calls them: no "Reset demo" control yet (ui/CLAUDE.md asks for one); ingest and /evaluations replay are not called by the UI.

## Tests: 277 → 298 passed (`python -m pytest core`) · smoke test: pass

## How to run what I built
Server `.venv\Scripts\python -m uvicorn app.api:app --app-dir core --port 8000` · tests `.venv\Scripts\python -m pytest core` · smoke `.venv\Scripts\python scripts\smoke.py` · report `.venv\Scripts\python scripts\extraction_report.py`
