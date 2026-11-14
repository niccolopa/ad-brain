# Contract — the only interface between CORE and SURFACE

Rule: agree out loud → change this file → then change code. Never the other way round.
Claude Code is denied write access to this folder on purpose: you edit it yourselves.
Examples: `contract/examples/*.json`. The UI copies them to `ui/src/mocks/` (mock mode).
Core's FastAPI responses must validate against these shapes; the OpenAPI schema is generated
from Core's Pydantic models, and the UI generates its types from it.

## The three questions, answered
1. **"We don't know"** never becomes a guess. The answer carries `status: "amber"` (synthetic
   fleet) and the unknown as a QUESTION object in `open_questions`, with what it blocks and the
   deadline that drives it. A HYPOTHESIS is shown only in `hypotheses`, never used for a status.
2. **Not found** → HTTP 404 with `Error` (`AIRCRAFT_NOT_FOUND`, `AD_NOT_FOUND`,
   `QUESTION_NOT_FOUND`). Never a 200 with empty data.
3. **What the UI needs, nothing more:** a status + one-line reason per aircraft (fleet board),
   the reasoning path as graph edges, citations it can highlight, the decision ledger rows, the
   questions sorted by urgency. Large AD text is fetched only on the AD view.

## Conventions
- Ids are strings. Aircraft id = registration (`DEMO-01`, `EI-…`). AD id = authority + number
  (`FAA:2012-02-02`, `EASA:2024-0152R1`); URL-encode ids in paths (`FAA%3A2012-02-02`).
- Dates ISO 8601 (`2026-11-14`); timestamps UTC (`2026-11-14T10:31:00Z`).
- Every answer carries `citations` and `reasoning_path`. A citation's `quote` is copied verbatim
  from `data/raw/ads/<file>.txt`; the UI highlights it by **string match** in the AD text, not by
  character offsets (offsets break across line endings and re-extraction).
- A `quote` matches a span of the file after collapsing every whitespace run (spaces, tabs,
  line breaks) to one space, in both the quote and the file. A quote must not cross a hyphen
  split across lines (`065-` / `00176-5201`): end it before the split.
- `occurrence` picks which match to highlight when the quote appears more than once in the file
  (1 = first match).
- Examples show a subset of the applicable ADs; the rules engine computes the full list.
- `synthetic: true` on everything invented (the DEMO-xx fleet, its logbooks, its people).
- Real aircraft: `status` is `"no_records"`, never red; reason "AD applies — no compliance
  records in this system".

## Shared shapes
```
Citation       { "ad_id": "FAA:2012-19-01", "quote": "<verbatim sentence>", "file": "data/raw/ads/FAA-2012-19-01.txt", "occurrence": 1, "source_url": "https://…" }
ReasoningStep  { "from": "<object id>", "link": "supersedes | revises | appliesTo | hasInstalled | satisfies | madeBy | justifiedBy | contradicts", "to": "<object id>", "derived": false, "note": "<why, one line>" }
EpistemicClass "REGULATION" | "DECISION" | "OBSERVATION" | "HYPOTHESIS" | "QUESTION"
Status         "active" | "superseded" | "contested"
AircraftStatus "green" | "amber" | "red" | "no_records"
Urgency        "low" | "medium" | "high" | "overdue"
Error          { "error_code": "AIRCRAFT_NOT_FOUND", "message": "<for humans>", "details": {} }
```
`derived: true` = an inferred link (aircraft → engine → AD). The graph draws it dashed, next to
the two links it came from.

