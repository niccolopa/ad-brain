"""GET /ads/{id}: metadata, relations, golden applicability/conditions/not-evaluated/credit with citations, and the
agent's extraction compared with golden. Real golden files and the real extraction cache."""
import pytest
from fastapi.testclient import TestClient

from app import extract, store
from app.api import app

client = TestClient(app)
STATE = store.load()


@pytest.fixture(autouse=True)
def demo_state():
    assert client.post("/demo/reset").status_code == 200
    yield
    client.post("/demo/reset")


def detail(ad_id: str) -> dict:
    r = client.get(f"/ads/{ad_id.replace(':', '%3A')}")
    assert r.status_code == 200, r.text
    return r.json()


def test_2012_02_02_before_ingest_is_served_but_not_loaded():
    b = detail("FAA:2012-02-02")
    assert b["loaded"] is False and b["ad"]["status"] == "active" and b["ad"]["supersedes"] == ["FAA:2008-03-02"]
    assert b["ad"]["title"] == "Fuel return line chafing (adds serials)"
    assert [(g["model"], g["serial_from"], g["serial_to"], g["group"]) for g in b["applicability"]] == [
        ("172R", "17281188", "17281390", "Group 1"), ("172S", "172S9491", "172S10489", "Group 2"),
        ("172R", "17281391", "17281572", "Group 3"), ("172S", "172S10490", "172S11073", "Group 4")]
    assert b["applicability"][3]["citation"]["quote"] == "Group 4: Model 172S, S/N 172S10490 through 172S11073"
    assert b["text"] == store.ad_text(STATE.available["FAA:2012-02-02"])
    ex = b["extraction"]
    assert ex["source"] == "cache" and ex["usable"] is True and ex["agreement"] == 1.0 and ex["misses"] == []
    assert ex["decided_by"] == "not_loaded"


def test_after_ingest_the_extraction_decided():
    client.post("/ads/FAA%3A2012-02-02/ingest")
    b = detail("FAA:2012-02-02")
    assert b["loaded"] is True and b["extraction"]["decided_by"] == "extraction"
    assert all(c["origin"] == "golden" for c in b["citations"])  # still golden quotes


def test_loaded_at_reset_means_golden_decided():
    assert detail("EASA:2018-0072")["extraction"]["decided_by"] == "golden"


def test_credit_paragraph_occurrence_and_not_evaluated_notes():
    b = detail("FAA:2012-19-01")
    [credit] = b["credited_compliance"]
    assert credit["ad_id"] == "FAA:2006-20-09" and credit["paragraph"] == "(g)(1)"
    assert credit["citation"]["occurrence"] == 2
    assert [n["note"] for n in b["not_evaluated"]] == [
        "not evaluated: manufacture/overhaul date clause (see notes)",
        "not evaluated: crankshaft Table 5 clause (engine listed, crankshaft not listed: no action) (see notes)"]
    assert [(c["fact"], c["applies_when"]) for c in b["conditions"]] == [("engine_listed_MSB569A", "yes")]
    assert all(g["series"] for g in b["applicability"])


def test_misses_show_agent_golden_and_who_decided():
    b = detail("FAA:2012-19-01")
    ex = b["extraction"]
    assert ex["usable"] is False and ex["decided_by"] == "golden" and ex["agreement"] < 1
    [miss] = ex["misses"]
    assert miss["field"] == "not_evaluated" and miss["decided"] == "golden"
    assert any("These applicable engines are manufactured new" in g for g in miss["golden"])
    assert any("before January 1, 1997" in a for a in miss["agent_proposed"])
    eci = detail("FAA:2006-12-07")["extraction"]["misses"]
    applic = next(m for m in eci if m["field"] == "applicability")
    assert len(applic["agent_proposed"]) == 18 and len(applic["golden"]) == 15


def test_relations_superseded_and_revises():
    old = detail("FAA:2006-20-09")["ad"]
    assert old["status"] == "superseded" and old["superseded_by"] == "FAA:2012-19-01"
    r1 = detail("EASA:2024-0152R1")
    assert r1["ad"]["revises"] == "EASA:2024-0152" and len(r1["conditions"]) == 2


@pytest.mark.parametrize("ad_id", sorted(STATE.available))
def test_every_citation_is_in_its_file(ad_id):
    b = detail(ad_id)
    text = store.ad_text(STATE.available[ad_id])
    assert b["citations"] and all(c["file"] == STATE.available[ad_id].file for c in b["citations"])
    for c in b["citations"]:
        assert store.quote_count(c["quote"], text) >= c["occurrence"], c["quote"][:60]


def test_without_cache_the_extraction_block_says_why(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "CACHE_DIR", tmp_path)
    ex = detail("EASA:2018-0072")["extraction"]
    assert ex["source"] is None and "no cached extraction" in ex["reason"] and ex["decided_by"] == "golden"


@pytest.mark.parametrize("ad", ["FAA%3A9999-99-99", "FAA%3A2008-03-02", "2012-02-02", "faa%3A2012-02-02"])
def test_unknown_or_unlabelled_ad_404(ad):
    r = client.get(f"/ads/{ad}")
    assert r.status_code == 404 and r.json()["error_code"] == "AD_NOT_FOUND"
