"""GET /fleet and GET /questions from the store."""
import json

import pytest
from fastapi.testclient import TestClient

from app import rules
from app.api import EXAMPLES_DIR, app
from app.ontology import Question

client = TestClient(app)
INGEST_2012_02_02 = "/ads/FAA%3A2012-02-02/ingest"


@pytest.fixture(autouse=True)
def demo_state():
    assert client.post("/demo/reset").status_code == 200


def fleet() -> dict:
    r = client.get("/fleet")
    assert r.status_code == 200
    return {a["id"]: a for a in r.json()["aircraft"]}


def test_fleet_demo_state():
    f = fleet()
    assert {k: v["status"] for k, v in f.items()} == {
        "DEMO-01": "green", "DEMO-02": "green", "DEMO-03": "green", "DEMO-04": "amber", "DEMO-05": "green",
        "EI-GKN": "no_records", "EI-HAS": "no_records", "EI-GWY": "no_records"}
    assert f["DEMO-04"]["open_questions"] == 1
    assert f["DEMO-04"]["reason"].startswith(
        "Open question: Is MOD2008/233 or SB-826-CS embodied on DEMO-04? (AD EASA:2024-0152R1)")
    assert f["DEMO-02"]["reason"] == "All applicable ADs complied with or not applicable"
    assert f["EI-HAS"]["reason"] == "No AD in the loaded set applies — no compliance records in this system"
    assert f["EI-GWY"]["open_questions"] == 1 and f["EI-GWY"]["status"] == "no_records"


def test_fleet_after_ingest_matches_contract_reason():
    client.post(INGEST_2012_02_02)
    f = fleet()
    ex = json.loads((EXAMPLES_DIR / "fleet.json").read_text(encoding="utf-8"))["response"]["body"]
    [ex01] = [a for a in ex["aircraft"] if a["id"] == "DEMO-01"]
    assert f["DEMO-01"]["status"] == "red" and f["DEMO-01"]["reason"] == ex01["reason"]
    assert f["EI-GKN"]["reason"] == rules.NO_RECORDS_REASON


def test_fleet_never_red_for_real_aircraft():
    client.post(INGEST_2012_02_02)
    assert all(a["status"] == "no_records" for a in fleet().values() if not a["synthetic"])


def test_questions_sorted_and_rule_matches_contract():
    b = client.get("/questions").json()
    ex = json.loads((EXAMPLES_DIR / "q5-questions.json").read_text(encoding="utf-8"))["response"]["body"]
    assert b["urgency_rule"] == ex["urgency_rule"]
    assert [(q["aircraft_id"], q["urgency"]) for q in b["questions"]] == [("DEMO-04", "high"), ("EI-GWY", None)]


def test_questions_filter_by_aircraft():
    assert [q["ad_id"] for q in client.get("/questions?aircraft_id=DEMO-04").json()["questions"]] == \
        ["EASA:2024-0152R1"]
    assert client.get("/questions?aircraft_id=DEMO-01").json()["questions"] == []


@pytest.mark.parametrize("ac", ["EI-XXX", "", "demo-04"])
def test_questions_unknown_aircraft_404(ac):
    r = client.get(f"/questions?aircraft_id={ac}")
    assert r.status_code == 404 and r.json()["error_code"] == "AIRCRAFT_NOT_FOUND"


def q(id_: str, urgency, days) -> Question:
    return Question(id=id_, text="t", aircraft_id="A", ad_id="FAA:1", blocks="b", deadline=None,
                    deadline_driver=None, days_left=days, urgency=urgency, synthetic=True, citations=[])


def test_sort_questions():
    qs = [q("none", None, None), q("low", "low", 200), q("high10", "high", 10), q("over", "overdue", -3),
          q("med", "medium", 60), q("high5b", "high", 5), q("high5a", "high", 5)]
    assert [x.id for x in rules.sort_questions(qs)] == ["over", "high5a", "high5b", "high10", "med", "low", "none"]
    assert rules.sort_questions([]) == []
