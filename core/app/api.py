"""One endpoint per business question (contract/README.md, "Endpoints").
Real: fleet, Q1 status, Q2 affected-aircraft and ingest, Q3 supersession, Q5 questions, AD detail, demo reset. The rest still serve contract/examples/ (fakes)."""
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import evaluations, extract, llm, rules, store
from app.ontology import (
    OPPOSITE,
    ActionLogEntry,
    AdDetailResponse,
    AdExtraction,
    AffectedAircraft,
    AffectedAircraftResponse,
    Aircraft,
    AircraftStatusResponse,
    AirworthinessDirective,
    AnswerRequest,
    AnswerResponse,
    ApplicabilityGroup,
    ApplicableAD,
    ChainLink,
    ComplianceRecord,
    ComplianceState,
    ConditionOut,
    CreditOut,
    CurrentReplay,
    DecisionRecord,
    DecisionSnapshot,
    DecisionsResponse,
    DemoResetResponse,
    Due,
    Error,
    Evaluation,
    ExtractionInfo,
    ExtractionMiss,
    Fact,
    FleetAircraft,
    FleetResponse,
    IngestChanges,
    IngestResponse,
    LoadedAD,
    NotAffected,
    NotEvaluatedOut,
    Person,
    Question,
    QuestionsResponse,
    ReasoningStep,
    RefusedAttempt,
    ReplayChanges,
    ReplayResponse,
    ResetCounts,
    StatusChange,
    SupersessionResponse,
    ValidatedField,
)

log = logging.getLogger("adbrain.api")

REPO = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO / "contract" / "examples"
DEMO_MODE = llm.demo_mode()  # /health reports the real setting

app = FastAPI(title="AD Brain core")
STATE = store.load()
EVAL_LOG = evaluations.EvaluationLog(evaluations.LOG_FILE)


class NotFound(Exception):
    """An error with a stable code. 404 unless told otherwise."""
    def __init__(self, error_code: str, message: str, details: dict, status_code: int = 404) -> None:
        self.error = Error(error_code=error_code, message=message, details=details)
        self.status_code = status_code


HTTP_FORBIDDEN, HTTP_CONFLICT, HTTP_UNPROCESSABLE = 403, 409, 422
ANSWER_ROLE = "certifying_engineer"  # only a certifying engineer answers a QUESTION (mechanic → OBSERVATION: LATER)
DEMO_PEOPLE = {  # the demo's people are synthetic; ids as in contract/examples
    "certifying_engineer": Person(id="P-CE-1", name="Certifying Engineer 1 (synthetic)", role="certifying_engineer",
                                  synthetic=True),
    "mechanic": Person(id="P-ME-1", name="Mechanic 1 (synthetic)", role="mechanic", synthetic=True),
    "agent": Person(id="P-AG-1", name="Analyst agent", role="agent", synthetic=True),
}
# "yes" to "Is X installed / embodied / listed?" sets the positive value of the condition's fact.
POSITIVE_VALUE = {"equipment_installed": "yes", "part_installed": "yes", "serial_listed": "yes",
                  "modification_not_embodied": "embodied"}
REAL_AIRCRAFT_REASON = "real aircraft: needs a real certifying engineer"


@app.exception_handler(RequestValidationError)
def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    err = Error(error_code="VALIDATION_ERROR", message="Missing or malformed parameters.",
                details={"errors": jsonable_encoder(exc.errors())})
    return JSONResponse(err.model_dump(), status_code=HTTP_UNPROCESSABLE)


