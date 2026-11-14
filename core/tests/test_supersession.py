"""Q3 — supersession chain and whether earlier compliance is still valid. Real data unless stated."""
import json

import pytest
from fastapi.testclient import TestClient

from app import rules, store
from app.api import EXAMPLES_DIR, app

client = TestClient(app)
STATE = store.load()
INGEST_2012_02_02 = "/ads/FAA%3A2012-02-02/ingest"
CREDIT_G1 = ("(1) If you previously complied with AD 2006-20-09 (71 FR 57407, September 29, 2006), no further "
             "action is required.")


@pytest.fixture(autouse=True)
def demo_state():
    assert client.post("/demo/reset").status_code == 200


def q3(aircraft: str, ad: str) -> dict:
    r = client.get(f"/aircraft/{aircraft}/ads/{ad.replace(':', '%3A')}/supersession")
    assert r.status_code == 200, r.text
    return r.json()


# ---------- the test table ----------
@pytest.mark.parametrize("aircraft,ad,expected", [
    ("DEMO-01", "FAA:2006-20-09", "yes"),             # credited via 2012-19-01 (g)(1)  ← contract example row
    ("DEMO-01", "FAA:2012-19-01", "yes"),             # in force, no own record, credited record
    ("DEMO-02", "FAA:2006-20-09", "not_applicable"),  # engine not listed in MSB 569A
    ("EI-GKN", "FAA:2006-20-09", "unknown"),          # MSB 569A question
    ("DEMO-02", "FAA:2013-03-15", "yes"),             # in force, own record
    ("DEMO-03", "FAA:2006-12-07", "unknown"),         # ECi question
    ("DEMO-05", "EASA:2024-0152R1", "not_applicable"),  # MOD2008/233 embodied
])
def test_table(aircraft, ad, expected):
    assert q3(aircraft, ad)["still_valid"] == expected


def test_contract_example_matches_a_table_row():
    ex = json.loads((EXAMPLES_DIR / "q3-supersession.json").read_text(encoding="utf-8"))["response"]["body"]
    assert (ex["aircraft_id"], ex["asked_ad_id"], ex["still_valid"]) == ("DEMO-01", "FAA:2006-20-09", "yes")


def test_demo01_2006_20_09_chain_path_and_credit():
    b = q3("DEMO-01", "FAA:2006-20-09")
    assert [(c["ad_id"], c["status"], c["superseded_by"]) for c in b["chain"]] == [
        ("FAA:2006-20-09", "superseded", "FAA:2012-19-01"), ("FAA:2012-19-01", "active", None)]
    assert b["compliance"]["id"] == "CR-DEMO01-ENG-1" and b["compliance"]["epistemic_class"] == "OBSERVATION"
    assert b["compliance"]["synthetic"] is True and b["compliance"]["recorded_by"] is None
    assert [(s["from"], s["link"], s["to"], s["derived"]) for s in b["reasoning_path"]] == [
        ("DEMO-01", "hasInstalled", "DEMO-01/engine", False),
        ("FAA:2012-19-01", "appliesTo", "DEMO-01/engine", False),
        ("FAA:2012-19-01", "appliesTo", "DEMO-01", True),
        ("FAA:2012-19-01", "supersedes", "FAA:2006-20-09", False),
        ("CR-DEMO01-ENG-1", "satisfies", "FAA:2006-20-09", False)]
    credit = [c for c in b["citations"] if c["quote"] == CREDIT_G1]
    assert credit and credit[0]["occurrence"] == 2 and credit[0]["file"] == "data/raw/ads/FAA-2012-19-01.txt"
    assert any(c["quote"] == "This AD supersedes AD 2006-20-09 (71 FR 57407, September 29, 2006)."
               for c in b["citations"])


def test_demo01_2012_19_01_reason_says_no_own_record_and_g1():
    b = q3("DEMO-01", "FAA:2012-19-01")
    assert "FAA:2012-19-01 has no compliance record of its own" in b["reason"]
    assert "paragraph (g)(1) of FAA:2012-19-01" in b["reason"] and CREDIT_G1 in b["reason"]
    assert any(c["quote"] == CREDIT_G1 and c["occurrence"] == 2 for c in b["citations"])
    assert b["compliance"]["id"] == "CR-DEMO01-ENG-1" and b["compliance"]["ad_id"] == "FAA:2006-20-09"


def test_unknown_reason_carries_the_question():
    assert "Is EI-GKN's engine S/N" in q3("EI-GKN", "FAA:2006-20-09")["reason"]


def test_real_aircraft_never_yes_without_records():
    for reg in ("EI-GKN", "EI-HAS", "EI-GWY"):
        for ad in ("FAA:2006-20-09", "FAA:2012-19-01", "FAA:2004-15-18", "EASA:2018-0072"):
            assert q3(reg, ad)["still_valid"] in ("no_record", "unknown", "not_applicable")


