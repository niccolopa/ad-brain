"""Agent extraction: llm.py failure handling (fake client, no network), parsing, comparison with golden,
and how ingest chooses between the cached extraction and golden. Fixtures: the real cache in data/cache/."""
import json
from types import SimpleNamespace

import openai
import pytest
from fastapi.testclient import TestClient

from app import api, extract, llm, store
from app.api import app

STATE = store.load()
client = TestClient(app)
INGEST_2012_02_02 = "/ads/FAA%3A2012-02-02/ingest"
ENV = {"AI_GATEWAY_API_KEY": "sk-test-not-a-real-key", "LLM_BASE_URL": "https://example.invalid/v1",
       "LLM_PROVIDER": "kva", "LLM_MODEL_EXTRACTION": "m-extract", "LLM_MODEL_PHRASING": "m-phrase",
       "LLM_CONNECT_TIMEOUT_SECONDS": "5", "LLM_TOTAL_TIMEOUT_SECONDS": "30", "LLM_PHRASING_MAX_TOKENS": "400",
       "LLM_EXTRACTION_TOTAL_TIMEOUT_SECONDS": "180", "LLM_EXTRACTION_MAX_TOKENS": "16000", "DEMO_MODE": "true"}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "load_dotenv", lambda *_a, **_k: None)  # never read the real .env in tests
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(llm, "USAGE_LOG", tmp_path / "usage.jsonl")
    return tmp_path / "usage.jsonl"


# ---------- settings ----------
@pytest.mark.parametrize("key", ["AI_GATEWAY_API_KEY", "LLM_MODEL_EXTRACTION", "LLM_EXTRACTION_MAX_TOKENS",
                                 "LLM_EXTRACTION_TOTAL_TIMEOUT_SECONDS", "LLM_CONNECT_TIMEOUT_SECONDS"])
def test_missing_key_fails_loudly_naming_the_key(env, monkeypatch, key):
    monkeypatch.setenv(key, "")
    with pytest.raises(llm.ConfigError, match=key):
        llm.settings()


@pytest.mark.parametrize("value", ["abc", "0", "-5"])
def test_bad_number_fails(env, monkeypatch, value):
    monkeypatch.setenv("LLM_EXTRACTION_MAX_TOKENS", value)
    with pytest.raises(llm.ConfigError, match="LLM_EXTRACTION_MAX_TOKENS"):
        llm.settings()


def test_config_error_never_contains_the_key(env, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(llm.ConfigError) as e:
        llm.settings()
    assert ENV["AI_GATEWAY_API_KEY"] not in str(e.value)


def test_settings_per_purpose(env):
    s = llm.settings()
    assert s.max_tokens == {"extraction": 16000, "phrasing": 400}
    assert s.total_timeout == {"extraction": 180.0, "phrasing": 30.0} and s.model["extraction"] == "m-extract"


# ---------- complete(): every failure is LLMUnavailable, usage logged without prompt or key ----------
class FakeClient:
    def __init__(self, outcome):
        self.outcome = outcome
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class Status402(openai.APIStatusError):
    def __init__(self, code=402):  # bypass the SDK constructor: only status_code is read
        self.status_code = code


class Timeout(openai.APITimeoutError):
    def __init__(self):
        pass


def reply(content, finish="stop"):
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)],
                           usage=usage)


def run_with(monkeypatch, outcome, purpose="extraction"):
    fake = FakeClient(outcome)
    monkeypatch.setattr(llm.openai, "OpenAI", lambda **_k: fake)
    return fake, (lambda: llm.complete(purpose, [{"role": "user", "content": "SECRET PROMPT"}]))


@pytest.mark.parametrize("outcome,match", [
    (reply(""), "empty"), (reply("   \n"), "empty"), (reply(None), "empty"),
    (SimpleNamespace(choices=[], usage=None), "empty"),
    (reply('{"a":', finish="length"), "truncated"),
    (Status402(), "402"), (Status402(500), "HTTP 500"), (Timeout(), r"Timeout \(connect 5\.0s, total 180\.0s\)"),
])
def test_failures_raise_llm_unavailable(env, monkeypatch, outcome, match):
    _, call = run_with(monkeypatch, outcome)
    with pytest.raises(llm.LLMUnavailable, match=match):
        call()