@app.exception_handler(NotFound)
def not_found(_: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse(exc.error.model_dump(), status_code=exc.status_code)


@app.exception_handler(Exception)
def internal_error(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error")
    err = Error(error_code="INTERNAL_ERROR", message="Unexpected error; see the server log.", details={})
    return JSONResponse(err.model_dump(), status_code=500)


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_aircraft(aircraft_id: str) -> Aircraft:
    if aircraft_id not in STATE.aircraft:
        raise NotFound("AIRCRAFT_NOT_FOUND", f"No aircraft with id {aircraft_id} in this system.", {"id": aircraft_id})
    return STATE.aircraft[aircraft_id]


def get_ad(ad_id: str) -> LoadedAD:
    if ad_id not in STATE.ads:
        raise NotFound("AD_NOT_FOUND", f"No AD with id {ad_id} in this system.", {"ad_id": ad_id})
    return STATE.ads[ad_id]


def ad_object(ad: LoadedAD) -> AirworthinessDirective:
    by = [o.ad_id for o in STATE.ads.values() if ad.ad_id in o.golden.supersedes + o.golden.revises]
    return AirworthinessDirective(
        ad_id=ad.ad_id, authority=ad.ad_id.split(":")[0], title=ad.title, effective_date=ad.golden.effective_date,
        status="superseded" if by else "active", supersedes=ad.golden.supersedes,
        superseded_by=by[0] if by else None, revises=ad.golden.revises[0] if ad.golden.revises else None,
        source_url=ad.source_url, file=ad.file)


def decision_facts() -> list[Fact]:
    """Facts supplied by human decisions (answered QUESTIONs), used by the rules like observations."""
    return [Fact(id=d.id, aircraft_id=d.aircraft_id, fact=k, value=v) for d in STATE.decisions for k, v in d.facts.items()]


def assess(aircraft_id: str) -> rules.Assessment:
    return rules.assess(get_aircraft(aircraft_id), list(STATE.ads.values()), STATE.logbook, date.today(),
                        decision_facts())


def applies_path(aircraft: Aircraft, ad_id: str, res: rules.Applicability, suffix: str = "") -> list[ReasoningStep]:
    """AD appliesTo aircraft; via the engine: aircraft hasInstalled engine + AD appliesTo engine ⇒ derived link."""
    if res.via == "airframe":
        return [ReasoningStep(from_=ad_id, link="appliesTo", to=aircraft.id, derived=False, note=res.why + suffix,
                              rule_id=res.decided_by)]
    eng = rules.engine_id(aircraft)
    return [
        ReasoningStep(from_=aircraft.id, link="hasInstalled", to=eng, derived=False, note=aircraft.engine_model,
                      rule_id=rules.R_ENGINE_DERIVED),
        ReasoningStep(from_=ad_id, link="appliesTo", to=eng, derived=False, note=res.why, rule_id=res.decided_by),
        ReasoningStep(from_=ad_id, link="appliesTo", to=aircraft.id, derived=True,
                      note=f"inferred from the two links above: {res.why}{suffix}", rule_id=rules.R_ENGINE_DERIVED),
    ]


def summary(a: rules.Assessment, applicable: list[ApplicableAD]) -> str:
    """Template text (no LLM): the UI never needs a live call to render."""
    ac = a.aircraft.id
    if a.status == "no_records":
        return f"{ac}: {rules.NO_RECORDS_REASON}." if applicable else \
            f"{ac}: no AD in the loaded set applies; no compliance records in this system."
    if a.status == "red":
        red = [x for x in applicable if x.compliance.state == "no_record"]
        return f"{ac} is not airworthy in this system: " + "; ".join(
            f"AD {x.ad_id} applies ({x.applies_because}) and has no compliance record" for x in red) + "."
    if a.status == "amber":
        return f"{ac} has {len(a.questions)} open question(s): " + " ".join(q.text for q in a.questions)
    return f"{ac}: all applicable ADs in the loaded set are complied with or not applicable."


@app.get("/aircraft/{aircraft_id}/status", response_model=AircraftStatusResponse)
def aircraft_status(aircraft_id: str) -> AircraftStatusResponse:
    aircraft, ads, today = get_aircraft(aircraft_id), list(STATE.ads.values()), date.today()
    inputs = evaluations.snapshot_inputs(aircraft, STATE.logbook, today, decision_facts())
    a = evaluations.decide(inputs, ads)
    ev = EVAL_LOG.record(a, inputs, ads)
    applicable, path = [], []
    for ad_id, res in a.results.items():
        if res.verdict != "applies":
            continue
        ad, rec, credit = STATE.ads[ad_id], a.compliance.get(ad_id), a.credits.get(ad_id)
        applicable.append(ApplicableAD(
            ad_id=ad_id, title=ad.title, status=ad_object(ad).status, applies_because=res.why,
            compliance=ComplianceState(state="complied" if rec else "no_record", record_id=rec.id if rec else None),
            due=Due(text=ad.golden.compliance_time_text, citation=rules.due_citation(ad, res.row),
                    overdue=(rec is None) if a.aircraft.synthetic else None),
            citations=res.citations + ([credit] if credit else [])))
        path += applies_path(a.aircraft, ad_id, res, f"; complied {rec.id}" if rec else "; no compliance record")
        if rec:
            note = f"credited: compliance with {rec.ad_id}: {credit.quote}" if credit else rec.text
            path.append(ReasoningStep(from_=rec.id, link="satisfies", to=ad_id, derived=False, note=note,
                                      rule_id=rules.R_CREDIT if credit else rules.R_COMPLIANCE_RECORD))
    citations = [c for x in applicable for c in x.citations + ([x.due.citation] if x.due.citation else [])]
    citations += [c for q in a.questions for c in q.citations]
    return AircraftStatusResponse(
        aircraft=a.aircraft, status=a.status, summary=summary(a, applicable), summary_source="template",
        applicable_ads=applicable, superseded_ads=a.superseded, open_questions=a.questions, hypotheses=[],
        citations=list({c.model_dump_json(): c for c in citations}.values()),  # dedupe, keep order
        reasoning_path=path, computed_at=now_utc(),
        evaluation_id=ev["id"], rules_version=ev["rules_version"]["id"], inputs_hash=ev["inputs_hash"])


@app.get("/ads/{ad_id}/affected-aircraft", response_model=AffectedAircraftResponse)
def affected_aircraft(ad_id: str) -> AffectedAircraftResponse:
    ad = get_ad(ad_id)
    affected, not_affected, questions, path, citations = [], [], [], [], []
    for ac in STATE.aircraft.values():
        a = assess(ac.id)
        res = a.results.get(ad_id)
        if res is None:  # superseded by an active AD
            not_affected.append(NotAffected(aircraft_id=ac.id, why=f"{ad_id} is superseded"))
        elif res.verdict == "applies":
            all_serials = res.row is not None and res.row.serial_from is None and res.row.serial_to is None
            via = "installed_engine" if res.via == "engine" else "all_serials" if all_serials else "serial_range"
            affected.append(AffectedAircraft(aircraft_id=ac.id, model=ac.model, serial=ac.serial, via=via,
                                             why=res.why, status_now=a.status))
            path += applies_path(ac, ad_id, res)
            citations += res.citations
        elif res.verdict == "unknown":
            questions += [q for q in a.questions if q.ad_id == ad_id]
            citations += res.citations
        else:
            not_affected.append(NotAffected(aircraft_id=ac.id, why=res.why))
    return AffectedAircraftResponse(
        ad=ad_object(ad), checked_aircraft=len(STATE.aircraft), affected=affected, not_affected=not_affected,
        open_questions=questions, citations=list({c.model_dump_json(): c for c in citations}.values()),
        reasoning_path=path)


def example(name: str) -> JSONResponse:
    """The response of contract/examples/<name>.json, with its HTTP status."""
    resp = json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))["response"]
    return JSONResponse(resp["body"], status_code=resp["http_status"])


