"""Rules on real golden ADs (data/golden/) and the real/demo fleet. Negative cases included."""
from datetime import date

import pytest

from app import rules, store
from app.ontology import Aircraft, LogbookRow

STATE = store.load()
ADS = list(STATE.available.values())  # rules run over the full golden set
TODAY = date(2026, 11, 14)
AD_2012_02_02 = STATE.available["FAA:2012-02-02"]
AD_2004_15_18 = STATE.available["FAA:2004-15-18"]
AD_2018_0072 = STATE.available["EASA:2018-0072"]
AD_2024_0152R1 = STATE.available["EASA:2024-0152R1"]


def plane(model: str, serial, synthetic: bool = True, id_: str = "T-1") -> Aircraft:
    return Aircraft(id=id_, registration=id_, model=model, serial=serial if isinstance(serial, str) else "",
                    engine_model="x", synthetic=synthetic, base=None,
                    arc_review_due="2026-11-28" if synthetic else None).model_copy(update={"serial": serial})


def obs(fact: str, value: str, id_: str = "OB-T-1") -> LogbookRow:
    return LogbookRow(id=id_, aircraft_id="T-1", subject_id="T-1", ad_id="EASA:2024-0152R1", date="2025-01-01",
                      kind="observation", text="test", synthetic=True, fact=fact, value=value)


# ---------- model ----------
@pytest.mark.parametrize("raw,expected", [
    ("Cessna 172S", "172S"), ("CESSNA 172S", "172S"), ("172S", "172S"),
    ("Tecnam P2008 JC", "P2008 JC"), ("  cessna   172R ", "172R"), ("", ""),
])
def test_normalise_model(raw, expected):
    assert rules.normalise_model(raw) == expected


def test_172RG_is_not_172R():
    assert rules.evaluate(AD_2012_02_02, plane("Cessna 172RG", "17281200"), {}).verdict == "not_applicable"


# ---------- serial ----------
@pytest.mark.parametrize("raw,model,expected", [
    ("172S10600", "172S", "172S10600"),
    ("l72S11074", "172S", "172S11074"),   # OCR lowercase L (2013-03-15, 2012-22-01)
    ("172S-10705", "172S", "172S10705"),  # register format
    ("172R-80221", "172R", "17280221"),   # register format, explicit rule
    (" 1050 ", "P2008 JC", "1050"),
    ("t18208001", "T182T", "T18208001"),
])
def test_normalise_serial_accepts(raw, model, expected):
    assert rules.normalise_serial(raw, model) == expected


@pytest.mark.parametrize("raw,model", [
    (None, "172S"), ("", "172S"), ("   ", "172S"), (172, "172S"),
    ("172R-80221", "172S"),   # hyphen prefix is not the aircraft's model
    ("182T-1234", "182T"),    # no explicit rule for this model
    ("172S-10-705", "172S"), ("172S-ABC", "172S"), ("-10705", "172S"),
    ("172S 10600", "172S"), ("172S#10600", "172S"), ("172S", "172S"),
])
def test_normalise_serial_rejects_ambiguous(raw, model):
    assert rules.normalise_serial(raw, model) is None


def test_parse_serial():
    assert rules.parse_serial("172S10600") == rules.Serial("172S", 10600)
    assert rules.parse_serial("17281188") == rules.Serial("", 17281188)
    assert rules.parse_serial("T18208001") == rules.Serial("T", 18208001)
    with pytest.raises(ValueError):
        rules.parse_serial("172S")


# ---------- ranges: both sides of every 2012-02-02 boundary ----------
@pytest.mark.parametrize("model,serial,verdict,group", [
    ("172R", "17281187", "not_applicable", None),
    ("172R", "17281188", "applies", "Group 1"),
    ("172R", "17281390", "applies", "Group 1"),
    ("172R", "17281391", "applies", "Group 3"),
    ("172R", "17281572", "applies", "Group 3"),
    ("172R", "17281573", "not_applicable", None),
    ("172S", "172S9490", "not_applicable", None),
    ("172S", "172S9491", "applies", "Group 2"),
    ("172S", "172S10489", "applies", "Group 2"),
    ("172S", "172S10490", "applies", "Group 4"),
    ("172S", "172S11073", "applies", "Group 4"),
    ("172S", "172S11074", "not_applicable", None),
    ("172S", "172S-10600", "applies", "Group 4"),
])
def test_2012_02_02_boundaries(model, serial, verdict, group):
    r = rules.evaluate(AD_2012_02_02, plane(f"Cessna {model}", serial), {})
    assert r.verdict == verdict
    if group:
        assert r.why.endswith(f"({group})")
        assert r.citations[0].quote.startswith(f"{group}:")