def test_ok_call_uses_purpose_settings_and_logs_usage_safely(env, monkeypatch):
    fake, call = run_with(monkeypatch, reply('{"ok": true}'))
    assert call() == '{"ok": true}'
    assert fake.kwargs["max_tokens"] == 16000 and fake.kwargs["model"] == "m-extract"
    row = json.loads(env.read_text(encoding="utf-8").splitlines()[-1])
    assert row["outcome"] == "ok" and row["total_tokens"] == 15
    text = env.read_text(encoding="utf-8")
    assert "SECRET PROMPT" not in text and ENV["AI_GATEWAY_API_KEY"] not in text


def test_usage_row_names_the_ad(env, monkeypatch):
    fake = FakeClient(reply("x"))
    monkeypatch.setattr(llm.openai, "OpenAI", lambda **_k: fake)
    llm.complete("extraction", [{"role": "user", "content": "p"}], ref="FAA:2012-02-02")
    assert json.loads(env.read_text(encoding="utf-8").splitlines()[-1])["ref"] == "FAA:2012-02-02"


def test_gateway_cost_is_logged_when_returned(env, monkeypatch):
    with_cost = reply("x")
    with_cost.usage.cost, with_cost.usage.gateway_cost, with_cost.usage.market_cost = 0.0123, 0.0123, True
    _, call = run_with(monkeypatch, with_cost)
    call()
    row = json.loads(env.read_text(encoding="utf-8").splitlines()[-1])
    assert row["cost_usd"] == 0.0123 and row["gateway_cost_usd"] == 0.0123
    assert row["market_cost_usd"] is None  # not a number: never logged as a cost
    _, call = run_with(monkeypatch, reply("y"))  # no cost in usage
    call()
    assert json.loads(env.read_text(encoding="utf-8").splitlines()[-1])["cost_usd"] is None


def test_gateway_cost_read_from_sdk_extra_fields():
    usage = SimpleNamespace(model_extra={"cost": 2.4e-05})
    assert llm._usage_number(usage, "cost") == 2.4e-05 and llm._usage_number(usage, "gateway_cost") is None


def test_phrasing_uses_its_own_limits(env, monkeypatch):
    fake, call = run_with(monkeypatch, reply("hi"), purpose="phrasing")
    call()
    assert fake.kwargs["max_tokens"] == 400 and fake.kwargs["model"] == "m-phrase"


# ---------- parse ----------
GOLDEN_2018 = STATE.available["EASA:2018-0072"].golden.model_dump()


@pytest.mark.parametrize("raw", [json.dumps(GOLDEN_2018), "```json\n" + json.dumps(GOLDEN_2018) + "\n```"])
def test_parse_accepts_plain_and_fenced(raw):
    assert extract.parse(raw, "EASA:2018-0072").applicability[0].serial_to == "1085"


@pytest.mark.parametrize("raw,exc", [("", ValueError), ("not json", ValueError), ("[1, 2]", TypeError),
                                     ("null", TypeError), ('{"applicability": []}', Exception)])
def test_parse_rejects(raw, exc):
    with pytest.raises(exc):
        extract.parse(raw, "EASA:2018-0072")


def test_parse_sets_our_ad_id_and_prefixes_bare_numbers():
    d = {**STATE.available["FAA:2012-19-01"].golden.model_dump(), "ad_number": "2012-19-01",
         "supersedes": ["2006-20-09"]}
    d["credited_compliance"][0]["ad_id"] = "2006-20-09"
    ad = extract.parse(json.dumps(d), "FAA:2012-19-01")
    assert ad.ad_number == "FAA:2012-19-01" and ad.supersedes == ["FAA:2006-20-09"]
    assert ad.credited_compliance[0].ad_id == "FAA:2006-20-09"
    d["supersedes"] = ["see paragraph (b)"]  # not an AD number: left as is, so validation decides
    assert extract.parse(json.dumps(d), "FAA:2012-19-01").supersedes == ["see paragraph (b)"]


