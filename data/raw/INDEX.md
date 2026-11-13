# Dataset index — airworthiness directives (ADs)

Prepared before the event (rule §7: a dataset we have the right to use). FAA ADs are US
government documents; EASA ADs are public and credited to EASA.
Status: **verified** = checked against the official text or an official mirror on 13 Nov ·
**to check** = read paragraph (b) "Affected ADs" / the Supersedure field and fill in.
File naming: `data/raw/ads/FAA-<AD number>.txt` and `data/raw/ads/EASA-<AD number>.txt`.

## FAA — Cessna 172R / 172S airframe

| ID | Subject | Effective | Applicability (short) | Relation | Source | Status | Role in the demo |
|---|---|---|---|---|---|---|---|
| FAA:2008-03-02 | Fuel return line chafing | 2008-03-06 | 172R, 172S (serials: read text) | superseded by 2012-02-02 | https://ad.easa.europa.eu/blob/20080302_Superseded.pdf/AD_US-2008-03-02_1 | verified | old rule that turns red |
| FAA:2012-02-02 | Fuel return line chafing (adds serials) | 2012-03-13 | Group 1: Model 172R, S/N 17281188 through 17281390 · Group 2: Model 172S, S/N 172S9491 through 172S10489 · Group 3: Model 172R, S/N 17281391 through 17281572 · Group 4: Model 172S, S/N 172S10490 through 172S11073 ((c)(1)–(4)) | supersedes 2008-03-02 | https://ad.easa.europa.eu/blob/20120202.pdf/AD_US-2012-02-02_1 | verified | the supersession story |
| FAA:2012-22-01 | Fuel return line, aircraft with the fuel return modification kit | 2012-12-28 | 172R/172S that incorporated SB04-28-03 + kit MK172-28-01 (incl. 172S S/N 172S8001–172S9490) | same subject as 2012-02-02, **not** a supersession. Own (b) Affected ADs: “None.” | https://www.federalregister.gov/documents/2012/11/23/2012-26500/airworthiness-directives-cessna-aircraft-company-airplanes | verified | "looks like the same AD but isn't" (where RAG gets confused) + depends on a modification → QUESTION |
| FAA:2013-03-15 | Install fuel return line support clamps and brackets | 2013-03-19 | 172R S/N 17281573–17281616 · 172S S/N 172S11074–172S11193 | Affected ADs: none | https://www.govinfo.gov/content/pkg/FR-2013-02-12/pdf/2013-02897.pdf (the PDF also contains other rules: keep only AD 2013-03-15) | verified | deadline: whichever is later of next annual / 100 h TIS / 12 months after 2013-03-19 |
| FAA:2006-17-04 | Flexible fuel hose end fittings | 2006-09-01 | 172R, 172S, 182T, T182T, 206H, T206H | superseded by 2007-08-03. Own (b): “None.” · 2007-08-03 (b): “This AD supersedes AD 2006-17-04; Amendment 39-14725.” | search "2006-17-04" on https://ad.easa.europa.eu | verified | second supersession pair |
| FAA:2007-08-03 | Flexible fuel hose end fittings (torque) | 2007-05-02 | 172R, 172S, 182T, T182T, 206H, T206H | supersedes 2006-17-04 | https://www.govinfo.gov/content/pkg/FR-2007-04-12/pdf/E7-6826.pdf | verified | |
| FAA:2003-24-13 | KAP 140 autopilot software | 2004-01-20 | 172R/172S/182S/182T/T182T/206H/T206H with KAP 140 | superseded by 2004-15-18. Own (b): “None.” · 2004-15-18 (b): “This AD supersedes AD 2003-24-13.” | search "2003-24-13" on https://ad.easa.europa.eu | verified | third supersession pair |
| FAA:2004-15-18 | KAP 140 autopilot software (corrects the applicability) | 2004-09-12 | same models, **only if a KAP 140 is installed** | supersedes 2003-24-13 | https://www.govinfo.gov/content/pkg/FR-2004-07-30/pdf/04-17217.pdf | verified | depends on equipment → QUESTION "is a KAP 140 installed?" |
| FAA:2011-10-09 | Seat rails, repetitive inspection | 2011-06-17 | all S/N of the Cessna models listed in (c); the 172 group (c)(4) runs 172 … 172Q, 172RG, F/FR/P/R172 variants — **172R and 172S are not listed** | supersedes 87-20-03 R2, Amendment 39-6669 ((b)) | https://www.govinfo.gov/content/pkg/FR-2011-05-13/html/2011-10988.htm | verified ((b) and (c) of the new file) | repetitive deadline; also a "172" AD that does NOT apply to 172R/172S |
| FAA:2008-10-02 | Alternate static air source selector valve | 2008-05-12 | Cessna 172 series (Table 2 incl. 172R all S/N from 17280001, 172S 172S8001–172S10671); only with P/N 2013142-18 valve installed after 2007-11-19 | Own (b): “None.” · related to (not superseded by) 2008-26-10 | search "2008-10-02" on https://ad.easa.europa.eu | verified | labelling exercise |
| FAA:2008-26-10 | Alternate static air source selector valve | 2009-01-05 | Cessna 172, 175, 177, 180, 182… series | relates to, does not supersede. (b): “This AD relates to AD 98-01-01, Amendment 39-10287 and AD 2008-10-02, Amendment 39-15508.” (there is a correction 2010-28579) | https://www.govinfo.gov/content/pkg/FR-2008-12-24/pdf/E8-30465.pdf | verified | |
| FAA:2020-18-01 | Forward cabin doorpost cracks (repetitive) | 2020-11-12 | 172N, 172P, 172Q, 172RG, F172N, F172P, FR172K, R172K, 182E… — **172R and 172S are not listed** | — | https://public-inspection.federalregister.gov/2020-22039.pdf | verified (cite the SUMMARY sentence: the applicability table in the PDF is an image, checked by eye, 172R/172S absent) | probably the **negative case**: a "172" AD that does NOT apply to our aircraft |

