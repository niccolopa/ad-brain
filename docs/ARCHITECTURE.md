# Architecture — AD brain

**In one line:** an operational-ontology pattern at hackathon scale. Data → ontology → logic and actions →
apps. The LLM sits only at the two edges: reading text in, phrasing answers out. It is never in
the middle, where the decisions are made.

## 0. Scope — what we build
The five questions (the A-to-Z path, one API endpoint each):
1. Is aircraft X airworthy today? If not, why?
2. Which aircraft does a new AD affect?
3. What superseded the AD we complied with, and is our compliance still valid?
4. Who decided AD Y doesn't apply, and on what evidence?
5. What unknown blocks a sign-off, and how soon does it matter?

Demo moments, in build order. Cut from the bottom if late:
1. Pick a real aircraft: its applicable ADs are computed and the reasoning path is drawn on the graph.
2. A new AD is ingested live: the old one turns red and the affected aircraft change status.
3. Plain RAG vs AD Brain, side by side, on a superseded AD.
4. An agent tries to sign off compliance and is rejected (certifying role required).
5. Unknowns panel with rising urgency.

Build order: a walking skeleton first (everything end to end with fakes), then replace the fakes
one at a time. Feature freeze at 16:00. Out of scope: section 10.

## 1. Layers, top to bottom

| Layer | What it does | Pattern | Owner |
|---|---|---|---|
| **Sources** | AD texts, pre-converted to text: FAA ADs (valid in the EU for US-designed aircraft) from the EASA Safety Publications Tool, Federal Register text only where EASA has none + EASA ADs for European designs; provenance in data/raw/ads/SOURCES.csv · aircraft: Irish IAA register snapshot (real, EU) + an Italian flight-school fleet (synthetic, labelled) · logbooks (synthetic, labelled) | Data connectivity | Core |
| **Ingestion pipeline** | The LLM reads one AD and returns a structured candidate (applicability, supersedes, deadline, plus the exact quote for each field). Schema validation runs, then each field is checked against its quote. The result is stored and cached on disk. | Transform pipeline | Core |
| **Ontology** | Objects, links, and on every assertion: epistemic class + status + citation | Ontology | Core (schema in contract/) |
| **Rules engine** | Pure, tested functions: does this AD apply to this aircraft? what replaced it? when is it due? what is the aircraft's status? | Functions | Core |
| **Actions** | Typed changes with submission criteria (role checks) and an action log | Actions with submission criteria and action log | Core |
| **Analyst agent** | An LLM with tools: query functions (read) and propose-action (write, staged for a human) | Agent tools with human confirmation | Core |
| **API** | One endpoint per business question, plus actions and reset | — | Core |
| **UI** | Five screens. Every claim is clickable through to its source | Operational app | Surface |
| **Evaluation** | Golden set → extraction accuracy | Evals | both |

## 2. Nouns — object types
- `AirworthinessDirective`: AD number (primary key), title, effective date, unsafe condition,
  compliance time, source URL.
- `Aircraft`: registration, model, serial, year. `Engine`: model (+ serial if known).
  Both implement the `AirworthinessSubject` interface.