def test_single_serial_and_gaps_2004_15_18():
    # 172S 172S9195, 172S9197 listed; 172S9196 and 172S9199 are gaps
    facts = {"KAP140_installed": [obs("KAP140_installed", "yes")]}
    for s, v in [("172S9195", "applies"), ("172S9196", "not_applicable"), ("172S9197", "applies"),
                 ("172S9199", "not_applicable"), ("172S9203", "applies"), ("172S9204", "not_applicable")]:
        assert rules.evaluate(AD_2004_15_18, plane("Cessna 172S", s), facts).verdict == v, s


def test_easa_range_inclusive():
    for s, v in [("1001", "not_applicable"), ("1002", "applies"), ("1085", "applies"), ("1086", "not_applicable")]:
        assert rules.evaluate(AD_2018_0072, plane("Tecnam P2008 JC", s), {}).verdict == v, s


# ---------- unclear serial → QUESTION, never not_applicable ----------
@pytest.mark.parametrize("serial", ["", None, "172S#10600", "172R-80221", "17281200", "ABC-?"])
def test_unclear_serial_is_a_question(serial):
    r = rules.evaluate(AD_2012_02_02, plane("Cessna 172S", serial), {})
    assert r.verdict == "unknown"
    assert r.question == f"serial unclear: {serial}"


def test_unclear_serial_synthetic_is_amber_real_is_no_records():
    syn = rules.assess(plane("Cessna 172S", "172S#10600"), ADS, [], TODAY)
    real = rules.assess(plane("Cessna 172S", "172S#10600", synthetic=False), ADS, [], TODAY)
    assert syn.status == "amber" and any(q.text == "serial unclear: 172S#10600" for q in syn.questions)
    assert real.status == "no_records" and any(q.text == "serial unclear: 172S#10600" for q in real.questions)
    assert real.questions[0].deadline is None and real.questions[0].urgency is None


def test_all_serials_row_needs_no_serial():
    # 2024-0152R1 covers all P2008 JC serials: an odd serial is no reason for a question about the serial
    r = rules.evaluate(AD_2024_0152R1, plane("Tecnam P2008 JC", "???"), {})
    assert r.verdict == "unknown" and "serial" not in (r.question or "")


# ---------- conditions: matched on fact/value, positive and negative ----------
def test_condition_unknown_without_observation():
    r = rules.evaluate(AD_2024_0152R1, plane("Tecnam P2008 JC", "1050"), {})
    assert r.verdict == "unknown"
    assert r.question == "Is MOD2008/233 or SB-826-CS embodied on T-1?"


def test_condition_embodied_means_not_applicable():
    r = rules.evaluate(AD_2024_0152R1, plane("Tecnam P2008 JC", "1150"),
                       {"MOD2008_233": [obs("MOD2008_233", "embodied")]})
    assert r.verdict == "not_applicable" and "OB-T-1" in r.why


def test_condition_all_hold_means_applies():
    facts = {"MOD2008_233": [obs("MOD2008_233", "not_embodied")], "SB_826_CS": [obs("SB_826_CS", "not_embodied")]}
    assert rules.evaluate(AD_2024_0152R1, plane("Tecnam P2008 JC", "1150"), facts).verdict == "applies"


def test_condition_partly_known_is_still_unknown():
    r = rules.evaluate(AD_2024_0152R1, plane("Tecnam P2008 JC", "1150"),
                       {"MOD2008_233": [obs("MOD2008_233", "not_embodied")]})
    assert r.verdict == "unknown" and r.question == "Is SB-826-CS embodied on T-1?"


def test_positive_equipment_observation_applies():
    p = plane("Cessna 172S", "172S9000")
    assert rules.evaluate(AD_2004_15_18, p, {"KAP140_installed": [obs("KAP140_installed", "yes")]}).verdict == "applies"
    assert rules.evaluate(AD_2004_15_18, p, {"KAP140_installed": [obs("KAP140_installed", "no")]}).verdict \
        == "not_applicable"
    assert rules.evaluate(AD_2004_15_18, p, {}).verdict == "unknown"