@app.get("/health")
def health() -> dict:
    return {"ok": True, "demo_mode": DEMO_MODE}


def statuses() -> dict[str, str]:
    return {ac_id: assess(ac_id).status for ac_id in STATE.aircraft}


@app.post("/demo/reset", response_model=DemoResetResponse)
def demo_reset() -> DemoResetResponse:
    global STATE
    STATE = store.load()
    EVAL_LOG.mark_reset()  # the evaluation log is append-only: reset adds a marker, never truncates
    assessments = [assess(ac_id) for ac_id in STATE.aircraft]
    return DemoResetResponse(
        ok=True, state=f"demo-{date.today().isoformat()}", reset_at=now_utc(),
        counts=ResetCounts(ads=len(STATE.ads), aircraft=len(STATE.aircraft),
                           questions=sum(len(a.questions) for a in assessments),
                           decisions=0, proposals=0,  # ponytail: no decisions/proposals store yet
                           logbook_records=len(STATE.logbook)),
        not_loaded=sorted(set(STATE.available) - set(STATE.ads)),
        aircraft_status={a.aircraft.id: a.status for a in assessments})


def choose_source(golden_ad: LoadedAD) -> tuple[LoadedAD, str, ExtractionInfo, list[ValidatedField]]:
    """The extraction decides only when every quote is found and every compared field agrees with golden.
    Otherwise golden decides, and every miss is returned as a rejected field."""
    live = not llm.demo_mode()
    facts = extract.fact_vocabulary(STATE.available, STATE.logbook)
    try:
        record = extract.run(golden_ad, facts, live=live)
    except llm.LLMUnavailable as e:
        return golden_ad, "golden", ExtractionInfo(used=False, source=None, model=None, prompt_version=None,
                                                   agreement=None, reason=str(e), misses=[]), []
    used_source = "llm" if live and not record.get("fallback_reason") else "cache"
    r = extract.evaluate_record(record, golden_ad)
    base = {"source": used_source, "model": record.get("model"), "prompt_version": record.get("prompt_version")}
    if not r["ok"]:
        return golden_ad, "golden", ExtractionInfo(used=False, agreement=None, reason=r["error"], misses=[],
                                                   **base), []
    misses = [f"{name}: missing {f['missing']}; extra {f['extra']}" for name, f in r["fields"].items()
              if not f["agree"]] + [f"quote not found: {q}" for q in r["rejected"]]
    if not r["usable"]:
        rejected = [ValidatedField(field=name, value={"missing": f["missing"], "extra": f["extra"]}, quote="",
                                   file=golden_ad.file, occurrence=1, check="disagrees with golden")
                    for name, f in r["fields"].items() if not f["agree"]]
        log.warning("ingest %s: extraction not used (%d miss(es)); golden decides", golden_ad.ad_id, len(misses))
        return golden_ad, "golden", ExtractionInfo(used=False, agreement=r["agreement"], misses=misses,
                                                   reason="extraction disagrees with golden or a quote is not "
                                                          "in the text: golden decides", **base), rejected
    # Values from the extraction, citations (and every free text) from golden: the agent's quotes are verified but
    # may stop mid-sentence, so answers cite the human-checked sentence. The decided record hashes the cache file.
    extracted = extract.with_golden_quotes(extract.parse(record["raw"], golden_ad.ad_id), golden_ad.golden)
    ad = golden_ad.model_copy(update={"golden": extracted, "golden_file": extract.cache_ref(golden_ad.ad_id)})
    return ad, used_source, ExtractionInfo(
        used=True, agreement=r["agreement"], misses=[],
        reason="values from the extraction; citations from golden (human-checked)", **base), []


