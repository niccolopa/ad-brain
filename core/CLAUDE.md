# CORE — data → ontology → rules → actions → API

Owner: Niccolò. The root CLAUDE.md applies; this file adds Core specifics.

## Stack (change these lines if the team picks another)
Python 3.11+ · FastAPI · Pydantic v2 · SQLite (stdlib sqlite3) · pytest · ruff · pyright (Pylance).
Dependencies pinned in core/requirements.txt. Type hints on every function signature;
pyright runs in basic mode with no errors allowed on the demo path.

## Layout (created on Saturday, not before)
- app/ontology/  object and link types as Pydantic models. They are the source of truth that
                 FastAPI turns into the OpenAPI schema the UI generates its types from.
- app/ingest/    AD text (data/raw/ads/*.txt; source of each file in data/raw/ads/SOURCES.csv:
                 EASA first, Federal Register text only where EASA had none) → extraction (LLM)
                 → validation → store. This is a pipeline (automated transform), not an action.
- app/rules/     deterministic: applicability, supersession chains, deadlines, airworthiness status.
- app/actions/   typed actions with role checks and audit events.
- app/llm.py     the ONLY module that talks to an LLM. It uses the `openai` SDK pointed at the
                 KVA Vercel AI Gateway (LLM_BASE_URL, AI_GATEWAY_API_KEY from .env), with model
                 strings from config (LLM_MODEL_EXTRACTION, LLM_MODEL_PHRASING). Explicit
                 timeouts, one retry, fallback, results cached in data/cache/.
                 LLM_PROVIDER selects the endpoint: `kva` (default) or `openrouter` (paid by us,
                 only if the KVA budget runs out). Only the selected provider's key is required.
- app/api.py     one endpoint per business question (see contract/README.md), plus reset.
- tests/

## LLM budget (shared by the whole team, set by KVA)
- HTTP 402 means the budget is used up. Treat it as a handled failure: switch to the cache or
  the template, log it once, never crash, never retry in a loop.
- Log the token usage of every call (the `usage` field of the response) to
  data/cache/llm_usage.jsonl, without prompts or keys. Core turns it into "cost per AD" for the
  business case.
- Never print, log or commit AI_GATEWAY_API_KEY or OPENROUTER_API_KEY.

## Domain rules
- AD identity = authority + AD number, e.g. "FAA:2012-02-02", "EASA:2012-0043" (the formats differ;
  never compare bare numbers). Supersession: FAA "Affected ADs" paragraph, EASA "Supersedure" field;
  EASA revisions (e.g. 2024-0152R1) are a `revises` link. Which authority applies depends on the
  model's State of Design.
- In scope: applicability by model and serial-number range; compliance deadlines.
  Out of scope: part numbers, AMOCs, terminating actions, repetitive inspections.
  If an AD needs out-of-scope logic, store a QUESTION object instead of guessing.
- Serial numbers are strings with prefixes (e.g. "172S9491"). Range checks must parse the
  prefix and the number; test both sides of every range boundary.
- A field extracted by the LLM is a HYPOTHESIS until it is validated against its source span.
- Extraction quality is measured against data/golden/. Report accuracy; never hide misses.
- Registry data: never store or log owner name or address.
- Real (non-synthetic) aircraft: we have no maintenance records, so their status is never
  "non-compliant" or "grounded". It is "AD applies — no compliance records in this system".
  Red, amber and green statuses are for the synthetic fleet only. Test this rule.

## API conventions
- Every answer includes `citations` (AD number + exact source sentence + URL) and
  `reasoning_path` (ordered steps: object → link → object). The UI draws the path.
- Errors return JSON with a stable `error_code` and a human message. Never a stack trace.
- Keep models named and documented: the UI's types are generated from them.
