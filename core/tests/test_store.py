"""Loading data/: real files load; bad files fail loudly."""
import json
import shutil

import pytest

from app import store
from app.ontology import Aircraft


def test_real_data_loads():
    s = store.load()
    assert set(s.available) == {"FAA:2004-15-18", "FAA:2012-02-02", "FAA:2013-03-15", "EASA:2018-0072",
                                "EASA:2024-0152R1"}
    assert set(s.ads) == set(s.available) - store.NOT_LOADED_AT_RESET
    assert "FAA:2012-02-02" not in s.ads
    assert len(s.aircraft) == 8 and len(s.logbook) == 21
    assert s.available["FAA:2012-02-02"].title == "Fuel return line chafing (adds serials)"
    assert s.available["FAA:2012-02-02"].file == "data/raw/ads/FAA-2012-02-02.txt"
    assert s.available["FAA:2012-02-02"].source_url == "https://ad.easa.europa.eu/blob/20120202.pdf/AD_US-2012-02-02_1"
    assert {a.id for a in s.aircraft.values() if not a.synthetic} == {"EI-GKN", "EI-HAS", "EI-GWY"}


def test_every_citation_quote_is_in_its_file():
    for ad in store.load().available.values():
        text = (store.REPO / ad.file).read_text(encoding="utf-8")
        for row in ad.golden.applicability:
            assert store.quote_count(ad.cite(row.quote).quote, text) >= 1


def test_no_personal_data_fields():
    assert set(Aircraft.model_fields) == {"id", "registration", "model", "serial", "engine_model", "synthetic",
                                          "base", "arc_review_due"}


def test_collapse_whitespace():
    assert store.quote_count("Group 4: Model 172S,\n  S/N", "x Group 4:\tModel   172S, S/N y") == 1
    assert store.quote_count("absent", "text") == 0


def test_parse_index_titles():
    md = "| ID | Subject |\n|---|---|\n| FAA:1-1 | Fuel line | x |\n| EASA:2-2 | Firewall |\nnot a row\n"
    assert store.parse_index_titles(md) == {"FAA:1-1": "Fuel line", "EASA:2-2": "Firewall"}
    assert store.parse_index_titles("") == {}
    with pytest.raises(store.DataError):
        store.parse_index_titles("| FAA:1-1 |  | x |")


# ---------- fail loudly: copy the real files to tmp, break one thing ----------
@pytest.fixture
def golden_copy(tmp_path, monkeypatch):
    d = tmp_path / "golden"
    shutil.copytree(store.GOLDEN_DIR, d)
    monkeypatch.setattr(store, "GOLDEN_DIR", d)
    return d