@app.post("/ads/{ad_id}/ingest", response_model=IngestResponse)
def ingest(ad_id: str) -> IngestResponse:
    """Pipeline run (not an action). The LLM extraction (demo mode: its cache) fills the AD's inputs when it is
    fully validated and agrees with golden; otherwise golden does. Idempotent: the AD id is the key."""
    if ad_id not in STATE.available:
        raise NotFound("AD_NOT_FOUND", f"No AD with id {ad_id} to ingest.", {"ad_id": ad_id})
    ad, source, extraction, misses = choose_source(STATE.available[ad_id])
    checks = store.field_checks(ad, store.ad_text(ad))
    validated = [c for c in checks if c.check == store.QUOTE_FOUND]
    rejected = [c for c in checks if c.check != store.QUOTE_FOUND]
    if rejected:
        log.warning("ingest %s: %d field(s) rejected, AD not loaded", ad_id, len(rejected))
    STATE.ingest_runs += 1
    before = statuses()
    newly = ad_id not in STATE.ads and not rejected
    if newly:
        STATE.ads[ad_id] = ad
    after = statuses()

    g = ad.golden
    path = [ReasoningStep(from_=ad_id, link="supersedes", to=old, derived=False, rule_id=rules.R_CHAIN,
                          note=(g.field_quotes.get("supersedes") or ["supersedes"])[0]) for old in g.supersedes]
    path += [ReasoningStep(from_=ad_id, link="revises", to=old, derived=False, rule_id=rules.R_CHAIN,
                           note=(g.field_quotes.get("revises") or ["revises"])[0]) for old in g.revises]
    if ad_id in STATE.ads:
        for ac_id in STATE.aircraft:
            res = assess(ac_id).results.get(ad_id)
            if res is not None and res.verdict == "applies":
                path += applies_path(STATE.aircraft[ac_id], ad_id, res)
    return IngestResponse(
        run_id=f"ING-{date.today().isoformat()}-{STATE.ingest_runs:03d}", ad_id=ad_id, source=source,
        validated_fields=validated, rejected_fields=rejected + misses, extraction=extraction,
        changes=IngestChanges(
            superseded=g.supersedes + g.revises if newly else [],
            aircraft_status_changed=[StatusChange(aircraft_id=k, from_=before[k], to=after[k])
                                     for k in before if before[k] != after[k]]),
        citations=list({c.quote: ad.cite(c.quote) for c in validated}.values()),
        reasoning_path=path)


