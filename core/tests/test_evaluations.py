"""Evaluation records and replay: same input → same decision; a changed rule version changes it and says which."""
import json
import logging
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import api, evaluations, rules, store
from app.api import app

client = TestClient(app)
STATE = store.load()
TODAY = date(2026, 11, 14)
INGEST_2012_02_02 = "/ads/FAA%3A2012-02-02/ingest"


@pytest.fixture(autouse=True)
def demo_state():
    assert client.post("/demo/reset").status_code == 200


def status(aircraft_id: str) -> dict:
    r = client.get(f"/aircraft/{aircraft_id}/status")
    assert r.status_code == 200
    return r.json()


# ---------- hashes ----------
def test_file_hash_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / "lf.txt", tmp_path / "crlf.txt"
    lf.write_bytes(b"a\nb\n")
    crlf.write_bytes(b"a\r\nb\r\n")
    assert evaluations.file_sha256(lf) == evaluations.file_sha256(crlf)
    crlf.write_bytes(b"a\r\nc\r\n")
    assert evaluations.file_sha256(lf) != evaluations.file_sha256(crlf)


def test_rules_version_names_every_ad_and_changes_with_the_set():
    ads = list(STATE.ads.values())
    v = evaluations.rules_version(ads)
    assert v == evaluations.rules_version(ads)
    assert [a["ad_id"] for a in v["ads"]] == sorted(STATE.ads)
    assert "FAA:2012-02-02" not in {a["ad_id"] for a in v["ads"]}  # not loaded at reset
    assert evaluations.rules_version(list(STATE.available.values()))["id"] != v["id"]


def test_rules_version_changes_when_a_golden_file_changes(tmp_path):
    ad = STATE.ads["EASA:2018-0072"]
    copy = tmp_path / "EASA-2018-0072.json"
    copy.write_text(evaluations.golden_path(ad).read_text(encoding="utf-8").replace("1085", "1086"), encoding="utf-8")
    v1 = evaluations.rules_version([ad])
    v2 = evaluations.rules_version([ad.model_copy(update={"golden_file": str(copy)})])
    assert v1["id"] != v2["id"] and v1["rules_py"] == v2["rules_py"]


def test_inputs_hash_covers_aircraft_logbook_and_date():
    ac = STATE.aircraft["DEMO-04"]
    base = evaluations.snapshot_inputs(ac, STATE.logbook, TODAY)
    h = evaluations.canonical_sha256
    assert h(base) == h(evaluations.snapshot_inputs(ac, list(reversed(STATE.logbook)), TODAY))  # order-free
    assert h(base) != h(evaluations.snapshot_inputs(ac, STATE.logbook, date(2026, 11, 15)))  # urgency is dated
    fewer = [r for r in STATE.logbook if r.id != "CR-DEMO04-AF-1"]
    assert h(base) != h(evaluations.snapshot_inputs(ac, fewer, TODAY))
    assert all(r["aircraft_id"] == "DEMO-04" for r in base["logbook"])


# ---------- the demo case: DEMO-01 before and after the 2012-02-02 ingest ----------
def test_demo01_replay_before_and_after_ingest():
    q1 = status("DEMO-01")
    ev_id = q1["evaluation_id"]
    assert q1["status"] == "green" and ev_id.startswith("EV-") and q1["rules_version"] and q1["inputs_hash"]
    ev = client.get(f"/evaluations/{ev_id}").json()
    assert ev["kind"] == "computed" and ev["status"] == "green" and ev["rule_ids_fired"][-1] == "R-STATUS-GREEN"
    assert ev["rules_version"]["id"] == q1["rules_version"]

    same = client.post(f"/evaluations/{ev_id}/replay").json()
    assert same["same"] is True and same["changed"]["rules_version"] is False
    assert same["replay_evaluation_id"] == ev_id  # same version + same inputs: nothing new appended

    client.post(INGEST_2012_02_02)
    diff = client.post(f"/evaluations/{ev_id}/replay").json()
    assert diff["same"] is False
    assert (diff["before"]["status"], diff["after"]["status"]) == ("green", "red")
    assert diff["after"]["verdicts"]["FAA:2012-02-02"] == "applies"
    assert diff["changed"] == {"rules_version": True, "rules_py": False, "ads_added": ["FAA:2012-02-02"],
                               "ads_removed": [], "ads_changed": []}
    new = client.get(f"/evaluations/{diff['replay_evaluation_id']}").json()
    assert new["replay_of"] == ev_id and new["status"] == "red" and new["inputs_hash"] == ev["inputs_hash"]

    client.post("/demo/reset")
    back = client.post(f"/evaluations/{ev_id}/replay").json()
    assert back["same"] is True and back["after"]["status"] == "green"


