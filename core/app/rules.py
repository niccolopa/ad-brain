"""Deterministic rules: serial normalisation, applicability, aircraft status. No I/O, no LLM."""
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.ontology import (
    OPPOSITE,
    Aircraft,
    Citation,
    Fact,
    GoldenApplicability,
    GoldenCondition,
    LoadedAD,
    LogbookRow,
    Question,
    Urgency,
)

log = logging.getLogger("adbrain.rules")

MANUFACTURER_PREFIXES = ("CESSNA", "TECNAM", "LYCOMING")
# Register format "<model>-<digits>" → AD serial format. Only these models; anything else is unclear.
REGISTER_HYPHEN_PREFIX = {"172S": "172S", "172R": "172"}  # 172S-10705 → 172S10705 · 172R-80221 → 17280221
SERIAL_RE = re.compile(r"^(?P<prefix>(?:.*[A-Z])?)(?P<number>\d+)$")
URGENCY_HIGH_DAYS = 30
URGENCY_MEDIUM_DAYS = 90
NO_RECORDS_REASON = "AD applies — no compliance records in this system"
QUESTION_BLOCKS = "ARC review sign-off"
QUESTION_DEADLINE_DRIVER = "ARC review due (synthetic)"
QUESTION_TEMPLATE = {"equipment_installed": "Is {values} installed on {ac}?",
                     "part_installed": "Is {values} installed on {ac}?",
                     "modification_not_embodied": "Is {values} embodied on {ac}?",
                     "serial_listed": "Is {ac}'s {values}?"}
NOT_EVALUATED_NOTE = "not evaluated: {clause} (see notes)"
ENGINE_ID_SUFFIX = "/engine"

Verdict = Literal["applies", "not_applicable", "unknown"]
Via = Literal["airframe", "engine"]

# ---------- Rule ids. docs/DECISION-MODEL.md lists exactly these (tests/test_decision_model.py checks it) ----------
R_MODEL_EXACT = "R-MODEL-EXACT"
R_MODEL_SERIES = "R-MODEL-SERIES"
R_MODEL_NOT_LISTED = "R-MODEL-NOT-LISTED"
R_ENGINE_DERIVED = "R-ENGINE-DERIVED"
R_SERIAL_NORMALISE = "R-SERIAL-NORMALISE"
R_SERIAL_ALL = "R-SERIAL-ALL"
R_SERIAL_RANGE = "R-SERIAL-RANGE"
R_SERIAL_OUTSIDE = "R-SERIAL-OUTSIDE"
R_UNCLEAR_TO_QUESTION = "R-UNCLEAR-TO-QUESTION"
R_CONDITION_HOLDS = "R-CONDITION-HOLDS"
R_CONDITION_FAILS = "R-CONDITION-FAILS"
R_CONDITION_UNKNOWN = "R-CONDITION-UNKNOWN"
R_CONTRADICTION_TO_QUESTION = "R-CONTRADICTION-TO-QUESTION"
R_NOT_EVALUATED = "R-NOT-EVALUATED"
R_COMPLIANCE_RECORD = "R-COMPLIANCE-RECORD"
R_CREDIT = "R-CREDIT"
R_CREDIT_UNLABELLED = "R-CREDIT-UNLABELLED"
R_SUPERSEDED_NOT_COUNTED = "R-SUPERSEDED-NOT-COUNTED"
R_CHAIN = "R-CHAIN"
R_CHAIN_BROKEN = "R-CHAIN-BROKEN"
R_STATUS_RED = "R-STATUS-RED"
R_STATUS_AMBER = "R-STATUS-AMBER"
R_STATUS_GREEN = "R-STATUS-GREEN"
R_REAL_NO_RECORDS = "R-REAL-NO-RECORDS"
R_URGENCY = "R-URGENCY"
R_DECISION_ANSWER = "R-DECISION-ANSWER"
RULE_IDS = frozenset(v for k, v in dict(globals()).items() if k.startswith("R_") and isinstance(v, str))
STATUS_RULE = {"red": R_STATUS_RED, "amber": R_STATUS_AMBER, "green": R_STATUS_GREEN,
               "no_records": R_REAL_NO_RECORDS}


