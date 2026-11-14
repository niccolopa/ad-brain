# Decision model — AD Brain

The airworthiness decision is made by explicit, tested rules in `core/app/rules.py`, never by the LLM.
The LLM only fills the model's inputs (applicability, conditions, supersession, credit) from the AD text,
and every input it fills must quote the text and agree with a human-checked golden file before it is used
(`core/app/extract.py`). Every reasoning step in an answer names the rule that fired (`rule_id`).

**Inputs** of one decision: the aircraft (model, serial, engine model, synthetic or real), its logbook rows
(compliance records and observed facts), the active ADs (golden records), and the as-of date.
**Outcome**: per AD *applies / not applicable / unknown*; per aircraft *red / amber / green / no_records*;
per earlier compliance *yes / no_record / unknown / not_applicable*.
**Cases the model does not cover go to a person**: they become a QUESTION (amber for the synthetic fleet),
or a clause listed as *not evaluated* in the answer. Nothing uncovered is guessed.

Source column: **AD** = the AD text pattern the rule implements (with an example) · **Contract** =
`contract/README.md` · **Policy** = our own rule (`core/CLAUDE.md`, `docs/ARCHITECTURE.md`), not a regulation.

| Id | Inputs | Condition | Outcome | Source |
|---|---|---|---|---|
| R-MODEL-EXACT | aircraft model; AD applicability rows | normalised model (manufacturer word dropped) equals a row's model exactly | row is a candidate; `172RG` never matches `172R` | AD: "Group 1: Model 172R, serial numbers (S/N) 17281188 through 17281390" (FAA 2012-02-02) |
| R-MODEL-SERIES | engine model; series rows | engine model starts with `<series>-` | row is a candidate (`IO-360-L2A` in `IO-360`; not `AEIO-360-B1B`) | AD: "This AD applies to Lycoming Engines (L)O-360, (L)IO-360, AEIO-360, IO-390, AEIO-390," (FAA 2012-19-01) |
| R-MODEL-NOT-LISTED | aircraft and engine model | no row matches either | not applicable | AD: the applicability paragraph lists models; anything else is outside it |
| R-ENGINE-DERIVED | aircraft `hasInstalled` engine; AD `appliesTo` engine | no airframe row matches, an engine row does | AD `appliesTo` aircraft, **derived** (drawn dashed) | Policy: ARCHITECTURE.md §3 inference (aircraft → engine → AD) |
| R-SERIAL-NORMALISE | raw serial | OCR `l72S…`, or register `172S-NNNNN` / `172R-NNNNN` | AD-format serial (`172S…`, `172NNNNN`); no other rewrite | AD: "(2) Model 172S, S/N l72S11074 through 172S11193." (FAA 2013-03-15, OCR) · IAA register format |
| R-SERIAL-ALL | matched row | row has no serial bounds | serial is irrelevant | AD: "Tecnam P2008 JC, all serial numbers (s/n), except …" (EASA 2024-0152R1) |
| R-SERIAL-RANGE | normalised serial; row bounds | same prefix and from ≤ number ≤ to (inclusive) | applies (pending conditions) | AD: "Group 4: Model 172S, S/N 172S10490 through 172S11073" (FAA 2012-02-02) |
| R-SERIAL-OUTSIDE | normalised serial; row bounds | same prefix, outside every range | not applicable | AD: same paragraphs; both sides of every boundary are tested |
| R-UNCLEAR-TO-QUESTION | raw serial; engine serial | serial missing, malformed, other prefix, or an engine range with no engine serial | **unknown → QUESTION** "serial unclear: <raw>" | Policy: core/CLAUDE.md "store a QUESTION instead of guessing" |
| R-CONDITION-HOLDS | logbook fact/value; golden condition | observed value = `applies_when` | condition met | AD: "(1) equipped with a KAP 140 autopilot computer system" (FAA 2004-15-18) |
| R-CONDITION-FAILS | logbook fact/value; golden condition | observed value = the opposite of `applies_when` | not applicable, cites the observation | AD: "… except those on which Tecnam modification MOD2008/233 or … SB-826-CS has been embodied." (EASA 2024-0152R1) |
| R-CONDITION-UNKNOWN | logbook facts | no observation, or a value outside the condition's vocabulary | **unknown → QUESTION** (deadline = ARC review) | Contract: "'We don't know' never becomes a guess" |
| R-CONTRADICTION-TO-QUESTION | logbook facts | two observations of one fact disagree | **unknown → QUESTION**; nothing overwritten | Policy: CLAUDE.md "Contradictions … never overwrite a conflicting fact silently" |
| R-NOT-EVALUATED | golden `not_evaluated` clauses | the AD has a clause the rules cannot check (e.g. manufacture/overhaul date) | the answer says "not evaluated: <clause> (see notes)" and cites it | AD: "These applicable engines are manufactured new, rebuilt, overhauled, or had a crankshaft installed after January 1, 1997, …" (FAA 2012-19-01) |
| R-COMPLIANCE-RECORD | logbook compliance rows | a record for this AD exists | complied (`satisfies`) | Policy: ARCHITECTURE.md §2 ComplianceRecord (OBSERVATION) |
| R-CREDIT | golden `credited_compliance`; records | a record for an AD this AD credits exists | complied via credit; reason names the paragraph and cites it | AD: "(1) If you previously complied with AD 2006-20-09 (71 FR 57407, September 29, 2006), no further action is required." (FAA 2012-19-01 (g)(1)) |
| R-CREDIT-UNLABELLED | chain; records; credits | a record exists for an earlier AD, but no credit is labelled for a step | **unknown**, never "no": the label missing does not prove the text gives no credit | Policy: no guess from missing data |
| R-SUPERSEDED-NOT-COUNTED | active ADs' `supersedes` / `revises` | another active AD supersedes or revises this one | not counted for status; listed in `superseded_ads` | AD: "This AD supersedes AD 2006-20-09 (71 FR 57407, September 29, 2006)." (FAA 2012-19-01 (b)) |
| R-CHAIN | supersedes / revises links | asked AD → … → AD in force | the chain in Q3; each link cites its sentence | AD: "(b) This AD supersedes 2005-26-10, Amendment 39-14431." (FAA 2006-12-07) · EASA "Revision: This AD revises EASA AD 2024-0152 …" |
| R-CHAIN-BROKEN | supersedes / revises links | a cycle, or two ADs supersede one | **unknown**, with the reason; no AD in force picked | Policy: no guess |
| R-STATUS-RED | per-AD results; records | synthetic aircraft, an applicable AD with no record | red | Policy: ARCHITECTURE.md §6 (all golden compliance windows ended before 2026, so no record = overdue) |
| R-STATUS-AMBER | questions | synthetic aircraft, no red, ≥ 1 open QUESTION | amber | Contract: "status: amber … and the unknown as a QUESTION object" |
| R-STATUS-GREEN | per-AD results | synthetic aircraft, every applicable AD complied, no question | green | Policy: ARCHITECTURE.md §6 |
| R-REAL-NO-RECORDS | aircraft `synthetic` | a real aircraft (EU register) | always `no_records`, never red: "AD applies — no compliance records in this system" | Contract: "Real aircraft: status is no_records, never red" |
| R-DECISION-ANSWER | an answered QUESTION (DECISION by a certifying engineer) | a condition fact was supplied by a human decision, not observed | the fact is used like an observation; the decision id is cited; a clash with an observation becomes a contradiction QUESTION | Policy: ARCHITECTURE.md §4 "DECISION: a human with a role, via an action" |
| R-URGENCY | question deadline; as-of date | days until the ARC review | overdue < 0 · high ≤ 30 · medium ≤ 90 · low > 90 | Contract: q5 `urgency_rule` |

**Limits, stated:** part numbers, AMOCs, terminating actions, repetitive inspections and deadline arithmetic
are out of scope (ARCHITECTURE.md §10); an AD that needs them gets a QUESTION or a *not evaluated* line.
