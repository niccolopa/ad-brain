# Handoff — CORE
<!-- Overwrite this file at every handoff. Max 25 lines. Facts only. -->

Updated: 2026-11-13 evening · Branch: main · Last commit: c8813c2 — data: 21 AD texts, sources, verified relations, LF line endings (rule 7)

## Done since last handoff
- data/raw/INDEX.md: every relation checked against (b)/Supersedure text; 2012-02-02 has 4 groups (172R 17281188–17281390, 172S 172S9491–172S10489, 172R 17281391–17281572, 172S 172S10490–172S11073).
- Irish IAA register (30 Sep 2025): 6 × 172R, 14 × 172S, **0 × Tecnam P2008**. Owner/address/charge columns never read. demo-aircraft.csv: EI-GKN, EI-HAS, EI-GWY. EI-HAS is the real contradiction: register year 2000 vs serial order → delivery date unknown → AD 2008-26-10 is an open QUESTION.
- Demo story: DEMO-01 = 172S10600 (Group 4, delivered 2007). Group 2 compliance with 2008-03-02 would satisfy 2012-02-02 ((g)(1), (h), (i) are "Retained From AD 2008-03-02"); only Group 3/4 get a new obligation ((g)(2), from 2012-03-13). Before ingest DEMO-01 is green, after ingesting 2012-02-02 red.
- One fact, one place: italian-fleet.csv keeps identity only (mark … delivered, arc_review_due, note). Equipment facts are observations in demo-logbooks.csv (21 synthetic rows, all dated after delivery). No observation = unknown; a QUESTION only when an applicable AD depends on it. A scratch re-derivation from the two CSVs matches the draft exactly (before ingest 01/02/05 green, 03/04 amber; after, 01 red; questions: DEMO-03 ECi, DEMO-04 MOD).
- Contract draft (data/raw/pdf/contract-draft/, not copied into contract/): DEMO-01 Group 4 + (g)(2), Q3 on DEMO-01, ad-detail cites Group 4. Quote check 22/22 ok, no VERIFY.

## Next 3 steps
1. Parser: accept "l72S" (lowercase L, in 2012-22-01 and 2013-03-15) and "172S-10705" / "172R-80221" register serials; tests for each, and 172RG must not match 172R.
2. Range + deadline code with tests from real text: all 4 groups of 2012-02-02, edges 172S10489/172S10490/172S11073; (g)(2) 100 h or 12 months after 2012-03-13.
3. Status engine: DEMO-01 green → red on ingest of 2012-02-02, from demo-logbooks.csv + italian-fleet.csv; test: delete an observation → its QUESTION appears.

## Contract
change proposed: occurrence on Citation, due.citation, compliance_time field in q2-ingest, not_loaded / aircraft_status / logbook_records in demo-reset (draft, needs both of us)

## For the other role (written as GitHub issue text)
- Contract draft ready for review in data/raw/pdf/contract-draft/: fleet.json now shows DEMO-01 red (after ingest), DEMO-02 green, DEMO-03 1 question; Q-DEMO02-KAP, Q-DEMO03-VALVE, Q-DEMO01-VALVE removed.

## Tests
no code yet · smoke test: not run (no scripts/smoke.py)