@dataclass(frozen=True)
class Serial:
    prefix: str
    number: int


@dataclass
class Applicability:
    """Does one AD apply to one aircraft, and why. `unknown` always carries a question text."""
    verdict: Verdict
    why: str
    row: GoldenApplicability | None = None
    question: str | None = None
    citations: list[Citation] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)  # logbook row ids used
    via: Via = "airframe"
    rule_ids: list[str] = field(default_factory=list)  # every rule that fired, in order
    decided_by: str = ""  # the rule that decided the verdict
    unknown_conditions: list[GoldenCondition] = field(default_factory=list)  # what an answer to its QUESTION sets


def normalise_model(raw: str) -> str:
    """'Cessna 172S' / 'CESSNA 172S' / '172S' → '172S'. Exact compare afterwards: 172RG ≠ 172R."""
    words = raw.upper().split()
    if words and words[0] in MANUFACTURER_PREFIXES:
        words = words[1:]
    return " ".join(words)


def normalise_serial(raw: str | None, model: str) -> str | None:
    """AD-format serial, or None when unclear (→ QUESTION, never 'not applicable').
    Explicit rules only: OCR 'l72S…' → '172S…'; register '<model>-<digits>' via REGISTER_HYPHEN_PREFIX."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip()
    if len(s) > 1 and s[0] == "l" and s[1].isdigit():  # OCR: lowercase L for 1
        s = "1" + s[1:]
    s = s.upper()
    if s.count("-") == 1:
        head, tail = s.split("-")
        if head != model or head not in REGISTER_HYPHEN_PREFIX or not tail.isdigit():
            return None
        s = REGISTER_HYPHEN_PREFIX[head] + tail
    if not re.fullmatch(r"[A-Z0-9]+", s) or not SERIAL_RE.match(s):
        return None
    return s


def parse_serial(s: str) -> Serial:
    """'172S10600' → ('172S', 10600) · '17281188' → ('', 17281188) · 'T18208001' → ('T', 18208001)."""
    m = SERIAL_RE.match(s)
    if not m:
        raise ValueError(f"not a serial: {s!r}")
    return Serial(m["prefix"], int(m["number"]))


def in_range(serial: Serial, row: GoldenApplicability) -> bool:
    if row.serial_from is None and row.serial_to is None:
        return True
    lo, hi = parse_serial(row.serial_from or row.serial_to), parse_serial(row.serial_to or row.serial_from)
    return serial.prefix == lo.prefix == hi.prefix and lo.number <= serial.number <= hi.number


def range_text(row: GoldenApplicability) -> str:
    if row.serial_from is None and row.serial_to is None:
        return f"{row.model}, all serial numbers"
    if row.serial_from == row.serial_to:
        return f"S/N {row.serial_from}"
    return f"{row.serial_from}–{row.serial_to}"


def group_label(row: GoldenApplicability) -> str | None:
    """'Group 4: Model 172S, …' or '(4) Group 4: Model 172S, …' → 'Group 4'. Only when the quote names the group."""
    m = re.match(r"^(?:\(\d+\)\s*)?(Group \d+):", row.quote)
    return m[1] if m else None


def model_matches(row: GoldenApplicability, model: str) -> bool:
    """Exact model, or for a series row ('IO-360') any model of that series ('IO-360-L2A', not 'AEIO-360-B1B')."""
    m = normalise_model(row.model)
    return model.startswith(m + "-") if row.series else model == m


def engine_id(aircraft: Aircraft) -> str:
    return aircraft.id + ENGINE_ID_SUFFIX


def evaluate(ad: LoadedAD, aircraft: Aircraft, facts: dict[str, list[LogbookRow | Fact]]) -> Applicability:
    """Model + serial range + conditions. `facts` = this aircraft's observations by fact key.
    Rows are matched on the airframe model first, else on the installed engine model (inferred link)."""
    model = normalise_model(aircraft.model)
    rows = [r for r in ad.golden.applicability if model_matches(r, model)]
    via: Via = "airframe"
    if not rows:
        engine = normalise_model(aircraft.engine_model)
        rows = [r for r in ad.golden.applicability if model_matches(r, engine)]
        if not rows:
            return Applicability("not_applicable", f"model {model} and engine {engine} are not listed",
                                 rule_ids=[R_MODEL_NOT_LISTED], decided_by=R_MODEL_NOT_LISTED)
        via = "engine"
    fired = [R_MODEL_SERIES if any(r.series for r in rows) else R_MODEL_EXACT]
    if via == "engine":
        fired.append(R_ENGINE_DERIVED)

    ranged = [r for r in rows if r.serial_from is not None or r.serial_to is not None]
    match = next((r for r in rows if r not in ranged), None)  # an all-serials row matches any serial
    if match is None and via == "engine":
        # ponytail: no engine serials in this system; a ranged engine row can only be a question
        return Applicability("unknown", f"engine serial not in this system: {engine_id(aircraft)}",
                             question=f"engine serial unclear: {engine_id(aircraft)}",
                             citations=[ad.cite(r.quote) for r in rows], via=via,
                             rule_ids=fired + [R_UNCLEAR_TO_QUESTION], decided_by=R_UNCLEAR_TO_QUESTION)
    if via == "engine":
        assert match is not None
        why = (f"engine {engine} is an {match.model} series engine" if match.series
               else f"engine {engine} is listed")
        fired.append(R_SERIAL_ALL)
    elif match is None:
        norm = normalise_serial(aircraft.serial, model)
        serial = parse_serial(norm) if norm else None
        if norm and isinstance(aircraft.serial, str) and norm != aircraft.serial.strip().upper():
            fired.append(R_SERIAL_NORMALISE)
        if serial is None or all(parse_serial(r.serial_from or r.serial_to).prefix != serial.prefix for r in ranged):
            log.warning("serial unclear: %r (%s, %s)", aircraft.serial, aircraft.id, ad.ad_id)
            return Applicability("unknown", f"serial unclear: {aircraft.serial}",
                                 question=f"serial unclear: {aircraft.serial}",
                                 citations=[ad.cite(r.quote) for r in rows],
                                 rule_ids=fired + [R_UNCLEAR_TO_QUESTION], decided_by=R_UNCLEAR_TO_QUESTION)
        match = next((r for r in ranged if in_range(serial, r)), None)
        if match is None:
            return Applicability("not_applicable", f"S/N {norm} is outside "
                                 + ", ".join(range_text(r) for r in ranged),
                                 rule_ids=fired + [R_SERIAL_OUTSIDE], decided_by=R_SERIAL_OUTSIDE)
        why = f"S/N {norm} is within {range_text(match)}"
        fired.append(R_SERIAL_RANGE)
    else:
        why = range_text(match)
        fired.append(R_SERIAL_ALL)
    decided = fired[-1]
    if label := group_label(match):
        why += f" ({label})"
    cites = [ad.cite(match.quote)]

    unknown, used = [], []
    for cond in ad.golden.conditions:
        obs = facts.get(cond.fact, [])
        values = {o.value for o in obs}
        used += [o.id for o in obs]
        if any(getattr(o, "source", "observation") == "decision" for o in obs):
            fired.append(R_DECISION_ANSWER)  # a person with a role supplied this fact by answering a QUESTION
        if len(values) > 1:
            log.warning("contradicting observations %s for %s on %s", [o.id for o in obs], cond.fact, aircraft.id)
            unknown.append(cond)
            fired.append(R_CONTRADICTION_TO_QUESTION)
        elif values == {cond.applies_when}:
            why += f"; {cond.fact} = {cond.applies_when} ({obs[0].id})"
            fired.append(R_CONDITION_HOLDS)
            decided = R_CONDITION_HOLDS
        elif values == {OPPOSITE[cond.applies_when]}:
            return Applicability("not_applicable", f"{why}, but {cond.fact} = {obs[0].value} ({obs[0].id})",
                                 row=match, citations=cites + [ad.cite(cond.quote)], observations=used, via=via,
                                 rule_ids=fired + [R_CONDITION_FAILS], decided_by=R_CONDITION_FAILS)
        else:
            if values:
                log.warning("observation value %s does not fit condition %s on %s", values, cond.fact, aircraft.id)
            unknown.append(cond)
            fired.append(R_CONDITION_UNKNOWN)
    # Never hide a limit: clauses the rules do not evaluate are named in the answer and cited.
    for n in ad.golden.not_evaluated:
        why += "; " + NOT_EVALUATED_NOTE.format(clause=n.clause)
        cites.append(ad.cite(n.quote))
        fired.append(R_NOT_EVALUATED)
    fired = list(dict.fromkeys(fired))
    if unknown:
        cites += [ad.cite(q) for q in dict.fromkeys(c.quote for c in unknown)]
        by_template: dict[str, list[str]] = {}
        for c in unknown:
            by_template.setdefault(QUESTION_TEMPLATE[c.kind], []).append(c.value)
        question = " ".join(tpl.format(values=" or ".join(v), ac=aircraft.id) for tpl, v in by_template.items())
        decided = R_CONTRADICTION_TO_QUESTION if R_CONTRADICTION_TO_QUESTION in fired else R_CONDITION_UNKNOWN
        return Applicability("unknown", why, row=match, question=question, citations=cites, observations=used,
                             via=via, rule_ids=fired, decided_by=decided, unknown_conditions=unknown)
    return Applicability("applies", why, row=match, citations=cites, observations=used, via=via, rule_ids=fired,
                         decided_by=decided)


def urgency(days_left: int) -> Urgency:
    """q5 rule: overdue < 0 days · high ≤ 30 · medium ≤ 90 · low > 90."""
    if days_left < 0:
        return "overdue"
    if days_left <= URGENCY_HIGH_DAYS:
        return "high"
    return "medium" if days_left <= URGENCY_MEDIUM_DAYS else "low"


URGENCY_RULE = (f"overdue < 0 days · high ≤ {URGENCY_HIGH_DAYS} · medium ≤ {URGENCY_MEDIUM_DAYS} · "
                f"low > {URGENCY_MEDIUM_DAYS} (days until the deadline)")
URGENCY_ORDER = {"overdue": 0, "high": 1, "medium": 2, "low": 3, None: 4}  # None: real aircraft, no deadline


def sort_questions(questions: list[Question]) -> list[Question]:
    """By urgency, then days_left (no deadline last), then id for a stable order."""
    return sorted(questions, key=lambda q: (URGENCY_ORDER[q.urgency],
                                            q.days_left if q.days_left is not None else float("inf"), q.id))


def due_citation(ad: LoadedAD, row: GoldenApplicability | None) -> Citation | None:
    """The compliance-time quote naming the matched group ('Group 3 and Group 4' for Group 4); else None."""
    label = group_label(row) if row else None
    if label is None:
        return None
    quotes = [q for q in ad.golden.field_quotes.get("compliance_time_text", [])
              if re.search(rf"\b{label}\b", q)]
    return ad.cite(quotes[0]) if len(quotes) == 1 else None


def aircraft_status(synthetic: bool, any_unrecorded: bool, any_unknown: bool) -> str:
    """Real aircraft: always no_records (never red). Synthetic: red > amber > green."""
    if not synthetic:
        return "no_records"
    # ponytail: no record = overdue — every golden compliance window ended before 2026; deadline arithmetic in v2.
    if any_unrecorded:
        return "red"
    return "amber" if any_unknown else "green"


def days_until(deadline: str | None, today: date) -> int | None:
    return None if deadline is None else (date.fromisoformat(deadline) - today).days


@dataclass
class Assessment:
    """Everything Q1 and Q2 need about one aircraft against the loaded ADs."""
    aircraft: Aircraft
    status: str
    results: dict[str, Applicability]  # ad_id → verdict, active ADs only
    compliance: dict[str, LogbookRow]  # ad_id → compliance record (its own, or a credited AD's)
    credits: dict[str, Citation]  # ad_id → quote that credits the record of another AD
    questions: list[Question]
    superseded: list[str]  # ADs that would apply but are superseded by an active AD: not counted for status
    rule_ids: list[str] = field(default_factory=list)  # every rule that fired for this aircraft, status rule last


def assess(aircraft: Aircraft, ads: list[LoadedAD], logbook: list[LogbookRow], today: date,
           decision_facts: list[Fact] | tuple[Fact, ...] = ()) -> Assessment:
    rows = [r for r in logbook if r.aircraft_id == aircraft.id]
    facts: dict[str, list[LogbookRow | Fact]] = {}
    for r in rows:
        if r.kind == "observation" and r.fact:
            facts.setdefault(r.fact, []).append(r)
    for f in decision_facts:
        if f.aircraft_id == aircraft.id:
            facts.setdefault(f.fact, []).append(f)
    records = {r.ad_id: r for r in rows if r.kind == "compliance"}
    compliance: dict[str, LogbookRow] = {}
    credits: dict[str, Citation] = {}
    for ad in ads:
        if ad.ad_id in records:
            compliance[ad.ad_id] = records[ad.ad_id]
            continue
        for credit in ad.golden.credited_compliance:
            if credit.ad_id in records:
                compliance[ad.ad_id], credits[ad.ad_id] = records[credit.ad_id], ad.cite(credit.quote, credit.occurrence)
                break
    loaded = {ad.ad_id for ad in ads}
    replaced = {old for ad in ads for old in ad.golden.supersedes + ad.golden.revises if old in loaded}
    all_results = {ad.ad_id: evaluate(ad, aircraft, facts) for ad in ads}
    superseded = [k for k, r in all_results.items() if k in replaced and r.verdict != "not_applicable"]
    results = {k: r for k, r in all_results.items() if k not in replaced}

    questions = []
    deadline = aircraft.arc_review_due if aircraft.synthetic else None
    days = days_until(deadline, today)
    for ad_id, res in results.items():
        if res.verdict == "unknown":
            questions.append(Question(
                id=f"Q-{aircraft.id}-{ad_id}", text=res.question or res.why, aircraft_id=aircraft.id, ad_id=ad_id,
                blocks=QUESTION_BLOCKS, deadline=deadline,
                deadline_driver=QUESTION_DEADLINE_DRIVER if deadline else None,
                days_left=days, urgency=urgency(days) if days is not None else None,
                synthetic=aircraft.synthetic, citations=res.citations))
    unrecorded = any(r.verdict == "applies" and ad_id not in compliance for ad_id, r in results.items())
    status = aircraft_status(aircraft.synthetic, unrecorded, bool(questions))
    fired = [rid for r in results.values() for rid in r.rule_ids]
    applied = [k for k, r in results.items() if r.verdict == "applies" and k in compliance]
    if any(k not in credits for k in applied):
        fired.append(R_COMPLIANCE_RECORD)
    if any(k in credits for k in applied):
        fired.append(R_CREDIT)
    if superseded:
        fired.append(R_SUPERSEDED_NOT_COUNTED)
    if any(q.urgency for q in questions):
        fired.append(R_URGENCY)
    fired.append(STATUS_RULE[status])
    return Assessment(aircraft, status, results, compliance, credits, questions, superseded,
                      list(dict.fromkeys(fired)))


# ---------- Q3: supersession chain and validity of earlier compliance ----------
ChainLinkType = Literal["supersedes", "revises"]
Validity = Literal["yes", "no_record", "unknown", "not_applicable"]


@dataclass
class ChainStep:
    ad_id: str
    successor: str | None = None  # the AD that supersedes/revises this one (None = in force, or chain broken)
    link: ChainLinkType | None = None


def successors(ad_id: str, ads: dict[str, LoadedAD]) -> list[tuple[str, ChainLinkType]]:
    return ([(a.ad_id, "supersedes") for a in ads.values() if ad_id in a.golden.supersedes]
            + [(a.ad_id, "revises") for a in ads.values() if ad_id in a.golden.revises])


def is_known_ad(ad_id: str, ads: dict[str, LoadedAD]) -> bool:
    """Loaded, or named by a loaded AD (e.g. a superseded AD with no golden file)."""
    return ad_id in ads or bool(successors(ad_id, ads))


def supersession_chain(ad_id: str, ads: dict[str, LoadedAD]) -> tuple[list[ChainStep], str | None]:
    """Asked AD → … → the AD in force. Returns (chain, problem); a problem means no AD in force can be named."""
    chain, seen = [], set()
    current = ad_id
    while True:
        if current in seen:
            log.warning("supersession cycle at %s (from %s)", current, ad_id)
            return chain, f"supersession cycle: {' → '.join(s.ad_id for s in chain)} → {current}"
        seen.add(current)
        nxt = successors(current, ads)
        if len(nxt) > 1:
            log.warning("%s superseded by more than one AD: %s", current, nxt)
            chain.append(ChainStep(current))
            return chain, f"{current} is superseded by more than one AD: {', '.join(n for n, _ in nxt)}"
        if not nxt:
            chain.append(ChainStep(current))
            return chain, None
        chain.append(ChainStep(current, nxt[0][0], nxt[0][1]))
        current = nxt[0][0]


@dataclass
class StillValid:
    value: Validity
    reason: str
    record: LogbookRow | None = None
    credits: list[Citation] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)


def still_valid(chain: list[ChainStep], problem: str | None, head_result: Applicability | None,
                records: dict[str, LogbookRow], ads: dict[str, LoadedAD]) -> StillValid:
    """Is the compliance that counts for the AD in force still valid? A missing credit label is 'unknown', never 'no':
    the golden record not naming a credit does not prove the AD text gives none."""
    if problem or head_result is None:
        return StillValid("unknown", problem or "no AD in force could be determined", rule_ids=[R_CHAIN_BROKEN])
    head = chain[-1].ad_id
    base = ([R_CHAIN] if len(chain) > 1 else []) + head_result.rule_ids
    if head_result.verdict == "not_applicable":
        return StillValid("not_applicable", f"{head} (in force) does not apply: {head_result.why}", rule_ids=base)
    if head_result.verdict == "unknown":
        return StillValid("unknown", f"whether {head} (in force) applies is open: {head_result.question}",
                          rule_ids=base)
    if head in records:
        return StillValid("yes", f"{head} is in force and has its own compliance record {records[head].id}",
                          records[head], rule_ids=base + [R_COMPLIANCE_RECORD])
    for i in range(len(chain) - 2, -1, -1):  # nearest earlier AD with a record first
        old = chain[i].ad_id
        if old not in records:
            continue
        rec, cites, notes = records[old], [], []
        for prev, step in zip(chain[i:], chain[i + 1:]):
            credit = next((c for c in ads[step.ad_id].golden.credited_compliance if c.ad_id == prev.ad_id), None)
            if credit is None:
                return StillValid("unknown", f"{head} has no compliance record of its own; record {rec.id} is for "
                                  f"{old}, and the labelled data names no credit in {step.ad_id} for {prev.ad_id}: "
                                  "check the AD text", rec, rule_ids=base + [R_CREDIT_UNLABELLED])
            cites.append(ads[step.ad_id].cite(credit.quote, credit.occurrence))
            notes.append(f"paragraph {credit.paragraph or '(unnamed)'} of {step.ad_id}: \"{credit.quote}\"")
        return StillValid("yes", f"{head} has no compliance record of its own; record {rec.id} (compliance with "
                          f"{old}) is credited by " + "; ".join(notes), rec, cites, rule_ids=base + [R_CREDIT])
    for credit in ads[head].golden.credited_compliance:  # asked AD is the head: its own credits (same rule as Q1)
        if credit.ad_id in records:
            rec = records[credit.ad_id]
            return StillValid("yes", f"{head} has no compliance record of its own; record {rec.id} (compliance with "
                              f"{credit.ad_id}) is credited by paragraph {credit.paragraph or '(unnamed)'} of {head}: "
                              f"\"{credit.quote}\"", rec, [ads[head].cite(credit.quote, credit.occurrence)],
                              rule_ids=base + [R_CREDIT])
    names = " or ".join(s.ad_id for s in chain)
    return StillValid("no_record", f"{head} (in force) applies ({head_result.why}); no compliance record for {names}",
                      rule_ids=base)
