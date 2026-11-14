"""Q1 and Q2 over HTTP: real answers, 404s, real aircraft never red."""
import json

import pytest
from fastapi.testclient import TestClient

from app import api, store
from app.api import EXAMPLES_DIR, app

client = TestClient(app)
INGEST_2012_02_02 = "/ads/FAA%3A2012-02-02/ingest"


@pytest.fixture(autouse=True)
def demo_state():
    assert client.post("/demo/reset").status_code == 200


def test_unknown_aircraft_matches_error_example():
    ex = json.loads((EXAMPLES_DIR / "error-not-found.json").read_text(encoding="utf-8"))["response"]
    r = client.get("/aircraft/EI-XXX/status")
    assert r.status_code == 404 and r.json() == ex["body"]


@pytest.mark.parametrize("path", ["/aircraft/%20/status", "/aircraft/demo-01/status"])
def test_unknown_aircraft_variants_404(path):
    r = client.get(path)
    assert r.status_code == 404 and r.json()["error_code"] == "AIRCRAFT_NOT_FOUND"


@pytest.mark.parametrize("ad", ["FAA%3A9999-99-99", "2012-02-02", "EASA%3A2012-02-02", "faa%3A2012-02-02"])
def test_unknown_ad_404(ad):
    r = client.get(f"/ads/{ad}/affected-aircraft")
    assert r.status_code == 404 and r.json()["error_code"] == "AD_NOT_FOUND"


def test_q1_demo01_green_before_ingest():
    b = client.get("/aircraft/DEMO-01/status").json()
    assert b["status"] == "green" and b["applicable_ads"] == []


def test_q1_demo01_red_group4():
    client.post(INGEST_2012_02_02)
    b = client.get("/aircraft/DEMO-01/status").json()
    assert b["status"] == "red"
    [ad] = b["applicable_ads"]
    assert ad["ad_id"] == "FAA:2012-02-02" and ad["compliance"] == {"state": "no_record", "record_id": None}
    assert ad["applies_because"] == "S/N 172S10600 is within 172S10490–172S11073 (Group 4)"
    assert ad["citations"][0]["quote"] == "Group 4: Model 172S, S/N 172S10490 through 172S11073"
    assert ad["due"]["citation"]["quote"].startswith("(2) For Group 3 and Group 4 Airplanes:")
    assert ad["due"]["overdue"] is True
    assert b["reasoning_path"][0] == {"from": "FAA:2012-02-02", "link": "appliesTo", "to": "DEMO-01",
                                      "derived": False, "note": ad["applies_because"] + "; no compliance record"}


def test_q1_demo04_amber_with_question():
    b = client.get("/aircraft/DEMO-04/status").json()
    assert b["status"] == "amber"
    assert [q["text"] for q in b["open_questions"]] == ["Is MOD2008/233 or SB-826-CS embodied on DEMO-04?"]
    assert b["applicable_ads"][0]["compliance"]["record_id"] == "CR-DEMO04-AF-1"


@pytest.mark.parametrize("reg", ["EI-GKN", "EI-HAS", "EI-GWY"])
def test_q1_real_aircraft_never_red(reg):
    b = client.get(f"/aircraft/{reg}/status").json()
    assert b["status"] == "no_records" and not b["aircraft"]["synthetic"]
    assert all(ad["due"]["overdue"] is None for ad in b["applicable_ads"])


def test_q1_real_aircraft_reason():
    client.post(INGEST_2012_02_02)
    assert "AD applies — no compliance records in this system" in client.get("/aircraft/EI-GKN/status").json()["summary"]


def test_q2_easa_2018_0072():
    b = client.get("/ads/EASA%3A2018-0072/affected-aircraft").json()
    assert [a["aircraft_id"] for a in b["affected"]] == ["DEMO-04"]
    assert b["affected"][0]["why"] == "S/N 1050 is within 1002–1085" and b["affected"][0]["status_now"] == "amber"
    assert {"aircraft_id": "DEMO-05", "why": "S/N 1150 is outside 1002–1085"} in b["not_affected"]
    assert b["checked_aircraft"] == len(api.STATE.aircraft)
    assert b["ad"]["title"] == "P2008 JC — firewall inspection"
    assert b["citations"][0]["quote"] == "P2008 JC aeroplanes, serial numbers 1002 to 1085 inclusive."


