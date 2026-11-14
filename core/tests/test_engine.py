"""Aircraft → installed engine → AD inference, on the checked engine ADs in data/golden/."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import api, rules, store
from app.api import app
from app.ontology import GoldenApplicability

TODAY = date(2026, 11, 14)
STATE = store.load()
ENGINE_IDS = ("FAA:2006-12-07", "FAA:2006-20-09", "FAA:2012-19-01")
DRAFTS = {k: STATE.available[k] for k in ENGINE_IDS}  # name kept from the draft stage: the 3 engine ADs
ECI, CRANK_2006, CRANK_2012 = DRAFTS["FAA:2006-12-07"], DRAFTS["FAA:2006-20-09"], DRAFTS["FAA:2012-19-01"]
CREDIT_G1 = ("(1) If you previously complied with AD 2006-20-09 (71 FR 57407, September 29, 2006), no further "
             "action is required.")
DATE_CLAUSE = "not evaluated: manufacture/overhaul date clause (see notes)"
client = TestClient(app)


def facts_of(aircraft_id: str) -> dict:
    out: dict = {}
    for r in STATE.logbook:
        if r.aircraft_id == aircraft_id and r.kind == "observation":
            out.setdefault(r.fact, []).append(r)
    return out


def test_engine_ads_are_loaded_by_default():
    assert set(ENGINE_IDS) <= set(STATE.ads)


@pytest.mark.parametrize("engine,expected", [
    ("IO-360-L2A", True), ("IO-360-M1A", True),
    ("IO-360", False), ("IO-3600-L2A", False), ("AEIO-360-B1B", False), ("O-360-A1A", False),
    ("LIO-360-C1E6", False), ("", False),
])
def test_series_row_match(engine, expected):
    row = GoldenApplicability(model="IO-360", series=True, serial_from=None, serial_to=None, quote="q")
    assert rules.model_matches(row, engine) is expected


def test_exact_engine_row_match():
    row = GoldenApplicability(model="IO-360-L2A", serial_from=None, serial_to=None, quote="q")
    assert rules.model_matches(row, rules.normalise_model("LYCOMING IO-360-L2A"))
    assert rules.model_matches(row, rules.normalise_model("Lycoming IO-360-L2A"))
    assert not rules.model_matches(row, "IO-360-L2AX")


def test_eci_question_for_demo03():
    r = rules.evaluate(ECI, STATE.aircraft["DEMO-03"], facts_of("DEMO-03"))
    assert r.verdict == "unknown" and r.via == "engine"
    assert r.question.startswith("Is ECi cylinder assemblies P/N AEL65102") and r.question.endswith("on DEMO-03?")
    assert DATE_CLAUSE in r.why


def test_eci_not_applicable_when_observed_absent():
    r = rules.evaluate(ECI, STATE.aircraft["DEMO-01"], facts_of("DEMO-01"))
    assert r.verdict == "not_applicable" and "OB-DEMO01-ENG-3" in r.why


def test_rotax_engine_not_matched():
    for ad in DRAFTS.values():
        assert rules.evaluate(ad, STATE.aircraft["DEMO-04"], {}).verdict == "not_applicable"


def test_applies_says_what_is_not_evaluated():
    r = rules.evaluate(CRANK_2012, STATE.aircraft["DEMO-01"], facts_of("DEMO-01"))
    assert r.verdict == "applies" and r.via == "engine"
    assert r.why.startswith("engine IO-360-L2A is an IO-360 series engine; engine_listed_MSB569A = yes")
    assert DATE_CLAUSE in r.why and "crankshaft Table 5 clause" in r.why
    assert any(c.quote.startswith("These applicable engines are manufactured new") for c in r.citations)


def test_superseded_compliance_is_credited_and_old_ad_not_counted():
    a = rules.assess(STATE.aircraft["DEMO-01"], list(STATE.ads.values()) + [CRANK_2006, CRANK_2012],
                     STATE.logbook, TODAY)
    assert a.superseded == ["FAA:2006-20-09"] and "FAA:2006-20-09" not in a.results
    assert a.compliance["FAA:2012-19-01"].id == "CR-DEMO01-ENG-1"
    credit = a.credits["FAA:2012-19-01"]
    assert credit.quote == CREDIT_G1 and credit.occurrence == 2  # rule text; occurrence 1 is the preamble
    assert a.status == "green"


def test_old_ad_alone_is_complied_directly():
    a = rules.assess(STATE.aircraft["DEMO-01"], [CRANK_2006], STATE.logbook, TODAY)
    assert a.results["FAA:2006-20-09"].verdict == "applies" and "FAA:2006-20-09" not in a.credits
    assert a.status == "green"


def test_no_credited_record_is_red_for_synthetic():
    logbook = [r for r in STATE.logbook if r.id != "CR-DEMO01-ENG-1"]
    assert rules.assess(STATE.aircraft["DEMO-01"], [CRANK_2006, CRANK_2012], logbook, TODAY).status == "red"


def test_real_aircraft_engine_question_and_no_records():
    a = rules.assess(STATE.aircraft["EI-GKN"], list(DRAFTS.values()), STATE.logbook, TODAY)
    assert a.status == "no_records"
    texts = {q.ad_id: q.text for q in a.questions}
    assert texts["FAA:2012-19-01"] == ("Is EI-GKN's engine S/N (Tables 1-4) or crankshaft S/N (Table 5) "
                                       "listed in Lycoming MSB 569A?")
    assert "FAA:2006-20-09" not in texts  # superseded: no question for it


def test_ranged_engine_row_is_a_question():
    row = CRANK_2012.golden.applicability[0].model_copy(update={"model": "IO-360", "serial_from": "L-1",
                                                                "serial_to": "L-9"})
    ad = CRANK_2012.model_copy(update={"golden": CRANK_2012.golden.model_copy(update={"applicability": [row]})})
    r = rules.evaluate(ad, STATE.aircraft["DEMO-01"], {})
    assert r.verdict == "unknown" and r.question == "engine serial unclear: DEMO-01/engine"


# ---------- over HTTP, demo state (engine ADs loaded) ----------
@pytest.fixture
def with_drafts():
    client.post("/demo/reset")
    assert set(ENGINE_IDS) <= set(api.STATE.ads)
    yield


def test_q1_engine_path_is_drawn_with_derived_link(with_drafts):
    b = client.get("/aircraft/DEMO-01/status").json()
    assert b["status"] == "green" and b["superseded_ads"] == ["FAA:2006-20-09"]
    steps = [s for s in b["reasoning_path"] if "FAA:2012-19-01" in (s["from"], s["to"]) or s["link"] == "hasInstalled"]
    assert steps[0] == {"from": "DEMO-01", "link": "hasInstalled", "to": "DEMO-01/engine", "derived": False,
                        "note": "Lycoming IO-360-L2A", "rule_id": "R-ENGINE-DERIVED"}
    assert (steps[1]["from"], steps[1]["to"], steps[1]["derived"]) == ("FAA:2012-19-01", "DEMO-01/engine", False)
    assert (steps[2]["from"], steps[2]["to"], steps[2]["derived"]) == ("FAA:2012-19-01", "DEMO-01", True)
    assert DATE_CLAUSE in steps[1]["note"] and DATE_CLAUSE in steps[2]["note"]
    assert steps[3]["link"] == "satisfies" and steps[3]["from"] == "CR-DEMO01-ENG-1"
    [ad] = [x for x in b["applicable_ads"] if x["ad_id"] == "FAA:2012-19-01"]
    assert ad["compliance"] == {"state": "complied", "record_id": "CR-DEMO01-ENG-1"} and DATE_CLAUSE in ad["applies_because"]


def test_q1_demo03_amber_with_eci_question(with_drafts):
    b = client.get("/aircraft/DEMO-03/status").json()
    assert b["status"] == "amber" and [q["ad_id"] for q in b["open_questions"]] == ["FAA:2006-12-07"]


def test_q2_engine_ad_affected_via_installed_engine(with_drafts):
    b = client.get("/ads/FAA%3A2012-19-01/affected-aircraft").json()
    assert {a["aircraft_id"]: a["via"] for a in b["affected"]} == {"DEMO-01": "installed_engine"}
    assert {q["aircraft_id"] for q in b["open_questions"]} == {"EI-GKN", "EI-HAS", "EI-GWY"}
    assert any(s["derived"] for s in b["reasoning_path"])


def test_q2_superseded_ad_affects_nobody(with_drafts):
    b = client.get("/ads/FAA%3A2006-20-09/affected-aircraft").json()
    assert b["affected"] == [] and b["ad"]["status"] == "superseded" and b["ad"]["superseded_by"] == "FAA:2012-19-01"
    assert all(n["why"] == "FAA:2006-20-09 is superseded" for n in b["not_affected"])
