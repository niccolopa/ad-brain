# AD Brain — shared rules for Claude Code (both teammates)

KVA hackathon "AI brain for industry", Saturday 14 Nov 2026, Turin.
Team: Niccolò (role CORE) and Matteo (role SURFACE). Your user's role is in CLAUDE.local.md.

Project: an airworthiness-directive (AD) brain. It ingests real EASA and FAA ADs, builds an ontology
(directives, aircraft, compliance, decisions, unknowns) and answers five business questions with
citations. Scope, layers, object/link/action types and data flows: docs/ARCHITECTURE.md — read it
before designing or changing any component.
Interface between the two halves: contract/README.md and contract/examples/.

## Data policy — European first
AD Brain's first customers are European, so European official sources come first:
- EASA ADs for European designs (e.g. Tecnam).
- FAA ADs only for US-designed products (e.g. Cessna, Lycoming): they apply in the EU through
  EASA. Download them from the EASA Safety Publications Tool when it has them; US sites are
  the fallback.
- Real aircraft come from EU registers (the Irish IAA snapshot). The FAA registry is a fallback only.
- US-only material (e.g. FAA fines) appears only as evidence, labelled "US".

## Event rules that bind you
- The application is built on 14 Nov. Before that date, do NOT write application code.
  Allowed before: config, docs, the contract (a spec), the dataset, public project templates.
  Anything prepared in advance is logged in docs/PREPARED.md.
- Commit plan: until Saturday 10:30 only .gitignore and data/ are committed. Every other file
  in this folder is untracked on purpose and is committed at 10:30 in one commit. Don't
  suggest committing them earlier, and never run `git add -A` before then.
- The repository becomes public. Secrets live only in .env (git-ignored). Never print them.

## Environment
- Niccolò's laptop runs Windows (PowerShell, VS Code). Every command and script must work on
  Windows and macOS: no make, no .sh scripts, no Unix-only commands. Scripts are Python.
- Python 3.11+. The virtual environment is `.venv/` at the repo root.
- Quote paths in commands. Keep the repo folder name free of spaces.

## Who owns what
- CORE: core/, data/, scripts/
- SURFACE: ui/ (the pitch and the business case live outside this repo)
- Shared: contract/, docs/, README.md, CLAUDE.md. Change them only when the user says both agreed.
- Never edit files outside your user's folders. If a task needs a change on the other side,
  stop and write the request as text for a GitHub issue instead.

## How to help (the user's own standards)
1. Before implementing logic (not boilerplate): state in at most 5 bullets what it must do and
   the edge cases it can meet, then ask "OK?". Boilerplate and layout: just do it.
2. After delivering: list what a code review would flag — security, error handling,
   uncovered cases, technical debt. Never hand over code "that works" without this.
3. Flag defects you notice in existing code even if not asked.
4. Label every follow-up as FIX NOW (defect in what was delivered) or LATER (new scope).
5. When asked for a rating: two numbers (as hackathon work / as production code) and what
   separates them.
6. Never say "done" without running the tests and `python scripts/smoke.py` and reporting the result,
   including the test count before and after.

## Architecture rules (do not break)
- The LLM is never the source of truth. It extracts and phrases. Applicability, supersession
  and deadlines are deterministic code with tests.
- The LLM reads through typed query functions and writes only by proposing actions.
  Binding actions (DECISION class) require a human with the right role.
  Every action writes an audit event: who, when, what, why.
- Every stored assertion carries: epistemic_class (REGULATION | DECISION | OBSERVATION |
  HYPOTHESIS | QUESTION), status (active | superseded | contested) and a citation to the exact
  source text span.
- Contradictions become contradiction edges. Never overwrite a conflicting fact silently.
- Model real-world entities, not tables. Links are real relationships, not foreign-key artifacts.

## Engineering rules
- Validate every external input before use, LLM output included (schema validation).
- Every external call (LLM, HTTP) has explicit connect and total timeouts and a handled failure.
- Ingestion is idempotent: the AD number is the key; ingesting twice changes nothing.
- Unexpected cases are logged, never silently ignored.
- No personal data (owner names, addresses) in data files or logs.
- Logic is separate from I/O so it can be tested without network.
- Tests cover negative cases: empty, null, malformed, unexpected type.
  Every permission or validation check has a test where it must reject.
- Fixtures are real documents from data/raw/, not invented examples.
- No magic numbers or strings: use constants or config. File paths are relative to the
  source file, never to the launch directory.
- Commit messages say what changed. No generated files in git (exception: data/cache/,
  kept on purpose so the demo runs offline).
- Copy identifiers from their source; never retype names from memory.

## Demo robustness
- The UI must never need a live LLM call to render. LLM failures fall back to templates.
- No new dependencies after 14:00 on Saturday unless the user explicitly says so.
- Wow features stay behind flags that can be switched off.
- Don't refactor working code. Don't add features outside the scope section of docs/ARCHITECTURE.md.

## Handoff (between sessions and between the two of us)
Each role keeps one file: docs/handoff/core.md (CORE) or docs/handoff/surface.md (SURFACE).
Edit only your role's file. It is the one exception to the shared-docs rule.
- **At the start of every session:** read both handoff files and `git log --oneline -10`.
  Summarise in 3 bullets what changed since last time and what's next. If something conflicts
  with your task, say so before continuing.
- **Write your role's file** (overwrite it; git keeps the history) when the user says
  "handoff", before every sync point (Saturday 11:15, 12:10, 15:00, 15:45, 16:00), before
  ending a session, and when the context is getting long.
- Use the template already in the file. Max 25 lines. Facts only: say what was tested, not
  what "should work".
- No secrets or personal data in a handoff.
- Commit it on its own: `docs(handoff): <role> — <one line>`.

## Commands (filled in on Saturday)
- Core: run `…` · test `…`
- UI: run `…` · test `…`
- End to end: `python scripts/smoke.py`
