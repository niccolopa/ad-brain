"""One endpoint per business question (contract/README.md, "Endpoints").
Real: Q1 status, Q2 affected-aircraft. The rest still serve contract/examples/ (fakes)."""
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import rules, store
from app.ontology import (
    AffectedAircraft,
    AffectedAircraftResponse,
    Aircraft,
    AircraftStatusResponse,
    AirworthinessDirective,
    ApplicableAD,
    ComplianceState,
    Due,
    Error,
    LoadedAD,
    NotAffected,
    ReasoningStep,
)

log = logging.getLogger("adbrain.api")

REPO = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO / "contract" / "examples"
DEMO_MODE = True

app = FastAPI(title="AD Brain core")
STATE = store.load()


class NotFound(Exception):
    def __init__(self, error_code: str, message: str, details: dict) -> None:
        self.error = Error(error_code=error_code, message=message, details=details)


@app.exception_handler(NotFound)
def not_found(_: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse(exc.error.model_dump(), status_code=404)


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


def assess(aircraft_id: str) -> rules.Assessment:
    return rules.assess(get_aircraft(aircraft_id), list(STATE.ads.values()), STATE.logbook, date.today())


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
    a = assess(aircraft_id)
    applicable, path = [], []
    for ad_id, res in a.results.items():
        if res.verdict != "applies":
            continue
        ad, rec = STATE.ads[ad_id], a.compliance.get(ad_id)
        applicable.append(ApplicableAD(
            ad_id=ad_id, title=ad.title, status=ad_object(ad).status, applies_because=res.why,
            compliance=ComplianceState(state="complied" if rec else "no_record", record_id=rec.id if rec else None),
            due=Due(text=ad.golden.compliance_time_text, citation=rules.due_citation(ad, res.row),
                    overdue=(rec is None) if a.aircraft.synthetic else None),
            citations=res.citations))
        note = res.why + (f"; complied {rec.id}" if rec else "; no compliance record")
        path.append(ReasoningStep(from_=ad_id, link="appliesTo", to=a.aircraft.id, derived=False, note=note))
        if rec:
            path.append(ReasoningStep(from_=rec.id, link="satisfies", to=ad_id, derived=False, note=rec.text))
    citations = [c for x in applicable for c in x.citations + ([x.due.citation] if x.due.citation else [])]
    citations += [c for q in a.questions for c in q.citations]
    return AircraftStatusResponse(
        aircraft=a.aircraft, status=a.status, summary=summary(a, applicable), summary_source="template",
        applicable_ads=applicable, superseded_ads=[], open_questions=a.questions, hypotheses=[],
        citations=list({c.model_dump_json(): c for c in citations}.values()),  # dedupe, keep order
        reasoning_path=path, computed_at=now_utc())


@app.get("/ads/{ad_id}/affected-aircraft", response_model=AffectedAircraftResponse)
def affected_aircraft(ad_id: str) -> AffectedAircraftResponse:
    ad = get_ad(ad_id)
    affected, not_affected, questions, path, citations = [], [], [], [], []
    for ac in STATE.aircraft.values():
        a = assess(ac.id)
        res = a.results[ad_id]
        if res.verdict == "applies":
            all_serials = res.row is not None and res.row.serial_from is None and res.row.serial_to is None
            affected.append(AffectedAircraft(aircraft_id=ac.id, model=ac.model, serial=ac.serial,
                                             via="all_serials" if all_serials else "serial_range",
                                             why=res.why, status_now=a.status))
            path.append(ReasoningStep(from_=ad_id, link="appliesTo", to=ac.id, derived=False, note=res.why))
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


@app.post("/demo/reset")
def demo_reset() -> JSONResponse:
    global STATE
    STATE = store.load()
    return example("demo-reset")  # body still the example; real counts in v2


@app.get("/fleet")
def fleet() -> JSONResponse:
    return example("fleet")


@app.post("/ads/{ad_id}/ingest")
def ingest(ad_id: str) -> JSONResponse:
    return example("q2-ingest")


@app.get("/aircraft/{aircraft_id}/ads/{ad_id}/supersession")
def supersession(aircraft_id: str, ad_id: str) -> JSONResponse:
    return example("q3-supersession")


@app.get("/decisions")
def decisions(aircraft_id: str | None = None, ad_id: str | None = None) -> JSONResponse:
    return example("q4-decisions")


@app.get("/questions")
def questions(aircraft_id: str | None = None) -> JSONResponse:
    return example("q5-questions")


@app.get("/ads/{ad_id}")
def ad_detail(ad_id: str) -> JSONResponse:
    return example("ad-detail")


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