## FAA — Lycoming IO-360-L2A engine (fitted to the 172R/172S)

| ID | Subject | Effective / published | Applicability (short) | Relation | Source | Status | Role in the demo |
|---|---|---|---|---|---|---|---|
| FAA:2006-12-07 | ECi cylinder assemblies (P/N AEL65102 series) | 2006-07-11 | Lycoming 320/360/540 parallel-valve incl. IO-360-L2A, **only with those ECi cylinders** | supersedes 2005-26-10 | https://ad.easa.europa.eu/blob/20061207.pdf/AD_US-2006-12-07_1 | verified | **inference** aircraft → engine → AD + depends on a part → QUESTION |
| FAA:2006-20-09 | Crankshaft replacement | published 2006-09-29 | engines listed by serial number | superseded by 2012-19-01 | https://www.federalregister.gov/documents/2006/09/29/E6-15958/airworthiness-directives-lycoming-engines-lo-360-lio-360-aeio-360-o-540-io-540-aeio-540-ltio-540 | verified (relation) | |
| FAA:2012-19-01 | Crankshafts (adds IO-390 etc.) | published 2012-09-19 | applies if the crankshaft serial is listed in Lycoming MSB 569A | supersedes 2006-20-09 | https://www.federalregister.gov/documents/2012/09/19/2012-22924/airworthiness-directives-lycoming-engines-reciprocating-engines | verified (relation) | depends on a part → QUESTION |
| FAA:2005-19-11 | Crankshafts, Lycoming 360/540 ≤ 300 HP | read text | read text | read text | https://ad.easa.europa.eu/blob/20051911.pdf/AD_US-2005-19-11_1 | optional | |

## EASA — Tecnam (Italian design, EASA is the authority)

| ID | Subject | Effective | Applicability (short) | Relation | Source | Status | Role in the demo |
|---|---|---|---|---|---|---|---|
| EASA:2018-0072 | P2008 JC — firewall inspection | 27 Jun 2019 per the CAA NZ schedule (check on EASA) | P2008 JC S/N 1002 through 1085 | — | https://ad.easa.europa.eu/ad/2018-0072 | applicability verified | serial-range applicability, European |
| EASA:2024-0152 | P2008 JC — Advanced Start System deactivation | 15 Aug 2024 | P2008 JC all S/N, except those with Tecnam modification MOD2008/233 or SB-826-CS embodied | revised by 2024-0152R1 | https://ad.easa.europa.eu/ad/2024-0152 | verified | |
| EASA:2024-0152R1 | same, revision 1 | 27 Feb 2025 | same | revises 2024-0152 | https://ad.easa.europa.eu/ad/2024-0152 | verified | `revises` link + "mod embodied?" → QUESTION |
| EASA:2011-0153R1 | P2006T — landing gear emergency accumulator | dated 09 Sep 2011 | P2006T aeroplanes, all serial numbers | Own Revision field: “This AD revises EASA AD 2011-0153-E dated 25 August 2011.” · 2012-0043 Supersedure: “This AD supersedes EASA AD 2011-0153R1 dated 09 September 2011.” | https://ad.easa.europa.eu/ad/2011-0153 | verified | |
| EASA:2012-0043 | P2006T — landing gear emergency accumulator replacement (SB-080-CS) | issued 2012-03-19, effective 2012-04-02 | read text | supersedes 2011-0153R1 | https://ad.easa.europa.eu/blob/easa_ad_2012_0043.pdf/AD_2012-0043_1 | verified | European supersession |

## What this set covers
- **Supersession** (FAA): 5 verified pairs (2008-03-02→2012-02-02, 2006-17-04→2007-08-03, 2003-24-13→2004-15-18, 2006-20-09→2012-19-01, 2005-26-10→2006-12-07 — 2005-26-10 not in the set) + 2011-10-09 superseding 87-20-03 R2 (not in the set). **Not a supersession (traps):** 2012-22-01 vs 2012-02-02 (same subject); 2008-26-10 “relates to” 2008-10-02. **Supersession** (EASA): 2011-0153R1→2012-0043 + 1 revision (2024-0152→2024-0152R1).
- **Positive and negative applicability:** serial ranges on both sides; two "172" ADs that do NOT cover the 172R/172S: 2020-18-01 and 2011-10-09.
- **Inference:** aircraft → installed engine → engine ADs.
- **Unknowns (QUESTION):** ADs that depend on equipment, a modification or a part (KAP 140, kit MK172-28-01, ECi cylinders, MOD2008/233).
- **Deadlines:** "whichever is later" (2013-03-15). Repetitive inspections are out of scope, and neither repetitive AD in the set (2011-10-09, 2020-18-01) applies to our aircraft.