def test_q2_2012_02_02_includes_real_aircraft_as_no_records():
    assert client.get("/ads/FAA%3A2012-02-02/affected-aircraft").status_code == 404  # not loaded yet
    client.post(INGEST_2012_02_02)
    b = client.get("/ads/FAA%3A2012-02-02/affected-aircraft").json()
    got = {a["aircraft_id"]: a["status_now"] for a in b["affected"]}
    assert got == {"DEMO-01": "red", "EI-GKN": "no_records"}


def test_q2_conditional_ad_puts_unknowns_in_questions():
    b = client.get("/ads/FAA%3A2004-15-18/affected-aircraft").json()
    assert b["affected"] == [] and [q["aircraft_id"] for q in b["open_questions"]] == ["EI-GWY"]


def test_q2_revision_link():
    ad = client.get("/ads/EASA%3A2024-0152R1/affected-aircraft").json()["ad"]
    assert ad["revises"] == "EASA:2024-0152" and ad["status"] == "active"


# ---------- ingest (demo moment 2) ----------
def test_ingest_turns_demo01_green_to_red():
    r = client.post(INGEST_2012_02_02)
    assert r.status_code == 200
    b = r.json()
    assert b["ad_id"] == "FAA:2012-02-02" and b["source"] == "golden" and b["rejected_fields"] == []
    assert b["changes"]["aircraft_status_changed"] == [{"aircraft_id": "DEMO-01", "from": "green", "to": "red"}]
    assert b["changes"]["superseded"] == ["FAA:2008-03-02"]
    assert all(f["check"] == "quote found in text" for f in b["validated_fields"])
    g4 = {"model": "172S", "serial_from": "172S10490", "serial_to": "172S11073"}
    assert any(f["field"] == "applicability" and f["value"] == g4 for f in b["validated_fields"])
    assert {"from": "FAA:2012-02-02", "link": "appliesTo", "to": "DEMO-01", "derived": False,
            "note": "S/N 172S10600 is within 172S10490–172S11073 (Group 4)"} in b["reasoning_path"]
    assert b["reasoning_path"][0]["link"] == "supersedes" and b["reasoning_path"][0]["to"] == "FAA:2008-03-02"
    assert client.get("/aircraft/DEMO-01/status").json()["status"] == "red"


def test_ingest_twice_changes_nothing():
    first = client.post(INGEST_2012_02_02).json()
    second = client.post(INGEST_2012_02_02).json()
    assert second["changes"] == {"superseded": [], "aircraft_status_changed": []}
    assert second["validated_fields"] == first["validated_fields"]
    assert second["run_id"] != first["run_id"]
    assert len(api.STATE.ads) == len(api.STATE.available)


def test_ingest_already_loaded_ad_changes_nothing():
    b = client.post("/ads/EASA%3A2018-0072/ingest").json()
    assert b["changes"]["aircraft_status_changed"] == [] and b["rejected_fields"] == []


@pytest.mark.parametrize("ad", ["FAA%3A9999-99-99", "2012-02-02", "faa%3A2012-02-02", "FAA%3A2008-03-02"])
def test_ingest_unknown_ad_404(ad):
    r = client.post(f"/ads/{ad}/ingest")
    assert r.status_code == 404 and r.json()["error_code"] == "AD_NOT_FOUND"


def test_ingest_rejects_changed_text_and_does_not_load(monkeypatch):
    real = store.ad_text
    monkeypatch.setattr(store, "ad_text", lambda ad: real(ad).replace("172S11073", "172S11999"))
    b = client.post(INGEST_2012_02_02).json()
    assert [f["field"] for f in b["rejected_fields"]] == ["applicability"]
    assert b["changes"]["aircraft_status_changed"] == []
    assert "FAA:2012-02-02" not in api.STATE.ads
    assert client.get("/aircraft/DEMO-01/status").json()["status"] == "green"


def test_reset_undoes_ingest():
    client.post(INGEST_2012_02_02)
    b = client.post("/demo/reset").json()
    assert b["not_loaded"] == ["FAA:2012-02-02"]
    assert b["aircraft_status"]["DEMO-01"] == "green" and b["aircraft_status"]["DEMO-04"] == "amber"
    assert b["counts"]["ads"] == 4 and b["counts"]["logbook_records"] == 21 and b["counts"]["aircraft"] == 8
    assert b["counts"]["questions"] == 2  # DEMO-04 MOD, EI-GWY KAP 140
    assert client.post(INGEST_2012_02_02).json()["run_id"].endswith("-001")
