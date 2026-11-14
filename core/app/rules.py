"""Deterministic rules: serial normalisation, applicability, aircraft status. No I/O, no LLM."""
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.ontology import OPPOSITE, Aircraft, Citation, GoldenApplicability, LoadedAD, LogbookRow, Question, Urgency

log = logging.getLogger("adbrain.rules")

MANUFACTURER_PREFIXES = ("CESSNA", "TECNAM")
# Register format "<model>-<digits>" → AD serial format. Only these models; anything else is unclear.
REGISTER_HYPHEN_PREFIX = {"172S": "172S", "172R": "172"}  # 172S-10705 → 172S10705 · 172R-80221 → 17280221
SERIAL_RE = re.compile(r"^(?P<prefix>(?:.*[A-Z])?)(?P<number>\d+)$")
URGENCY_HIGH_DAYS = 30
URGENCY_MEDIUM_DAYS = 90
NO_RECORDS_REASON = "AD applies — no compliance records in this system"
QUESTION_BLOCKS = "ARC review sign-off"
QUESTION_DEADLINE_DRIVER = "ARC review due (synthetic)"
CONDITION_VERB = {"equipment_installed": "installed", "part_installed": "installed",
                  "modification_not_embodied": "embodied"}

Verdict = Literal["applies", "not_applicable", "unknown"]


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
    """'Group 4: Model 172S, …' → 'Group 4'. Only when the quote itself names the group."""
    m = re.match(r"^(Group \d+):", row.quote)
    return m[1] if m else None


def evaluate(ad: LoadedAD, aircraft: Aircraft, facts: dict[str, list[LogbookRow]]) -> Applicability:
    """Model + serial range + conditions. `facts` = this aircraft's observations by fact key."""
    model = normalise_model(aircraft.model)
    rows = [r for r in ad.golden.applicability if normalise_model(r.model) == model]
    if not rows:
        return Applicability("not_applicable", f"model {model} is not listed")

    ranged = [r for r in rows if r.serial_from is not None or r.serial_to is not None]
    match = next((r for r in rows if r not in ranged), None)  # an all-serials row matches any serial
    if match is None:
        norm = normalise_serial(aircraft.serial, model)
        serial = parse_serial(norm) if norm else None
        if serial is None or all(parse_serial(r.serial_from or r.serial_to).prefix != serial.prefix for r in ranged):
            log.warning("serial unclear: %r (%s, %s)", aircraft.serial, aircraft.id, ad.ad_id)
            return Applicability("unknown", f"serial unclear: {aircraft.serial}",
                                 question=f"serial unclear: {aircraft.serial}",
                                 citations=[ad.cite(r.quote) for r in rows])
        match = next((r for r in ranged if in_range(serial, r)), None)
        if match is None:
            return Applicability("not_applicable", f"S/N {norm} is outside "
                                 + ", ".join(range_text(r) for r in ranged))
        why = f"S/N {norm} is within {range_text(match)}"
    else:
        why = range_text(match)
    if label := group_label(match):
        why += f" ({label})"
    cites = [ad.cite(match.quote)]

    unknown, used = [], []
    for cond in ad.golden.conditions:
        obs = facts.get(cond.fact, [])
        values = {o.value for o in obs}
        used += [o.id for o in obs]
        if len(values) > 1:
            log.warning("contradicting observations %s for %s on %s", [o.id for o in obs], cond.fact, aircraft.id)
            unknown.append(cond)
        elif values == {cond.applies_when}:
            why += f"; {cond.fact} = {cond.applies_when} ({obs[0].id})"
        elif values == {OPPOSITE[cond.applies_when]}:
            return Applicability("not_applicable", f"{why}, but {cond.fact} = {obs[0].value} ({obs[0].id})",
                                 row=match, citations=cites + [ad.cite(cond.quote)], observations=used)
        else:
            if values:
                log.warning("observation value %s does not fit condition %s on %s", values, cond.fact, aircraft.id)
            unknown.append(cond)
    if unknown:
        cites += [ad.cite(q) for q in dict.fromkeys(c.quote for c in unknown)]
        by_verb: dict[str, list[str]] = {}
        for c in unknown:
            by_verb.setdefault(CONDITION_VERB[c.kind], []).append(c.value)
        question = " ".join(f"Is {' or '.join(v)} {verb} on {aircraft.id}?" for verb, v in by_verb.items())
        return Applicability("unknown", why, row=match, question=question, citations=cites, observations=used)
    return Applicability("applies", why, row=match, citations=cites, observations=used)


def urgency(days_left: int) -> Urgency:
    """q5 rule: overdue < 0 days · high ≤ 30 · medium ≤ 90 · low > 90."""
    if days_left < 0:
        return "overdue"
    if days_left <= URGENCY_HIGH_DAYS:
        return "high"
    return "medium" if days_left <= URGENCY_MEDIUM_DAYS else "low"


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
    results: dict[str, Applicability]  # ad_id → verdict
    compliance: dict[str, LogbookRow]  # ad_id → compliance record
    questions: list[Question]


def assess(aircraft: Aircraft, ads: list[LoadedAD], logbook: list[LogbookRow], today: date) -> Assessment:
    rows = [r for r in logbook if r.aircraft_id == aircraft.id]
    facts: dict[str, list[LogbookRow]] = {}
    for r in rows:
        if r.kind == "observation" and r.fact:
            facts.setdefault(r.fact, []).append(r)
    compliance = {r.ad_id: r for r in rows if r.kind == "compliance"}
    results = {ad.ad_id: evaluate(ad, aircraft, facts) for ad in ads}

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
    return Assessment(aircraft, aircraft_status(aircraft.synthetic, unrecorded, bool(questions)),
                      results, compliance, questions)