def _edit(path, fn):
    data = json.loads(path.read_text(encoding="utf-8"))
    fn(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_missing_title_fails(tmp_path, monkeypatch):
    md = tmp_path / "INDEX.md"
    md.write_text("\n".join(l for l in store.INDEX_MD.read_text(encoding="utf-8").splitlines()
                            if not l.startswith("| FAA:2012-02-02 ")), encoding="utf-8")
    monkeypatch.setattr(store, "INDEX_MD", md)
    with pytest.raises(store.DataError, match="FAA:2012-02-02: no Subject"):
        store.load_ads()


def test_quote_not_in_text_fails(golden_copy):
    _edit(golden_copy / "FAA-2012-02-02.json",
          lambda d: d["applicability"][3].update(quote="Group 4: Model 172S, S/N 172S10490 through 172S99999"))
    with pytest.raises(store.DataError, match="quote not found"):
        store.load_ads()


@pytest.mark.parametrize("breaker", [
    lambda d: d.update(applicability=[]),
    lambda d: d.update(ad_number="2012-02-02"),          # no authority
    lambda d: d.update(effective_date="13 March 2012"),
    lambda d: d.pop("compliance_time_text"),
])
def test_malformed_golden_fails(golden_copy, breaker):
    _edit(golden_copy / "FAA-2012-02-02.json", breaker)
    with pytest.raises(store.DataError):
        store.load_ads()


def test_bad_condition_value_fails(golden_copy):
    _edit(golden_copy / "EASA-2024-0152R1.json", lambda d: d["conditions"][0].update(applies_when="maybe"))
    with pytest.raises(store.DataError):
        store.load_ads()


def test_invalid_json_fails(golden_copy):
    (golden_copy / "FAA-2012-02-02.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(store.DataError):
        store.load_ads()


HEADER = "id,aircraft_id,subject_id,ad_id,date,kind,text,synthetic,fact,value\n"


@pytest.mark.parametrize("row,match", [
    ("OB-X,DEMO-01,DEMO-01,FAA:2004-15-18,2009-03-20,observation,t,true,,\n", "needs fact and value"),
    ("OB-X,DEMO-99,DEMO-99,FAA:2004-15-18,2009-03-20,observation,t,true,KAP140_installed,no\n", "unknown aircraft"),
    ("OB-X,DEMO-01,DEMO-01,2004-15-18,2009-03-20,observation,t,true,KAP140_installed,no\n", "bad AD id"),
    ("OB-X,DEMO-01,DEMO-01,FAA:2004-15-18,2009-03-20,observation,t,true,KAP140_installed,maybe\n", "OB-X"),
    ("OB-X,DEMO-01,DEMO-01,FAA:2004-15-18,2009-03-20,guess,t,true,KAP140_installed,no\n", "OB-X"),
    ("OB-X,DEMO-01,DEMO-01,FAA:2004-15-18,March 2009,observation,t,true,KAP140_installed,no\n", "OB-X"),
])
def test_bad_logbook_row_fails(tmp_path, monkeypatch, row, match):
    p = tmp_path / "logbook.csv"
    p.write_text(HEADER + row, encoding="utf-8")
    monkeypatch.setattr(store, "LOGBOOK_CSV", p)
    with pytest.raises(store.DataError, match=match):
        store.load_logbook(store.load_aircraft())


def test_logbook_missing_columns_fails(tmp_path, monkeypatch):
    p = tmp_path / "logbook.csv"
    p.write_text("id,aircraft_id\nOB-X,DEMO-01\n", encoding="utf-8")
    monkeypatch.setattr(store, "LOGBOOK_CSV", p)
    with pytest.raises(store.DataError, match="missing columns"):
        store.load_logbook(store.load_aircraft())


def test_bad_synthetic_flag_fails(tmp_path, monkeypatch):
    p = tmp_path / "fleet.csv"
    src = store.FLEET_CSV.read_text(encoding="utf-8").splitlines()
    p.write_text("\n".join([src[0], src[1].replace(",true,", ",yes,", 1)]), encoding="utf-8")
    monkeypatch.setattr(store, "FLEET_CSV", p)
    with pytest.raises(store.DataError, match="expected true/false"):
        store.load_aircraft()


# ---------- field checks (ingest) ----------
def test_field_checks_all_found_on_real_text():
    ad = store.load().available["FAA:2012-02-02"]
    checks = store.field_checks(ad, store.ad_text(ad))
    assert checks and all(c.check == store.QUOTE_FOUND for c in checks)
    assert [c.field for c in checks].count("applicability") == 4
    assert {"effective_date", "supersedes", "compliance_time"} <= {c.field for c in checks}


def test_field_checks_reject_on_changed_text():
    ad = store.load().available["FAA:2012-02-02"]
    text = store.ad_text(ad).replace("172S11073", "172S11999")
    bad = [c for c in store.field_checks(ad, text) if c.check == store.QUOTE_NOT_FOUND]
    assert [c.field for c in bad] == ["applicability"] and "172S11073" in bad[0].quote


def test_field_checks_reject_value_without_quote():
    ad = store.load().available["FAA:2012-02-02"]
    ad = ad.model_copy(update={"golden": ad.golden.model_copy(update={"field_quotes": {}})})
    bad = [c for c in store.field_checks(ad, store.ad_text(ad)) if c.check == store.QUOTE_NOT_FOUND]
    assert {c.field for c in bad} == {"effective_date", "supersedes", "compliance_time"}
    assert all(c.quote == "" for c in bad)


def test_field_checks_empty_text_rejects_everything():
    ad = store.load().available["EASA:2018-0072"]
    assert all(c.check == store.QUOTE_NOT_FOUND for c in store.field_checks(ad, ""))


def test_not_loaded_must_name_a_golden_ad(monkeypatch):
    monkeypatch.setattr(store, "NOT_LOADED_AT_RESET", frozenset({"FAA:0000-00-00"}))
    with pytest.raises(store.DataError, match="NOT_LOADED_AT_RESET"):
        store.load()
