# Prepared before the event

Rule §7 lets teams bring an idea, a dataset they have the right to use, and open-source
libraries, frameworks and models. Everything below was prepared before 14 Nov 2026.
The application code was written on the day; the git history shows when.

| Date | What | Who |
|---|---|---|
| 12 Nov | Plan, Claude Code rules (CLAUDE.md files, settings), repo config, docs templates | Niccolò, with Claude |
| | Reading test on AD 2012-02-02 (go/no-go on the domain) | both |
| | Answer from KVA on what pre-event setup is allowed: … | Matteo |
| 13 Nov | Python dependencies pinned (no application code) | Niccolò |
| 13 Nov | A helper script for Claude Code tooling; deleted on 14 Nov because KVA does not allow using its key for Claude Code (see git history) | Niccolò, with Claude |
| 13 Nov | Dataset index (data/raw/INDEX.md) and 2 draft golden labels, prepared with Claude | Niccolò |
| 13 Nov | Dataset: FAA AD texts (EASA mirror / Federal Register) and EASA AD texts (Tecnam), downloaded and converted with a helper script kept outside the repo; provenance in data/raw/ads/SOURCES.csv | Niccolò, with Claude |
| 13 Nov | Dataset: 5 real EU aircraft from the Irish IAA register snapshot (no owner data) + a fictional demo fleet (DEMO-01…05) | Niccolò |
| 13 Nov | Golden set: 5 ADs, every field checked against the AD text by Niccolò (drafts written with Claude Code) | Niccolò, with Claude |
| 13 Nov | API contract (spec + example JSON from real AD text and the synthetic fleet) | Niccolò, with Claude; Matteo reviews on 14 Nov before 10:30 |
| 13 Nov | Business case research (desk validation from public sources) | Matteo |
| 13 Nov | Pitch outline and demo script | Matteo |

## AI models and tools used (required by §7 in the submission)
- Claude (claude.ai and Claude Code) for planning, research and code assistance
- On the day: … (the LLM inside the product, the KVA harness, anything else)