def fleet_reason(a: rules.Assessment) -> str:
    """One line for the fleet board (template, no LLM)."""
    applies = [(k, r) for k, r in a.results.items() if r.verdict == "applies"]
    if a.status == "no_records":
        return rules.NO_RECORDS_REASON if applies else "No AD in the loaded set applies — no compliance records in this system"
    if a.status == "red":
        return "; ".join(f"AD {k} applies ({rules.group_label(r.row) if r.row and rules.group_label(r.row) else r.why})"
                         " and has no compliance record" for k, r in applies if k not in a.compliance)
    if a.status == "amber":
        q = rules.sort_questions(a.questions)
        line = f"Open question: {q[0].text} (AD {q[0].ad_id})"
        if q[0].days_left is not None and q[0].days_left <= rules.URGENCY_HIGH_DAYS:
            line += f" — ARC review in {q[0].days_left} days"
        return line + (f" (+{len(q) - 1} more)" if len(q) > 1 else "")
    return "All applicable ADs complied with or not applicable"


@app.get("/fleet", response_model=FleetResponse)
def fleet() -> FleetResponse:
    rows = []
    for ac_id in STATE.aircraft:
        a = assess(ac_id)
        rows.append(FleetAircraft(**a.aircraft.model_dump(), status=a.status, reason=fleet_reason(a),
                                  open_questions=len(a.questions)))
    return FleetResponse(aircraft=rows, computed_at=now_utc())


@app.get("/aircraft/{aircraft_id}/ads/{ad_id}/supersession", response_model=SupersessionResponse)
def supersession(aircraft_id: str, ad_id: str) -> SupersessionResponse:
    aircraft = get_aircraft(aircraft_id)
    if not rules.is_known_ad(ad_id, STATE.ads):
        raise NotFound("AD_NOT_FOUND", f"No AD with id {ad_id} in this system.", {"ad_id": ad_id})
    chain, problem = rules.supersession_chain(ad_id, STATE.ads)
    a = assess(aircraft_id)
    head = chain[-1].ad_id
    head_result = None if problem else a.results.get(head)
    records = {r.ad_id: r for r in STATE.logbook if r.aircraft_id == aircraft_id and r.kind == "compliance"}
    v = rules.still_valid(chain, problem, head_result, records, STATE.ads)

    links, path, citations = [], [], []
    for step in chain:
        loaded = STATE.ads.get(step.ad_id)
        links.append(ChainLink(ad_id=step.ad_id, status="superseded" if step.successor else "active",
                               superseded_by=step.successor, link=step.link,
                               effective_date=loaded.golden.effective_date if loaded else None))
    if head_result is not None and head_result.verdict == "applies":
        path += applies_path(aircraft, head, head_result)
        citations += head_result.citations
    for step in chain:
        if step.successor:
            new = STATE.ads[step.successor]
            quotes = new.golden.field_quotes.get(step.link or "", [])
            path.append(ReasoningStep(from_=new.ad_id, link=step.link or "supersedes", to=step.ad_id, derived=False,
                                      note=quotes[0] if quotes else step.link or "", rule_id=rules.R_CHAIN))
            citations += [new.cite(q) for q in quotes[:1]]
    rec = v.record
    if rec is not None:
        path.append(ReasoningStep(from_=rec.id, link="satisfies", to=rec.ad_id, derived=False,
                                  note=f"kept valid: {v.reason}" if v.credits else rec.text,
                                  rule_id=rules.R_CREDIT if v.credits else rules.R_COMPLIANCE_RECORD))
    citations += v.credits
    compliance = None if rec is None else ComplianceRecord(
        id=rec.id, ad_id=rec.ad_id, subject_id=rec.subject_id, date=rec.date, method=rec.text,
        evidence=f"logbook {rec.id} (synthetic)" if rec.synthetic else f"logbook {rec.id}",
        recorded_by=None, synthetic=rec.synthetic)
    inputs = evaluations.snapshot_inputs(aircraft, STATE.logbook, date.today(), decision_facts())
    return SupersessionResponse(
        aircraft_id=aircraft_id, asked_ad_id=ad_id, chain=links, compliance=compliance, still_valid=v.value,
        reason=v.reason, citations=list({c.model_dump_json(): c for c in citations}.values()), reasoning_path=path,
        rules_version=evaluations.rules_version(list(STATE.ads.values()))["id"],
        inputs_hash=evaluations.canonical_sha256(inputs))