def test_polling_does_not_flood_the_log():
    ids = {status("DEMO-02")["evaluation_id"] for _ in range(3)}
    assert len(ids) == 1 and len(api.EVAL_LOG.records) == 1


def test_real_aircraft_evaluation_is_no_records():
    ev = client.get(f"/evaluations/{status('EI-GKN')['evaluation_id']}").json()
    assert ev["status"] == "no_records" and ev["rule_ids_fired"][-1] == "R-REAL-NO-RECORDS"


def test_changed_rules_py_is_reported(tmp_path, monkeypatch):
    ev_id = status("DEMO-04")["evaluation_id"]
    fake = tmp_path / "rules.py"
    fake.write_text(evaluations.RULES_PY.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    monkeypatch.setattr(evaluations, "RULES_PY", fake)
    r = client.post(f"/evaluations/{ev_id}/replay").json()
    assert r["changed"]["rules_py"] is True and r["changed"]["rules_version"] is True
    assert r["same"] is True  # the decision itself did not change (the code is the same)


@pytest.mark.parametrize("path,method", [("/evaluations/EV-9999", "GET"), ("/evaluations/EV-9999/replay", "POST"),
                                         ("/evaluations/D-DEMO05-1", "GET"), ("/evaluations/", "GET")])
def test_unknown_evaluation_404(path, method):
    r = client.request(method, path)
    assert r.status_code == 404
    if path != "/evaluations/":
        assert r.json()["error_code"] == "EVALUATION_NOT_FOUND"


def test_tampered_inputs_are_refused():
    ev_id = status("DEMO-01")["evaluation_id"]
    api.EVAL_LOG.records[ev_id]["inputs"]["logbook"] = []
    r = client.post(f"/evaluations/{ev_id}/replay")
    assert r.status_code == 409 and r.json()["error_code"] == "INPUTS_HASH_MISMATCH"


# ---------- append-only log on disk ----------
def test_log_is_append_only_and_survives_a_restart(tmp_path):
    path = tmp_path / "evaluations.jsonl"
    log1 = evaluations.EvaluationLog(path)
    ac = STATE.aircraft["DEMO-03"]
    inputs = evaluations.snapshot_inputs(ac, STATE.logbook, TODAY)
    ads = list(STATE.ads.values())
    a = evaluations.decide(inputs, ads)
    first = log1.record(a, inputs, ads)
    size = path.stat().st_size
    log1.mark_reset()
    assert path.stat().st_size > size  # a reset appends, never truncates
    log1.record(a, inputs, ads)  # duplicate: not written again
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["evaluation", "reset"]

    log2 = evaluations.EvaluationLog(path)  # restart
    assert log2.records[first["id"]]["status"] == "amber"
    other = evaluations.snapshot_inputs(STATE.aircraft["DEMO-05"], STATE.logbook, TODAY)
    assert log2.record(evaluations.decide(other, ads), other, ads)["id"] == "EV-0002"  # ids keep counting


def test_malformed_log_line_is_logged_not_fatal(tmp_path, caplog):
    path = tmp_path / "evaluations.jsonl"
    path.write_text("{not json\n\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="adbrain.evaluations"):
        log = evaluations.EvaluationLog(path)
    assert log.records == {} and "not JSON" in caplog.text


def test_same_inputs_same_decision_pure():
    inputs = evaluations.snapshot_inputs(STATE.aircraft["DEMO-04"], STATE.logbook, TODAY)
    ads = list(STATE.ads.values())
    d1, d2 = (evaluations.decision_of(evaluations.decide(inputs, ads)) for _ in range(2))
    assert d1 == d2 and d1["status"] == "amber"
    assert rules.STATUS_RULE[d1["status"]] == "R-STATUS-AMBER"