def test_contradicting_observations_are_unknown():
    facts = {"MOD2008_233": [obs("MOD2008_233", "embodied", "OB-1"), obs("MOD2008_233", "not_embodied", "OB-2")]}
    assert rules.evaluate(AD_2024_0152R1, plane("Tecnam P2008 JC", "1150"), facts).verdict == "unknown"


def test_value_outside_condition_vocabulary_is_unknown():
    # 'yes' does not answer an embodied/not_embodied condition
    facts = {"MOD2008_233": [obs("MOD2008_233", "yes")]}
    assert rules.evaluate(AD_2024_0152R1, plane("Tecnam P2008 JC", "1150"), facts).verdict == "unknown"


# ---------- status ----------
@pytest.mark.parametrize("days,expected", [(-1, "overdue"), (0, "high"), (30, "high"), (31, "medium"),
                                           (90, "medium"), (91, "low")])
def test_urgency(days, expected):
    assert rules.urgency(days) == expected


@pytest.mark.parametrize("unrecorded,unknown", [(True, True), (True, False), (False, True), (False, False)])
def test_real_aircraft_never_red(unrecorded, unknown):
    assert rules.aircraft_status(False, unrecorded, unknown) == "no_records"


def test_synthetic_status_order():
    assert rules.aircraft_status(True, True, True) == "red"
    assert rules.aircraft_status(True, False, True) == "amber"
    assert rules.aircraft_status(True, False, False) == "green"


def test_fleet_statuses_from_real_data():
    # full golden set = the state after FAA:2012-02-02 is ingested
    got = {a.id: rules.assess(a, ADS, STATE.logbook, TODAY).status for a in STATE.aircraft.values()}
    assert got == {"DEMO-01": "red", "DEMO-02": "green", "DEMO-03": "amber", "DEMO-04": "amber",
                   "DEMO-05": "green", "EI-GKN": "no_records", "EI-HAS": "no_records", "EI-GWY": "no_records"}


def test_demo_state_before_ingest():
    demo_ads = list(STATE.ads.values())  # without store.NOT_LOADED_AT_RESET
    got = {a.id: rules.assess(a, demo_ads, STATE.logbook, TODAY).status for a in STATE.aircraft.values()}
    assert got["DEMO-01"] == "green" and got["DEMO-04"] == "amber"


def test_demo04_question_deadline_from_arc_review():
    q = rules.assess(STATE.aircraft["DEMO-04"], ADS, STATE.logbook, TODAY).questions
    assert [(x.ad_id, x.deadline, x.days_left, x.urgency) for x in q] == \
        [("EASA:2024-0152R1", "2026-11-28", 14, "high")]


def test_compliance_record_makes_applicable_ad_green():
    a = rules.assess(STATE.aircraft["DEMO-02"], ADS, STATE.logbook, TODAY)
    assert a.results["FAA:2013-03-15"].verdict == "applies" and a.compliance["FAA:2013-03-15"].id == "CR-DEMO02-AF-1"


def test_removing_an_observation_raises_its_question():
    logbook = [r for r in STATE.logbook if r.id != "OB-DEMO05-AF-1"]
    a = rules.assess(STATE.aircraft["DEMO-05"], ADS, logbook, TODAY)
    assert a.status == "amber" and [q.ad_id for q in a.questions] == ["EASA:2024-0152R1"]


def test_real_aircraft_question_has_no_deadline():
    q = rules.assess(STATE.aircraft["EI-GWY"], ADS, STATE.logbook, TODAY).questions
    assert [x.ad_id for x in q] == ["FAA:2004-15-18", "FAA:2006-12-07", "FAA:2012-19-01"]
    assert all(x.deadline is None and x.urgency is None and not x.synthetic for x in q)


# ---------- due citation ----------
def test_due_citation_picks_the_group_paragraph():
    r = rules.evaluate(AD_2012_02_02, plane("Cessna 172S", "172S10600"), {})
    c = rules.due_citation(AD_2012_02_02, r.row)
    assert c is not None and c.quote.startswith("(2) For Group 3 and Group 4 Airplanes:")
    r2 = rules.evaluate(AD_2012_02_02, plane("Cessna 172S", "172S10000"), {})
    assert rules.due_citation(AD_2012_02_02, r2.row).quote.startswith("(1) For Group 1 and Group 2 Airplanes:")


def test_due_citation_none_without_group():
    r = rules.evaluate(AD_2018_0072, plane("Tecnam P2008 JC", "1050"), {})
    assert rules.due_citation(AD_2018_0072, r.row) is None
    assert rules.due_citation(AD_2018_0072, None) is None