def get_evaluation(evaluation_id: str) -> dict:
    if evaluation_id not in EVAL_LOG.records:
        raise NotFound("EVALUATION_NOT_FOUND", f"No evaluation with id {evaluation_id}.", {"id": evaluation_id})
    return EVAL_LOG.records[evaluation_id]


@app.get("/evaluations/{evaluation_id}", response_model=Evaluation)
def evaluation(evaluation_id: str) -> Evaluation:
    return Evaluation.model_validate(get_evaluation(evaluation_id))


@app.post("/evaluations/{evaluation_id}/replay", response_model=ReplayResponse)
def replay(evaluation_id: str) -> ReplayResponse:
    """Recompute from the recorded inputs with the current rules and active ADs."""
    record = get_evaluation(evaluation_id)
    try:
        r = EVAL_LOG.replay(record, list(STATE.ads.values()))
    except ValueError as e:  # recorded inputs no longer match their hash
        raise NotFound("INPUTS_HASH_MISMATCH", str(e), {"id": evaluation_id}, HTTP_CONFLICT) from e
    return ReplayResponse(
        evaluation_id=evaluation_id, same=r.same, before=DecisionSnapshot(**evaluations.decision_of_record(record)),
        after=DecisionSnapshot(**r.after), changed=ReplayChanges(**r.changed()),
        replay_evaluation_id=r.new_record["id"], inputs_hash=record["inputs_hash"], replayed_at=now_utc(),
        current=current_replay(record))


def current_replay(record: dict) -> CurrentReplay | None:
    """Same aircraft and date, today's logbook and decisions, current rules: names the decisions that changed it."""
    aircraft = STATE.aircraft.get(record["aircraft_id"])
    if aircraft is None:
        return None
    inputs = evaluations.snapshot_inputs(aircraft, STATE.logbook, date.fromisoformat(record["as_of_date"]),
                                         decision_facts())
    now = evaluations.decision_of(evaluations.decide(inputs, list(STATE.ads.values())))
    was = {f["id"] for f in record["inputs"].get("decisions", [])}
    is_ = {f["id"] for f in inputs.get("decisions", [])}
    return CurrentReplay(**now, inputs_changed=evaluations.canonical_sha256(inputs) != record["inputs_hash"],
                         decisions_added=sorted(is_ - was), decisions_removed=sorted(was - is_),
                         same_as_recorded=now == evaluations.decision_of_record(record))


@app.get("/decisions", response_model=DecisionsResponse)
def decisions(aircraft_id: str | None = None, ad_id: str | None = None) -> DecisionsResponse:
    """Human DECISION records (answered QUESTIONs). Empty after /demo/reset. Unknown aircraft_id → 404."""
    if aircraft_id is not None:
        get_aircraft(aircraft_id)
    return DecisionsResponse(decisions=[d for d in STATE.decisions if (aircraft_id is None or d.aircraft_id == aircraft_id)
                                        and (ad_id is None or d.ad_id == ad_id)])


def log_action(action: str, role: str, params: dict, objects: list[str], result: str,
               reason: str | None = None) -> ActionLogEntry:
    person = DEMO_PEOPLE.get(role)
    entry = ActionLogEntry(id=f"AL-{len(STATE.action_log) + 1:04d}", action=action,
                           actor={"id": person.id if person else None, "role": role}, at=now_utc(), params=params,
                           objects_edited=objects, result=result, reason=reason)
    STATE.action_log.append(entry)
    return entry


def refuse(question_id: str, aircraft_id: str, role: str, body: AnswerRequest, failed: list[str], reason: str):
    """Log the refused attempt (readable by the UI on GET /questions) and answer 403."""
    entry = log_action("AnswerQuestion", role, {"question_id": question_id, **body.model_dump()}, [], "refused", reason)
    STATE.refused.append(RefusedAttempt(id=entry.id, at=entry.at, action="AnswerQuestion", question_id=question_id,
                                        aircraft_id=aircraft_id, actor_role=role, failed_criteria=failed,
                                        reason=reason))
    raise NotFound("SUBMISSION_CRITERIA_FAILED", reason, {"action": "AnswerQuestion", "actor_role": role,
                   "failed_criteria": failed, "attempt_logged_as": entry.id}, HTTP_FORBIDDEN)


