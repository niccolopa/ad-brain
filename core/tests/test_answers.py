"""Answering a QUESTION: a certifying engineer's DECISION supplies the unknown fact; refusals are logged and
readable; replay names the decision that changed the result. Real golden ADs and the real demo fleet."""
import json

import pytest
from fastapi.testclient import TestClient

from app import api, store
from app.api import EXAMPLES_DIR, app

client = TestClient(app)
ECI_Q = "Q-DEMO-03-FAA:2006-12-07"
MOD_Q = "Q-DEMO-04-EASA:2024-0152R1"
REAL_Q = "Q-EI-GKN-FAA:2012-19-01"
NOTE = "Engine logbook 2015-04-02 (synthetic): cylinders are Lycoming originals, not ECi AEL65102."


@pytest.fixture(autouse=True)
def demo_state():
    assert client.post("/demo/reset").status_code == 200
    yield
    client.post("/demo/reset")


def answer(question_id: str, answer: str = "no", role: str = "certifying_engineer", note: str = NOTE):
    return client.post(f"/questions/{question_id.replace(':', '%3A')}/answer",
                       json={"answer": answer, "answered_by_role": role, "note": note})


def status(aircraft_id: str) -> dict:
    return client.get(f"/aircraft/{aircraft_id}/status").json()


# ---------- the demo case ----------
def test_demo03_eci_answered_no_turns_green_and_replay_names_the_decision():
    before = status("DEMO-03")
    assert before["status"] == "amber" and [q["id"] for q in before["open_questions"]] == [ECI_Q]
    r = answer(ECI_Q, "no")
    assert r.status_code == 200, r.text
    b = r.json()
    d = b["decision"]
    assert d["id"] == "D-0001" and d["epistemic_class"] == "DECISION" and d["synthetic"] is True
    assert d["facts"] == {"ECi_AEL65102_cylinders_installed": "no"} and d["rationale"] == NOTE
    assert d["made_by"] == {"id": "P-CE-1", "name": "Certifying Engineer 1 (synthetic)",
                            "role": "certifying_engineer", "synthetic": True}
    assert [s["link"] for s in d["reasoning_path"]] == ["madeBy", "justifiedBy"]
    assert all(s["rule_id"] == "R-DECISION-ANSWER" for s in d["reasoning_path"]) and d["citations"]
    assert b["aircraft_status"] == {"aircraft_id": "DEMO-03", "from": "amber", "to": "green"}
    assert b["action_log"]["result"] == "ok" and b["action_log"]["objects_edited"] == ["D-0001", "DEMO-03"]

    after = status("DEMO-03")
    assert after["status"] == "green" and after["open_questions"] == []
    assert after["evaluation_id"] != before["evaluation_id"] and after["inputs_hash"] != before["inputs_hash"]
    ev = client.get(f"/evaluations/{after['evaluation_id']}").json()
    assert "R-DECISION-ANSWER" in ev["rule_ids_fired"] and ev["inputs"]["decisions"][0]["id"] == "D-0001"

    rp = client.post(f"/evaluations/{before['evaluation_id']}/replay").json()
    assert rp["same"] is True  # same recorded inputs → same decision
    assert rp["current"] == {"status": "green", "verdicts": rp["current"]["verdicts"], "inputs_changed": True,
                             "decisions_added": ["D-0001"], "decisions_removed": [], "same_as_recorded": False}
    assert rp["current"]["verdicts"]["FAA:2006-12-07"] == "not_applicable"


def test_answer_yes_makes_the_ad_apply_and_names_the_decision():
    b = answer(ECI_Q, "yes").json()
    assert b["decision"]["facts"] == {"ECi_AEL65102_cylinders_installed": "yes"}
    assert b["aircraft_status"]["to"] == "red"  # applies, no compliance record
    [eci] = [x for x in status("DEMO-03")["applicable_ads"] if x["ad_id"] == "FAA:2006-12-07"]
    assert "(D-0001)" in eci["applies_because"]


def test_decisions_endpoint_returns_real_records_and_filters():
    assert client.get("/decisions").json() == {"decisions": []}  # the contract example is gone
    answer(ECI_Q)
    assert [d["id"] for d in client.get("/decisions").json()["decisions"]] == ["D-0001"]
    assert [d["id"] for d in client.get("/decisions?aircraft_id=DEMO-03").json()["decisions"]] == ["D-0001"]
    assert client.get("/decisions?aircraft_id=DEMO-04").json()["decisions"] == []
    assert client.get("/decisions?ad_id=EASA%3A2018-0072").json()["decisions"] == []
    r = client.get("/decisions?aircraft_id=EI-XXX")
    assert r.status_code == 404 and r.json()["error_code"] == "AIRCRAFT_NOT_FOUND"


