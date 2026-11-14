# Contract proposal — CORE → both of us

Status: **proposal**, not applied. We apply it to `contract/` together. Every new field is **optional**,
so the UI keeps working on the current examples. Core's strict shape check (`core/app/ontology.py`,
`PROPOSED_OPTIONAL_FIELDS`) accepts exactly the new top-level fields listed here, nothing else.

## 1. Rule ids (decision model)
- `ReasoningStep.rule_id?: string` — the rule that fired, one of the ids in `docs/DECISION-MODEL.md`
  (e.g. `R-SERIAL-RANGE`, `R-ENGINE-DERIVED`, `R-CREDIT`). Present on every step Core returns.

## 2. Evaluation records and replay
An *evaluation* is a computed result. It is **not** a `Decision` (a Decision stays a person with a role).
- Q1 `GET /aircraft/{id}/status` gains `evaluation_id?`, `rules_version?` (hash), `inputs_hash?`.
- Q3 `GET /aircraft/{id}/ads/{ad_id}/supersession` gains `rules_version?`, `inputs_hash?`.
- New `GET /evaluations/{id}` →
  `{ id: "EV-0001", kind: "computed", aircraft_id, as_of_date, status, verdicts: {ad_id: applies|not_applicable|unknown},
     rule_ids_fired: [..], rules_version: { id, rules_py, ads: [{ad_id, sha256}] }, inputs_hash, inputs, decided_at,
     replay_of: null | "EV-…" }`
  · 404 `EVALUATION_NOT_FOUND`.
- New `POST /evaluations/{id}/replay` (same recorded inputs, current rules) →
  `{ evaluation_id, same: bool, before: {status, verdicts}, after: {status, verdicts},
     changed: { rules_version: bool, rules_py: bool, ads_added: [], ads_removed: [], ads_changed: [] },
     replay_evaluation_id, inputs_hash, replayed_at }`
  · 404 `EVALUATION_NOT_FOUND` · 409 `INPUTS_HASH_MISMATCH` (the recorded inputs were edited).
- Demo: DEMO-01 status → EV green · ingest FAA:2012-02-02 · replay → `same: false`, green → red,
  `ads_added: ["FAA:2012-02-02"]` · /demo/reset · replay → `same: true`.

## 3. Changes already live (from earlier handoffs, still to write into contract/)
- `AffectedAircraft.via` adds `"installed_engine"`.
- `Question.deadline`, `days_left`, `urgency` are null for real aircraft (no ARC date in this system).
- `due.overdue` is null for real aircraft.
- `/fleet` lists the 3 real EI-* aircraft too (always `no_records`).
- `/questions?aircraft_id=<unknown>` → 404 `AIRCRAFT_NOT_FOUND`.
- Q3: `still_valid` is `yes | no_record | unknown | not_applicable`; every `chain` item has `ad_id, status,
  superseded_by, link, effective_date` (nullable); `compliance` may be null; `compliance.recorded_by` is null.
- Q2 before the 2012-02-02 ingest: `GET /ads/FAA%3A2012-02-02/affected-aircraft` and Q3 on FAA:2008-03-02 → 404.
- Ingest `source`: see §4.

## 4. Agent extraction in ingest
- `POST /ads/{ad_id}/ingest` → `source` is `"cache"` (demo mode: the cached LLM extraction), `"llm"` (live call)
  or `"golden"` (the extraction was missing, invalid, or disagreed with golden).
- New optional `extraction?: { used: bool, source: "cache"|"llm"|null, model, prompt_version, agreement: 0..1,
  reason: string|null, misses: [string] }`. The extraction decides only if every quote is found in the text
  **and** every compared field agrees with golden; otherwise golden decides and every miss is listed.
- `rejected_fields[].check` gains `"disagrees with golden"` (value = `{missing, extra}`).
- An extraction for an AD with no golden file never decides a status (today: ingest of such an AD → 404).