def find_question(question_id: str) -> tuple[rules.Assessment, Question] | None:
    for aircraft_id in STATE.aircraft:
        a = assess(aircraft_id)
        for q in a.questions:
            if q.id == question_id:
                return a, q
    return None


@app.post("/questions/{question_id}/answer", response_model=AnswerResponse)
def answer_question(question_id: str, body: AnswerRequest) -> AnswerResponse:
    """A certifying engineer answers an open QUESTION: a human DECISION that supplies the unknown fact.
    Refused (403, logged): any other role; any real aircraft (the demo's engineer is synthetic)."""
    found = find_question(question_id)
    if found is None:
        if any(d.question_id == question_id for d in STATE.decisions):
            raise NotFound("ALREADY_ANSWERED", f"Question {question_id} was already answered.",
                           {"question_id": question_id}, HTTP_CONFLICT)
        raise NotFound("QUESTION_NOT_FOUND", f"No open question with id {question_id}.", {"question_id": question_id})
    a, q = found
    role = body.answered_by_role
    if role != ANSWER_ROLE:
        refuse(question_id, q.aircraft_id, role, body, [f"role = {ANSWER_ROLE}"],
               f"A {role} cannot answer a QUESTION: a certifying engineer must decide.")
    if not a.aircraft.synthetic:
        refuse(question_id, q.aircraft_id, role, body, ["aircraft is synthetic (the demo's engineers are synthetic)"],
               REAL_AIRCRAFT_REASON)
    conditions = a.results[q.ad_id].unknown_conditions
    if len(conditions) != 1:
        raise NotFound("ANSWER_NOT_SUPPORTED", "Only questions about exactly one fact can be answered yet "
                       "(multi-fact and serial questions: not built yet).",
                       {"question_id": question_id, "unknown_facts": [c.fact for c in conditions]}, HTTP_UNPROCESSABLE)
    cond = conditions[0]
    positive = POSITIVE_VALUE[cond.kind]
    value = positive if body.answer == "yes" else OPPOSITE[positive]
    decision_id = f"D-{len(STATE.decisions) + 1:04d}"
    entry = log_action("AnswerQuestion", role, {"question_id": question_id, **body.model_dump()},
                       [decision_id, q.aircraft_id], "ok")
    person = DEMO_PEOPLE[ANSWER_ROLE]
    decision = DecisionRecord(
        id=decision_id, question_id=question_id, question=q.text, aircraft_id=q.aircraft_id, ad_id=q.ad_id,
        answer=body.answer, facts={cond.fact: value}, rationale=body.note, evidence=[body.note], made_by=person,
        made_at=entry.at, action_log_id=entry.id, synthetic=True, citations=q.citations,
        reasoning_path=[
            ReasoningStep(from_=decision_id, link="madeBy", to=person.id, derived=False,
                          note=f"role {person.role} (synthetic)", rule_id=rules.R_DECISION_ANSWER),
            ReasoningStep(from_=decision_id, link="justifiedBy", to=q.ad_id, derived=False,
                          note=f"answers {question_id}: {cond.fact} = {value}", rule_id=rules.R_DECISION_ANSWER)])
    STATE.decisions.append(decision)
    after = assess(q.aircraft_id).status
    return AnswerResponse(decision=decision, action_log=entry,
                          aircraft_status=StatusChange(aircraft_id=q.aircraft_id, from_=a.status, to=after))


@app.get("/questions", response_model=QuestionsResponse)
def questions(aircraft_id: str | None = None) -> QuestionsResponse:
    """Unknown aircraft_id → 404 (contract rule 2: never a 200 with empty data for a missing object)."""
    ids = [get_aircraft(aircraft_id).id] if aircraft_id is not None else list(STATE.aircraft)
    found = [q for ac_id in ids for q in assess(ac_id).questions]
    refused = [r for r in STATE.refused if aircraft_id is None or r.aircraft_id == aircraft_id]
    return QuestionsResponse(questions=rules.sort_questions(found), urgency_rule=rules.URGENCY_RULE,
                             refused_attempts=refused)


