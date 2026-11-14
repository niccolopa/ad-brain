"""The decision table in docs/DECISION-MODEL.md and the code list the same rule ids; every rule fires somewhere."""
import re
from datetime import date

from fastapi.testclient import TestClient

from app import rules, store
from app.api import app
from app.ontology import LogbookRow

DOC = store.REPO / "docs" / "DECISION-MODEL.md"
ROW_RE = re.compile(r"^\| (R-[A-Z-]+) \|", re.MULTILINE)
STATE = store.load()
ADS = list(STATE.available.values())
TODAY = date(2026, 11, 14)
client = TestClient(app)


def table_ids() -> list[str]:
    return ROW_RE.findall(DOC.read_text(encoding="utf-8"))


def test_table_and_code_list_the_same_ids():
    ids = table_ids()
    assert len(ids) == len(set(ids)), "duplicate id in the table"
    assert set(ids) == rules.RULE_IDS, {"only in doc": set(ids) - rules.RULE_IDS,
                                        "only in code": rules.RULE_IDS - set(ids)}


def test_every_table_row_has_five_filled_cells():
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if ROW_RE.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            assert len(cells) == 5 and all(cells), line


def _obs(aircraft_id: str, fact: str, value: str, id_: str) -> LogbookRow:
    return LogbookRow(id=id_, aircraft_id=aircraft_id, subject_id=aircraft_id, ad_id="FAA:2004-15-18",
                      date="2025-01-01", kind="observation", text="test", synthetic=True, fact=fact, value=value)


def fired_everywhere() -> set[str]:
    """Union of the rules fired by real-data scenarios (plus a few edge inputs)."""
    fired: set[str] = set()
    for ac in STATE.aircraft.values():
        fired |= set(rules.assess(ac, ADS, STATE.logbook, TODAY).rule_ids)
    demo01 = STATE.aircraft["DEMO-01"]
    odd = [demo01.model_copy(update={"id": "T-1", "serial": "172S-10600"}),   # register format
           demo01.model_copy(update={"id": "T-2", "serial": "172S#1"}),       # unclear
           demo01.model_copy(update={"id": "T-3", "serial": "172S9000"})]     # KAP 140 range
    log = STATE.logbook + [_obs("T-3", "KAP140_installed", "yes", "OB-T3-1"),
                           _obs("T-1", "KAP140_installed", "yes", "OB-T1-1"),
                           _obs("T-1", "KAP140_installed", "no", "OB-T1-2")]  # T-1 is outside the KAP range: ignored
    log += [_obs("T-4", "KAP140_installed", "yes", "OB-T4-1"),  # T-4: contradiction inside the range
            _obs("T-4", "KAP140_installed", "no", "OB-T4-2")]
    odd.append(demo01.model_copy(update={"id": "T-4", "serial": "172S9000"}))
    for ac in odd:
        fired |= set(rules.assess(ac, ADS, log, TODAY).rule_ids)
    for path in ["/aircraft/DEMO-01/ads/FAA%3A2006-20-09/supersession"]:
        for step in client.get(path).json()["reasoning_path"]:
            fired.add(step["rule_id"])
    chain, problem = rules.supersession_chain("FAA:2006-20-09", STATE.ads)
    head = rules.assess(demo01, list(STATE.ads.values()), STATE.logbook, TODAY).results[chain[-1].ad_id]
    records = {r.ad_id: r for r in STATE.logbook if r.aircraft_id == "DEMO-01" and r.kind == "compliance"}
    no_credit = {**STATE.ads, "FAA:2012-19-01": STATE.ads["FAA:2012-19-01"].model_copy(update={
        "golden": STATE.ads["FAA:2012-19-01"].golden.model_copy(update={"credited_compliance": []})})}
    fired |= set(rules.still_valid(chain, problem, head, records, STATE.ads).rule_ids)
    fired |= set(rules.still_valid(chain, problem, head, records, no_credit).rule_ids)
    fired |= set(rules.still_valid(chain, "cycle", None, records, STATE.ads).rule_ids)
    return fired


def test_every_rule_fires_in_some_scenario():
    fired = fired_everywhere()
    assert fired <= rules.RULE_IDS, fired - rules.RULE_IDS
    assert rules.RULE_IDS - fired == set()


def test_every_reasoning_step_names_a_known_rule():
    client.post("/demo/reset")
    client.post("/ads/FAA%3A2012-02-02/ingest")
    paths = [f"/aircraft/{a}/status" for a in STATE.aircraft]
    paths += [f"/ads/{ad.replace(':', '%3A')}/affected-aircraft" for ad in STATE.available]
    paths += ["/aircraft/DEMO-01/ads/FAA%3A2006-20-09/supersession", "/aircraft/DEMO-01/ads/FAA%3A2008-03-02/supersession"]
    steps = [s for p in paths for s in client.get(p).json()["reasoning_path"]]
    client.post("/demo/reset")
    assert steps and all(s["rule_id"] in rules.RULE_IDS for s in steps)


def test_status_rule_matches_status():
    for ac in STATE.aircraft.values():
        a = rules.assess(ac, ADS, STATE.logbook, TODAY)
        assert a.rule_ids[-1] == rules.STATUS_RULE[a.status]