- `ComplianceRecord` (an observation, kept separate from the aircraft's identity): AD,
  subject, date, method, evidence.
- `Decision`: what, why, evidence, who, when.
- `Person`: role = mechanic | certifying_engineer | agent.
- `Question`: what is unknown, what it blocks, the deadline that drives its urgency.
- `ActionLog`: who, when, which action, parameters, objects edited.

## 3. Links — real relationships
- AD `supersedes` AD (FAA: "Affected ADs" paragraph · EASA: "Supersedure" field)
- AD `revises` AD (EASA revisions such as 2024-0152R1 of 2024-0152)
- AD `issuedBy` Authority (FAA | EASA). The authority that applies to an aircraft comes from its
  model's State of Design: US-designed → FAA ADs, European-designed → EASA ADs.
- AD `appliesTo` model + serial range (from the "Applicability" paragraph)
- Aircraft `hasInstalled` Engine (dated)
- ComplianceRecord `satisfies` AD · Decision `madeBy` Person · Decision `justifiedBy` source quote
- Assertion `contradicts` Assertion

**Inference** (the KVA challenge's "missing link from two relations"):
Aircraft `hasInstalled` Engine + AD `appliesTo` that engine model ⇒ AD applies to the aircraft.
The graph shows the derived link as a dashed edge, together with the two links it came from.

## 4. The epistemic layer (what the jury's own paper asks for)

| Class | Who creates it | Example | How it can change |
|---|---|---|---|
| REGULATION | ingestion pipeline | AD 2012-02-02 applies to 172S 9491–10489 | only by a newer AD (supersession) |
| DECISION | a human with a role, via an action | "AD X doesn't apply to aircraft Y: modification Z embodied" | only by a newer, linked DECISION |
| OBSERVATION | a human via an action, or a logbook | "Fuel line replaced on 2026-03-02" | a conflict creates a contradiction edge, never an overwrite |
| HYPOTHESIS | the LLM or the agent | "Probably applies (serial unclear)" | freely; **never used to compute a status** |
| QUESTION | the system or a human | "Propeller serial unknown" | closed by AnswerQuestion |

Status of each assertion: active · superseded · contested.
**Hard rule:** airworthiness status is computed only from REGULATION + DECISION + OBSERVATION.
A HYPOTHESIS never changes a status. A QUESTION makes the status "unknown" and raises its urgency
as the deadline approaches.

## 5. Verbs — action types, with their submission criteria

| Action | Parameters | Submission criteria (must pass) | Writes |
|---|---|---|---|
| RecordCompliance | aircraft, AD, date, method, evidence | role ∈ {mechanic, certifying_engineer} · AD applies to the aircraft · evidence not empty | ComplianceRecord (OBSERVATION) |
| DeclareNotApplicable | aircraft, AD, rationale, evidence | role = certifying_engineer · rationale and evidence not empty | Decision (DECISION) |
| ResolveContradiction | assertion A, assertion B, chosen one, rationale | role = certifying_engineer | Decision; the losing assertion is marked superseded |
| AnswerQuestion | question, answer, evidence | role ∈ {mechanic, certifying_engineer} | closes the Question; new OBSERVATION |
| ProposeAction | any action above | caller = agent → stored as PENDING; it runs only when a human approves it | Proposal |

Every successful action writes one ActionLog object to the action log.
Ingesting an AD is a **pipeline run**, not an action: it is an automated transform, not a decision.

## 6. How a question flows — Q1 "Is aircraft X airworthy?"
1. UI → `GET /aircraft/{id}/status`
2. Rules engine: candidate ADs = by model and serial ∪ by installed engine model (inferred) →
   resolve supersession chains → for each active AD, check compliance records and decisions →
   compute the deadline.
3. Aggregate: anything overdue → red · due soon, or an open QUESTION → amber · otherwise green.
4. Response: status, reasons, `citations` (the exact AD sentences), `reasoning_path`.
5. Optional: the LLM writes a one-paragraph summary **from the response JSON only**.
   On a timeout or error → template text.
There is no LLM in steps 2–4.

## 7. How a write flows — the agent proposes a compliance record
1. The agent reads a logbook entry and proposes RecordCompliance (stored as a HYPOTHESIS).
2. The submission criteria see the caller is an agent → the proposal is PENDING.
   An agent trying to sign off directly is rejected. This is demo moment 4.
3. The certifying engineer approves in the UI → the action runs → ComplianceRecord + ActionLog.
4. The status is recomputed.

## 8. Many agents writing to the same memory (KVA challenge question 2)
- No agent writes facts directly. Every write is an action.
- Every action carries the version of the object it read. If the version has changed in the
  meantime, the action is rejected and the agent has to re-read (optimistic concurrency).
- Before writing, the action checks existing assertions on the same (subject, AD). If the new
  one conflicts → a contradiction edge + a QUESTION. Nothing is overwritten.

## 9. If Saturday morning's instructions change something
Rule: decide adaptations at the 10:25 sync. Change nothing irreversible before then.

| If KVA… | What changes | What stays |
|---|---|---|
| gives a memory or knowledge harness | our objects and epistemic classes are stored in it | the ontology, rules, actions, UI |
| gives an agent framework or SDK | the analyst agent runs inside it; its tools = our query functions + propose-action | everything else |
| LLM access (known now: Vercel AI Gateway, OpenAI-compatible) | only `core/app/llm.py` and the model strings in .env | everything else |
| imposes a language or stack | the implementation of one layer | the contract, the data, the design |
| imposes a domain or a dataset | the data and the object names | the engine: supersession, applicability, actions, epistemics. Fallback domain: software security advisories |
| changes the checkpoint material | Surface adapts the submission | — |
| changes the financial validation format | the presentation format | the one-page numbers sheet |

## 9b. LLM access and budget
- One endpoint, `https://ai-gateway.vercel.sh/v1` (OpenAI-compatible), with the key in .env.
  Switching model means changing one string.
- **Extraction:** the stronger model, run once per AD and cached → most of the budget goes here,
  and only once.
- **Phrasing:** the cheaper model, with a template fallback. Demo mode uses the cache, so the
  demo still works if the budget runs out (402).
- Token usage is logged per call → real "cost per AD" for the business case.

## 10. Out of scope (say it in the README and the pitch)
Part-number-level applicability · AMOCs · terminating actions and repetitive inspections ·
automatic download from the EASA tool (we ingest a pre-downloaded set) · real logbooks ·
authentication (roles are chosen in the UI for the demo).
