"""One endpoint per business question (contract/README.md, "Endpoints"). v0: fakes from contract/examples/."""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

REPO = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO / "contract" / "examples"
DEMO_MODE = True

app = FastAPI(title="AD Brain core")


def example(name: str) -> JSONResponse:
    """The response of contract/examples/<name>.json, with its HTTP status."""
    resp = json.loads((EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))["response"]
    return JSONResponse(resp["body"], status_code=resp["http_status"])


@app.get("/health")
def health() -> dict:
    return {"ok": True, "demo_mode": DEMO_MODE}


@app.post("/demo/reset")
def demo_reset() -> JSONResponse:
    return example("demo-reset")


@app.get("/fleet")
def fleet() -> JSONResponse:
    return example("fleet")


@app.get("/aircraft/{aircraft_id}/status")
def aircraft_status(aircraft_id: str) -> JSONResponse:
    return example("q1-aircraft-status")


@app.get("/ads/{ad_id}/affected-aircraft")
def affected_aircraft(ad_id: str) -> JSONResponse:
    return example("q2-affected-aircraft")


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