# ---------- compare ----------
def test_compare_identical_is_full_agreement():
    g = STATE.available["FAA:2004-15-18"].golden
    cmp = extract.compare(g, g)
    assert all(f["agree"] for f in cmp.values()) and extract.agreement(cmp) == 1.0


def test_compare_lists_missing_and_extra():
    g = STATE.available["FAA:2012-02-02"].golden
    worse = g.model_copy(update={"applicability": g.applicability[:3], "supersedes": ["FAA:2000-00-00"]})
    cmp = extract.compare(worse, g)
    assert cmp["applicability"]["missing"] == ["('172S', False, '172S10490', '172S11073')"]
    assert cmp["supersedes"] == {"agree": False, "golden": 1, "extracted": 1, "matched": 0,
                                 "missing": ["FAA:2008-03-02"], "extra": ["FAA:2000-00-00"]}
    assert extract.agreement(cmp) < 1.0


# ---------- the real cache (one live run on the 8 golden ADs) ----------
EXPECTED_USABLE = {"EASA:2018-0072": True, "EASA:2024-0152R1": True, "FAA:2004-15-18": True,
                   "FAA:2006-12-07": False, "FAA:2006-20-09": False, "FAA:2012-02-02": True,
                   "FAA:2012-19-01": False, "FAA:2013-03-15": True}


def test_cache_has_every_golden_ad_and_known_agreement():
    got = {}
    for ad_id, ad in STATE.available.items():
        r = extract.evaluate_record(extract.run(ad, [], live=False), ad)
        assert r["ok"] and r["quotes_rejected"] == 0, ad_id  # every extracted quote is in the text
        got[ad_id] = r["usable"]
    assert got == EXPECTED_USABLE


def test_demo_mode_without_cache_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "CACHE_DIR", tmp_path)
    with pytest.raises(llm.LLMUnavailable, match="no cached extraction"):
        extract.run(STATE.available["FAA:2012-02-02"], [], live=False)


def test_failed_live_call_never_overwrites_the_cache(tmp_path, monkeypatch):
    src = extract.cache_path("FAA:2012-02-02")
    monkeypatch.setattr(extract, "CACHE_DIR", tmp_path)
    extract.cache_path("FAA:2012-02-02").write_bytes(src.read_bytes())
    monkeypatch.setattr(extract.llm, "settings", lambda: SimpleNamespace(model={"extraction": "m"}))

    def fail(*_a, **_k):
        raise llm.LLMUnavailable("budget used up (HTTP 402)")
    monkeypatch.setattr(extract.llm, "complete", fail)
    record = extract.run(STATE.available["FAA:2012-02-02"], [], live=True)
    assert record["fallback_reason"] == "llm: budget used up (HTTP 402)" and record["raw"]
    assert extract.cache_path("FAA:2012-02-02").read_bytes() == src.read_bytes()


# ---------- values from the extraction, quotes from golden ----------
def test_with_golden_quotes_takes_values_from_extraction_and_quotes_from_golden():
    golden = STATE.available["FAA:2012-02-02"].golden
    record = extract.run(STATE.available["FAA:2012-02-02"], [], live=False)
    extracted = extract.parse(record["raw"], "FAA:2012-02-02")
    assert extracted.applicability[3].quote != golden.applicability[3].quote  # "(4) Group 4: …" vs "Group 4: …"
    merged = extract.with_golden_quotes(extracted, golden)
    assert [r.serial_to for r in merged.applicability] == [r.serial_to for r in extracted.applicability]
    assert [r.quote for r in merged.applicability] == [r.quote for r in golden.applicability]
    assert merged.field_quotes == golden.field_quotes


