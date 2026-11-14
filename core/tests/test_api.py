"""Q1 and Q2 over HTTP: real answers, 404s, real aircraft never red."""
import json

import pytest
from fastapi.testclient import TestClient

from app.api import EXAMPLES_DIR, STATE, app

client = TestClient(app)


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


def test_q1_demo01_red_group4():
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
    assert "AD applies — no compliance records in this system" in client.get("/aircraft/EI-GKN/status").json()["summary"]


def test_q2_easa_2018_0072():
    b = client.get("/ads/EASA%3A2018-0072/affected-aircraft").json()
    assert [a["aircraft_id"] for a in b["affected"]] == ["DEMO-04"]
    assert b["affected"][0]["why"] == "S/N 1050 is within 1002–1085" and b["affected"][0]["status_now"] == "amber"
    assert {"aircraft_id": "DEMO-05", "why": "S/N 1150 is outside 1002–1085"} in b["not_affected"]
    assert b["checked_aircraft"] == len(STATE.aircraft)
    assert b["ad"]["title"] == "P2008 JC — firewall inspection"
    assert b["citations"][0]["quote"] == "P2008 JC aeroplanes, serial numbers 1002 to 1085 inclusive."


def test_q2_2012_02_02_includes_real_aircraft_as_no_records():
    b = client.get("/ads/FAA%3A2012-02-02/affected-aircraft").json()
    got = {a["aircraft_id"]: a["status_now"] for a in b["affected"]}
    assert got == {"DEMO-01": "red", "EI-GKN": "no_records"}


def test_q2_conditional_ad_puts_unknowns_in_questions():
    b = client.get("/ads/FAA%3A2004-15-18/affected-aircraft").json()
    assert b["affected"] == [] and [q["aircraft_id"] for q in b["open_questions"]] == ["EI-GWY"]


def test_q2_revision_link():
    ad = client.get("/ads/EASA%3A2024-0152R1/affected-aircraft").json()["ad"]
    assert ad["revises"] == "EASA:2024-0152" and ad["status"] == "active"
