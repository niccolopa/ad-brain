# Handoff — CORE
<!-- Overwrite this file at every handoff. Max 25 lines. Facts only. -->

Updated: 2026-11-14 · Branch: main · Last commit: see `git log` (part 3: agent extraction)

## Done since last handoff
- Decision model: 25 rule ids in core/app/rules.py; every reasoning step has `rule_id`; table in docs/DECISION-MODEL.md; test: table = code, every rule fires.
- Evaluations: every Q1 answer records EV-… (rules_version = rules.py + golden hashes, inputs_hash, inputs, decided_at) in an append-only log data/runtime/evaluations.jsonl (git-ignored). GET /evaluations/{id}, POST /evaluations/{id}/replay. Tested: DEMO-01 replay green → red after the 2012-02-02 ingest (ads_added), same again after reset.
- Agent extraction (core/app/llm.py, extract.py, scripts/extract.py): live run on the 8 golden ADs, cached in data/cache/extractions/ (REPORT.json): 5/8 usable, quotes 121/121, overall 65% (81/100 items + 25 extra). Ingest uses the extraction only if all quotes found and it agrees with golden (2012-02-02: yes).
- scripts/use-kva.ps1 deleted (KVA does not allow its key for Claude Code).

## Next 3 steps
1. Matteo + Niccolò apply docs/handoff/contract-proposal.md to contract/ (all new fields optional).
2. Real GET /ads/{id} detail (metadata + full text).
3. Actions + action log (RecordCompliance, ProposeAction 202, role check 403) — demo moment 4.

## Contract
change proposed: docs/handoff/contract-proposal.md (§1 rule_id, §2 evaluations, §3 earlier changes, §4 extraction).

## Tests
185 → 270 passed (`python -m pytest core`) · smoke test: pass · .env needs LLM_PHRASING_MAX_TOKENS, LLM_EXTRACTION_TOTAL_TIMEOUT_SECONDS, LLM_EXTRACTION_MAX_TOKENS

## How to run what I built
Server `.venv\Scripts\python -m uvicorn app.api:app --app-dir core --port 8000` · tests `.venv\Scripts\python -m pytest core` · smoke `.venv\Scripts\python scripts\smoke.py` · extraction report `.venv\Scripts\python scripts\extract.py` (add `--live --all` to call the LLM)