## Object types
| Type | Fields | Example (real AD, synthetic aircraft) |
|---|---|---|
| AirworthinessDirective | `ad_id`, `authority` (FAA/EASA), `title`, `effective_date`, `status`, `supersedes[]`, `superseded_by`, `revises`, `source_url`, `file` | `FAA:2012-19-01`, effective `2012-10-24`, supersedes `FAA:2006-20-09` |
| Aircraft | `id`, `registration`, `model`, `serial`, `engine_model`, `synthetic`, `arc_review_due` | `DEMO-01`, Cessna 172S, `172S10600` |
| Engine | `id`, `model`, `serial` (may be null) | `DEMO-02/engine`, Lycoming IO-360-L2A |
| ComplianceRecord (OBSERVATION) | `id`, `ad_id`, `subject_id`, `date`, `method`, `evidence`, `recorded_by` | crankshaft replaced per AD 2006-20-09 (synthetic logbook) |
| Decision (DECISION) | `id`, `what`, `aircraft_id`, `ad_id`, `rationale`, `evidence[]`, `made_by`, `made_at`, `action_log_id` | "EASA 2024-0152R1 does not apply to DEMO-05: MOD2008/233 embodied" |
| Person | `id`, `name`, `role` (mechanic / certifying_engineer / agent), `synthetic` | `P-CE-1` "Certifying Engineer 1 (synthetic)" |
| Question (QUESTION) | `id`, `text`, `aircraft_id`, `ad_id`, `blocks`, `deadline`, `deadline_driver`, `days_left`, `urgency`, `status` | "Is MOD2008/233 embodied on DEMO-04?" |
| ActionLog | `id`, `action`, `actor`, `at`, `params`, `objects_edited[]`, `result` | — |

Deadline driver for the synthetic fleet: the aircraft's yearly ARC review (`arc_review_due`).
In the EU the ARC review must verify every applicable AD, so an open QUESTION blocks it.

## Endpoints
| Q | Method + path | Example | Errors | Demo moment |
|---|---|---|---|---|
| — | `GET /fleet` | `fleet.json` | — | fleet board |
| Q1 | `GET /aircraft/{id}/status` | `q1-aircraft-status.json` | 404 AIRCRAFT_NOT_FOUND | 1 |
| Q2 | `GET /ads/{ad_id}/affected-aircraft` | `q2-affected-aircraft.json` | 404 AD_NOT_FOUND | 1, 2 |
| Q2 | `POST /ads/{ad_id}/ingest` (pipeline run, not an action; demo mode reads the cache) | `q2-ingest.json` | 404 AD_NOT_FOUND · 503 LLM_UNAVAILABLE (falls back to cache) | 2 |
| Q3 | `GET /aircraft/{id}/ads/{ad_id}/supersession` | `q3-supersession.json` | 404 both | 2, 3 |
| Q4 | `GET /decisions?aircraft_id=&ad_id=` (both optional) | `q4-decisions.json` | — (empty list = no decisions) | ledger |
| Q5 | `GET /questions?aircraft_id=` (sorted by urgency, then days_left) | `q5-questions.json` | — | 5 |
| — | `GET /ads/{ad_id}` (metadata + full text) | `ad-detail.json` | 404 AD_NOT_FOUND | AD view |
| — | `POST /compare` `{question, aircraft_id, ad_id}` → plain RAG vs brain (behind a flag) | `compare.json` | 503 LLM_UNAVAILABLE | 3 |
| — | `POST /demo/reset` | `demo-reset.json` | — | all |
| — | `GET /health` | `{ "ok": true, "demo_mode": true }` | — | — |

## Actions
`POST /actions/{ActionType}` with body `{ "actor": {"person_id", "role"}, "params": {…}, "read_version": n }`.
- 200 → done: `{ "action_log": ActionLog, "result": {…} }`
- 202 → the caller is an agent: stored as a PENDING proposal (`action-proposed.json`)
- 403 SUBMISSION_CRITERIA_FAILED → which criteria failed (`action-rejected.json`)
- 409 VERSION_CONFLICT → the object changed since `read_version`: re-read and retry
- 422 VALIDATION_ERROR → missing or malformed params
Proposals: `GET /proposals?status=PENDING` · `POST /proposals/{id}/approve` (`action-approved.json`)
· `POST /proposals/{id}/reject` `{ "actor", "reason" }`.

## Demo control
`POST /demo/reset` restores the known demo state (cached extractions, synthetic logbooks,
no proposals) and returns `demo-reset.json`. The UI's "Reset demo" button calls it.

## All quotes checked against the files on 13 Nov.
Every `quote` matches its `file` at least `occurrence` times (whitespace collapsed).