def test_with_golden_quotes_refuses_an_item_golden_does_not_have():
    golden = STATE.available["FAA:2012-02-02"].golden
    odd = golden.applicability[0].model_copy(update={"serial_to": "17289999"})
    with pytest.raises(ValueError, match="no golden counterpart"):
        extract.with_golden_quotes(golden.model_copy(update={"applicability": [odd]}), golden)


def test_credit_quote_and_occurrence_come_from_golden():
    golden = STATE.available["FAA:2012-19-01"].golden
    llm_credit = golden.credited_compliance[0].model_copy(update={"quote": "no further action is required.",
                                                                  "occurrence": 1, "paragraph": None})
    merged = extract.with_golden_quotes(golden.model_copy(update={"credited_compliance": [llm_credit]}), golden)
    assert merged.credited_compliance[0] == golden.credited_compliance[0]


# ---------- ingest: extraction decides only when it is fully validated and agrees ----------
@pytest.fixture
def demo():
    client.post("/demo/reset")
    yield
    client.post("/demo/reset")


def test_ingest_uses_the_agreeing_extraction(demo):
    b = client.post(INGEST_2012_02_02).json()
    assert b["source"] == "cache" and b["extraction"]["used"] is True and b["extraction"]["misses"] == []
    assert b["extraction"]["citations_from"] == "golden"
    assert b["extraction"]["reason"] == "values from the extraction; citations from golden (human-checked)"
    golden = STATE.available["FAA:2012-02-02"].golden
    assert all(c["origin"] == "golden" for c in b["citations"])
    assert {c["quote"] for c in b["citations"]} <= {r.quote for r in golden.applicability} | {
        q for qs in golden.field_quotes.values() for q in qs}
    used = api.STATE.ads["FAA:2012-02-02"].golden
    assert [r.quote for r in used.applicability] == [r.quote for r in golden.applicability]
    assert used.compliance_time_text == golden.compliance_time_text  # no LLM-written text in answers
    due = client.get("/aircraft/DEMO-01/status").json()["applicable_ads"]
    [g4] = [x for x in due if x["ad_id"] == "FAA:2012-02-02"]
    assert g4["due"]["citation"]["quote"].endswith("inspect the fuel return line assembly (Cessna P/N 0500118-49) "
                                                   "for chafing.")  # the full sentence, not a cut quote
    assert b["changes"]["aircraft_status_changed"] == [{"aircraft_id": "DEMO-01", "from": "green", "to": "red"}]
    assert api.STATE.ads["FAA:2012-02-02"].golden_file == "data/cache/extractions/FAA-2012-02-02.json"


def test_ingest_falls_back_to_golden_without_cache(demo, tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "CACHE_DIR", tmp_path)
    b = client.post(INGEST_2012_02_02).json()
    assert b["source"] == "golden" and b["extraction"]["used"] is False
    assert "no cached extraction" in b["extraction"]["reason"]
    assert b["changes"]["aircraft_status_changed"][0]["to"] == "red"  # golden still decides


def test_ingest_lists_every_miss_and_golden_decides(demo, monkeypatch):
    real = extract.evaluate_record

    def disagree(record, ad):
        r = real(record, ad)
        r["fields"]["supersedes"] = {"agree": False, "golden": 1, "extracted": 0, "matched": 0,
                                     "missing": ["FAA:2008-03-02"], "extra": []}
        return {**r, "usable": False}
    monkeypatch.setattr(extract, "evaluate_record", disagree)
    b = client.post(INGEST_2012_02_02).json()
    assert b["source"] == "golden" and b["extraction"]["used"] is False
    assert b["extraction"]["misses"] == ["supersedes: missing ['FAA:2008-03-02']; extra []"]
    assert [f["check"] for f in b["rejected_fields"]] == ["disagrees with golden"]
    assert "FAA:2012-02-02" in api.STATE.ads  # golden was valid, so the AD is loaded
    assert api.STATE.ads["FAA:2012-02-02"].golden_file == "data/golden/FAA-2012-02-02.json"