def test_contract_example_shape_still_holds():
    ex = json.loads((EXAMPLES_DIR / "q4-decisions.json").read_text(encoding="utf-8"))["response"]["body"]
    answer(ECI_Q)
    assert set(client.get("/decisions").json()) == set(ex)


def test_reset_clears_answers():
    answer(ECI_Q)
    client.post("/demo/reset")
    assert client.get("/decisions").json()["decisions"] == [] and status("DEMO-03")["status"] == "amber"
    assert client.get("/questions").json()["refused_attempts"] == []


# ---------- refusals: 403, logged, readable on GET /questions ----------
@pytest.mark.parametrize("role", ["mechanic", "agent", "pilot"])
def test_other_roles_are_refused_and_logged(role):
    r = answer(ECI_Q, role=role)
    assert r.status_code == 403 and r.json()["error_code"] == "SUBMISSION_CRITERIA_FAILED"
    assert r.json()["details"]["failed_criteria"] == ["role = certifying_engineer"]
    attempt = r.json()["details"]["attempt_logged_as"]
    [ref] = client.get("/questions").json()["refused_attempts"]
    assert ref["id"] == attempt and ref["actor_role"] == role and ref["question_id"] == ECI_Q
    assert api.STATE.action_log[-1].result == "refused" and api.STATE.decisions == []
    assert status("DEMO-03")["status"] == "amber"  # nothing changed


def test_real_aircraft_question_cannot_be_answered_by_a_synthetic_engineer():
    assert any(q["id"] == REAL_Q for q in client.get("/questions?aircraft_id=EI-GKN").json()["questions"])
    r = answer(REAL_Q, "no")
    assert r.status_code == 403 and r.json()["message"] == "real aircraft: needs a real certifying engineer"
    assert api.STATE.decisions == []  # never a decision about a real registered aircraft
    refused = client.get("/questions?aircraft_id=EI-GKN").json()["refused_attempts"]
    assert [x["reason"] for x in refused] == ["real aircraft: needs a real certifying engineer"]
    assert client.get("/questions?aircraft_id=DEMO-03").json()["refused_attempts"] == []
    assert status("EI-GKN")["status"] == "no_records"


# ---------- validation and unsupported questions ----------
def test_answer_twice_is_409():
    answer(ECI_Q)
    r = answer(ECI_Q)
    assert r.status_code == 409 and r.json()["error_code"] == "ALREADY_ANSWERED"


def test_multi_fact_question_is_not_supported_yet():
    r = answer(MOD_Q, "no")
    assert r.status_code == 422 and r.json()["error_code"] == "ANSWER_NOT_SUPPORTED"
    assert r.json()["details"]["unknown_facts"] == ["MOD2008_233", "SB_826_CS"] and api.STATE.decisions == []


@pytest.mark.parametrize("qid", ["Q-NOPE", "Q-DEMO-01-FAA:2006-12-07", ""])
def test_unknown_question_404(qid):
    if not qid:
        assert client.post("/questions//answer", json={}).status_code in (404, 405)
        return
    r = answer(qid)
    assert r.status_code == 404 and r.json()["error_code"] == "QUESTION_NOT_FOUND"


@pytest.mark.parametrize("body", [
    {"answer": "maybe", "answered_by_role": "certifying_engineer", "note": NOTE},
    {"answer": "no", "answered_by_role": "certifying_engineer", "note": "   "},
    {"answer": "no", "answered_by_role": "certifying_engineer"},
    {"answer": "no", "answered_by_role": "", "note": NOTE},
    {},
])
def test_malformed_body_is_422_in_our_error_shape(body):
    r = client.post(f"/questions/{ECI_Q.replace(':', '%3A')}/answer", json=body)
    assert r.status_code == 422 and r.json()["error_code"] == "VALIDATION_ERROR" and api.STATE.decisions == []


def test_decision_fact_contradicting_an_observation_becomes_a_question():
    # DEMO-01 observed ECi cylinders "no" (OB-DEMO01-ENG-3); a decision saying "yes" must not overwrite it
    from datetime import date

    from app import rules
    from app.ontology import Fact
    state = store.load()
    a = rules.assess(state.aircraft["DEMO-01"], list(state.ads.values()), state.logbook, date(2026, 11, 14),
                     [Fact(id="D-T", aircraft_id="DEMO-01", fact="ECi_AEL65102_cylinders_installed", value="yes")])
    assert a.results["FAA:2006-12-07"].verdict == "unknown"
    assert "R-CONTRADICTION-TO-QUESTION" in a.rule_ids and "R-DECISION-ANSWER" in a.rule_ids