# ---------- an AD with no golden file, named by a loaded AD ----------
def test_2008_03_02_is_404_before_ingest_and_again_after_reset():
    path = "/aircraft/DEMO-01/ads/FAA%3A2008-03-02/supersession"
    r = client.get(path)
    assert r.status_code == 404 and r.json()["error_code"] == "AD_NOT_FOUND"
    client.post(INGEST_2012_02_02)
    assert client.get(path).status_code == 200
    client.post("/demo/reset")
    r = client.get(path)
    assert r.status_code == 404 and r.json()["error_code"] == "AD_NOT_FOUND"


def test_2008_03_02_after_ingest_no_record():
    client.post(INGEST_2012_02_02)
    b = q3("DEMO-01", "FAA:2008-03-02")
    assert b["still_valid"] == "no_record" and b["compliance"] is None
    assert b["chain"][0] == {"ad_id": "FAA:2008-03-02", "status": "superseded", "superseded_by": "FAA:2012-02-02",
                             "link": "supersedes", "effective_date": None}
    assert "(Group 4)" in b["reason"]


# ---------- 404 ----------
@pytest.mark.parametrize("path,code", [
    ("/aircraft/EI-XXX/ads/FAA%3A2006-20-09/supersession", "AIRCRAFT_NOT_FOUND"),
    ("/aircraft/DEMO-01/ads/FAA%3A9999-99-99/supersession", "AD_NOT_FOUND"),
    ("/aircraft/DEMO-01/ads/2006-20-09/supersession", "AD_NOT_FOUND"),
    ("/aircraft/EI-XXX/ads/FAA%3A9999-99-99/supersession", "AIRCRAFT_NOT_FOUND"),
])
def test_not_found(path, code):
    r = client.get(path)
    assert r.status_code == 404 and r.json()["error_code"] == code


# ---------- chain edge cases (test copies of real ADs) ----------
def _with(ad, **update):
    return ad.model_copy(update={"golden": ad.golden.model_copy(update=update)})


def test_chain_cycle_is_unknown():
    a, b = STATE.ads["FAA:2006-20-09"], STATE.ads["FAA:2012-19-01"]
    ads = {a.ad_id: _with(a, supersedes=["FAA:2012-19-01"]), b.ad_id: b}
    chain, problem = rules.supersession_chain("FAA:2006-20-09", ads)
    assert problem and "cycle" in problem
    assert rules.still_valid(chain, problem, None, {}, ads).value == "unknown"


def test_chain_branch_is_unknown():
    b, c = STATE.ads["FAA:2012-19-01"], STATE.ads["FAA:2013-03-15"]
    ads = {b.ad_id: b, c.ad_id: _with(c, supersedes=["FAA:2006-20-09"])}
    _chain, problem = rules.supersession_chain("FAA:2006-20-09", ads)
    assert problem == "FAA:2006-20-09 is superseded by more than one AD: FAA:2012-19-01, FAA:2013-03-15"


def test_record_without_labelled_credit_is_unknown_not_no():
    b = STATE.ads["FAA:2012-19-01"]
    ads = {b.ad_id: _with(b, credited_compliance=[])}
    chain, problem = rules.supersession_chain("FAA:2006-20-09", ads)
    head = rules.evaluate(ads[b.ad_id], STATE.aircraft["DEMO-01"],
                          {"engine_listed_MSB569A": [r for r in STATE.logbook if r.id == "OB-DEMO01-ENG-1"]})
    records = {r.ad_id: r for r in STATE.logbook if r.aircraft_id == "DEMO-01" and r.kind == "compliance"}
    v = rules.still_valid(chain, problem, head, records, ads)
    assert v.value == "unknown" and "names no credit in FAA:2012-19-01 for FAA:2006-20-09" in v.reason


def test_revision_is_a_chain_link():
    chain, problem = rules.supersession_chain("EASA:2024-0152", STATE.ads)
    assert problem is None and [(s.ad_id, s.link) for s in chain] == [("EASA:2024-0152", "revises"),
                                                                     ("EASA:2024-0152R1", None)]


# ---------- the golden credit quote ----------
def test_credit_quote_occurrence_checked_at_load(tmp_path, monkeypatch):
    d = tmp_path / "golden"
    d.mkdir()
    src = json.loads((store.GOLDEN_DIR / "FAA-2012-19-01.json").read_text(encoding="utf-8"))
    assert src["credited_compliance"][0]["occurrence"] == 2
    src["credited_compliance"][0]["occurrence"] = 3  # the sentence appears only twice
    (d / "FAA-2012-19-01.json").write_text(json.dumps(src), encoding="utf-8")
    with pytest.raises(store.DataError, match="credit quote not found 3 time"):
        store.load_ads(d)