def ad_extraction(golden_ad: LoadedAD) -> AdExtraction:
    """The agent's cached extraction for this AD, compared with golden. Read-only: never calls the LLM."""
    active = STATE.ads.get(golden_ad.ad_id)
    decided_by = ("not_loaded" if active is None
                  else "extraction" if active.golden_file == extract.cache_ref(golden_ad.ad_id) else "golden")
    try:
        record = extract.run(golden_ad, [], live=False)
    except llm.LLMUnavailable as e:
        return AdExtraction(source=None, model=None, prompt_version=None, agreement=None, quotes_found=None,
                            quotes_checked=None, usable=False, decided_by=decided_by, reason=str(e), misses=[])
    r = extract.evaluate_record(record, golden_ad)
    base = {"source": "cache", "model": record.get("model"), "prompt_version": record.get("prompt_version"),
            "decided_by": decided_by}
    if not r["ok"]:
        return AdExtraction(agreement=None, quotes_found=None, quotes_checked=None, usable=False, reason=r["error"],
                            misses=[], **base)
    misses = [ExtractionMiss(field=name, agent_proposed=f["extra"], golden=f["missing"])
              for name, f in r["fields"].items() if not f["agree"]]
    misses += [ExtractionMiss(field="quote", agent_proposed=[q], golden=[]) for q in r["rejected"]]
    return AdExtraction(agreement=r["agreement"], quotes_found=r["quotes_checked"] - r["quotes_rejected"],
                        quotes_checked=r["quotes_checked"], usable=r["usable"], misses=misses,
                        reason=None if r["usable"] else "extraction disagrees with golden: golden decides", **base)


@app.get("/ads/{ad_id}", response_model=AdDetailResponse)
def ad_detail(ad_id: str) -> AdDetailResponse:
    """Metadata, relations, full text and every golden field with its citation, plus the agent's extraction.
    Works for every golden AD, loaded or not yet ingested (`loaded`)."""
    if ad_id not in STATE.available:
        raise NotFound("AD_NOT_FOUND", f"No AD with id {ad_id} in this system.", {"ad_id": ad_id})
    ad = STATE.available[ad_id]
    g = ad.golden
    applicability = [ApplicabilityGroup(model=r.model, series=r.series, serial_from=r.serial_from,
                                        serial_to=r.serial_to, group=rules.group_label(r), citation=ad.cite(r.quote))
                     for r in g.applicability]
    conditions = [ConditionOut(kind=c.kind, fact=c.fact, applies_when=c.applies_when, value=c.value,
                               citation=ad.cite(c.quote)) for c in g.conditions]
    not_evaluated = [NotEvaluatedOut(clause=n.clause, note=rules.NOT_EVALUATED_NOTE.format(clause=n.clause),
                                     citation=ad.cite(n.quote)) for n in g.not_evaluated]
    credits = [CreditOut(ad_id=c.ad_id, paragraph=c.paragraph, citation=ad.cite(c.quote, c.occurrence))
               for c in g.credited_compliance]
    citations = [x.citation for x in [*applicability, *conditions, *not_evaluated, *credits]]
    citations += [ad.cite(q) for key in ("effective_date", "supersedes", "revises", "compliance_time_text")
                  for q in g.field_quotes.get(key, [])]
    return AdDetailResponse(
        ad=ad_object(ad), text=store.ad_text(ad),
        citations=list({(c.quote, c.occurrence): c for c in citations}.values()), loaded=ad_id in STATE.ads,
        applicability=applicability, conditions=conditions, not_evaluated=not_evaluated,
        credited_compliance=credits, extraction=ad_extraction(ad))


@app.post("/compare")
def compare() -> JSONResponse:
    return example("compare")


@app.post("/actions/{action_type}")
def action(action_type: str) -> JSONResponse:
    # ponytail: v0 fake — ProposeAction → 202, anything else → the 403 rejection example.
    return example("action-proposed" if action_type == "ProposeAction" else "action-rejected")


@app.get("/proposals")
def proposals(status: str | None = None) -> dict:
    # No example file in the contract: minimal shape, flagged for Surface.
    return {"proposals": []}


@app.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: str) -> JSONResponse:
    return example("action-approved")


@app.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str) -> dict:
    # No example file in the contract: minimal shape, flagged for Surface.
    return {"proposal_id": proposal_id, "status": "REJECTED"}
