"""Agent extraction: AD text → golden-shaped candidate (LLM) → schema + quote validation → field-by-field
comparison with the human-checked golden file. Pipeline, not an action. Every extracted field is a HYPOTHESIS
until its quote is found in the text; it decides nothing unless it also agrees with golden (see api.ingest)."""
import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app import llm, store
from app.ontology import GoldenAD, LoadedAD, LogbookRow

log = logging.getLogger("adbrain.extract")

CACHE_DIR = store.DATA / "cache" / "extractions"
PROMPT_VERSION = "extract-v2"
BARE_AD_NUMBER_RE = re.compile(r"^\d{2,4}-\d{2,4}(-\d{2})?(R\d+)?$")  # 2008-03-02 · 2024-0152R1
FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
COMPARED_FIELDS = ("effective_date", "supersedes", "revises", "applicability", "conditions", "credited_compliance",
                   "not_evaluated")

SYSTEM = """You extract fields from one airworthiness directive (AD) into JSON. You are filling the inputs of a
deterministic decision model: you never decide applicability yourself, you copy what the text says.
Rules:
- Return ONLY one JSON object, no prose, no code fences, in the shape of TEMPLATE below.
- Every value carries a verbatim quote copied character for character from the AD text (whitespace may differ).
  Never paraphrase a quote. A quote must not cross a word hyphenated across two lines: end it before the split.
- If a sentence appears more than once, make the quote unique (include the paragraph heading).
- applicability: one row per model and serial range or single serial. serial_from/serial_to null = all serials.
  For engine ADs that name a series (e.g. "IO-360 series"), set series=true and model to the series ("IO-360");
  "(L)IO-360" means two rows, IO-360 and LIO-360.
- Fix OCR errors in values only (e.g. "l72S" -> "172S"); quotes keep the text as printed.
- conditions: facts the AD's applicability depends on (equipment/part installed, modification embodied, serial
  listed in a service bulletin). fact must be one of FACT_KEYS; if none fits, use "OTHER:<short name>".
- not_evaluated: clauses that exempt aircraft by manufacture/overhaul date or history, which this system cannot check.
- credited_compliance: paragraphs saying previous compliance with another AD satisfies this one.
- AD ids (ad_number, supersedes, revises, credited_compliance.ad_id) as AUTHORITY:NUMBER, e.g. "FAA:2008-03-02".
- Unknown or absent: empty list or null. Do not invent."""


def fact_vocabulary(golden: dict[str, LoadedAD], logbook: list[LogbookRow]) -> list[str]:
    return sorted({c.fact for ad in golden.values() for c in ad.golden.conditions}
                  | {r.fact for r in logbook if r.fact})


def build_messages(ad_id: str, text: str, facts: list[str]) -> list[dict[str, str]]:
    template = (store.GOLDEN_DIR / store.GOLDEN_TEMPLATE).read_text(encoding="utf-8")
    user = (f"AD id: {ad_id}\nFACT_KEYS: {json.dumps(facts)}\nTEMPLATE:\n{template}\n\n"
            f"AD TEXT (between the markers):\n<<<\n{text}\n>>>")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def parse(raw: str, ad_id: str) -> GoldenAD:
    """LLM text → validated GoldenAD. Raises ValueError (bad JSON), TypeError (not an object) or ValidationError (bad shape).
    The AD id is ours, not the LLM's: it is set from the request (the LLM may drop the authority prefix)."""
    m = FENCE_RE.match(raw)
    data = json.loads(m[1] if m else raw)
    if not isinstance(data, dict):
        raise TypeError(f"expected a JSON object, got {type(data).__name__}")
    if data.get("ad_number") != ad_id:
        log.info("extraction %s: LLM ad_number %r replaced by the requested id", ad_id, data.get("ad_number"))
    authority = ad_id.split(":")[0]

    def prefixed(x: object) -> object:  # a bare AD number belongs to this AD's authority (FAA supersedes FAA)
        return f"{authority}:{x}" if isinstance(x, str) and BARE_AD_NUMBER_RE.match(x) else x

    for key in ("supersedes", "revises"):
        if isinstance(data.get(key), list):
            data[key] = [prefixed(x) for x in data[key]]
    for c in data.get("credited_compliance") or []:
        if isinstance(c, dict):
            c["ad_id"] = prefixed(c.get("ad_id"))
    return GoldenAD.model_validate({**data, "ad_number": ad_id})


def _keys(ad: GoldenAD, name: str) -> set:
    if name == "effective_date":
        return {ad.effective_date}
    if name in ("supersedes", "revises"):
        return set(getattr(ad, name))
    if name == "applicability":
        return {(r.model.upper(), r.series, r.serial_from, r.serial_to) for r in ad.applicability}
    if name == "conditions":
        return {(c.kind, c.fact, c.applies_when) for c in ad.conditions}
    if name == "credited_compliance":
        return {c.ad_id for c in ad.credited_compliance}
    if name == "not_evaluated":
        return {store.collapse(n.quote) for n in ad.not_evaluated}
    raise KeyError(name)


def compare(extracted: GoldenAD, golden: GoldenAD) -> dict[str, dict]:
    """Per field: golden vs extracted as sets; agree = equal sets. Misses are listed, never hidden."""
    out = {}
    for name in COMPARED_FIELDS:
        g, e = _keys(golden, name), _keys(extracted, name)
        out[name] = {"agree": g == e, "golden": len(g), "extracted": len(e), "matched": len(g & e),
                     "missing": sorted(map(str, g - e)), "extra": sorted(map(str, e - g))}
    return out


def agreement(cmp: dict[str, dict]) -> float:
    """Share of golden items matched, over all compared fields (an extra item counts as a miss too)."""
    golden = sum(f["golden"] for f in cmp.values())
    extra = sum(len(f["extra"]) for f in cmp.values())
    matched = sum(f["matched"] for f in cmp.values())
    return matched / (golden + extra) if golden + extra else 1.0


def with_golden_quotes(extracted: GoldenAD, golden: GoldenAD) -> GoldenAD:
    """The record that decides when the extraction is used: the compared values come from the extraction, every
    quote and every free text from the human-checked golden record. Raises ValueError if an extracted item has no
    golden counterpart (cannot happen when the extraction agrees with golden; checked anyway)."""
    def pick(items, golden_items, key, name):
        by_key = {key(g): g for g in golden_items}
        out = []
        for item in items:
            if key(item) not in by_key:
                raise ValueError(f"{name}: extracted item {key(item)} has no golden counterpart")
            out.append(item.model_copy(update={k: getattr(by_key[key(item)], k)
                                               for k in ("quote", "occurrence", "paragraph") if hasattr(item, k)}))
        return out

    return golden.model_copy(update={
        "effective_date": extracted.effective_date, "supersedes": extracted.supersedes,
        "revises": extracted.revises,
        "applicability": pick(extracted.applicability, golden.applicability,
                              lambda r: (r.model.upper(), r.series, r.serial_from, r.serial_to), "applicability"),
        "conditions": pick(extracted.conditions, golden.conditions,
                           lambda c: (c.kind, c.fact, c.applies_when), "conditions"),
        "credited_compliance": pick(extracted.credited_compliance, golden.credited_compliance,
                                    lambda c: c.ad_id, "credited_compliance"),
        "not_evaluated": pick(extracted.not_evaluated, golden.not_evaluated,
                              lambda n: store.collapse(n.quote), "not_evaluated"),
    })


def cache_path(ad_id: str) -> Path:
    return CACHE_DIR / f"{ad_id.replace(':', '-')}.json"


def cache_ref(ad_id: str) -> str:
    """The cache file as stored in LoadedAD.golden_file: repo-relative, or absolute if outside the repo (tests)."""
    path = cache_path(ad_id).resolve()
    return path.relative_to(store.REPO).as_posix() if path.is_relative_to(store.REPO) else str(path)


def sha256(text: str) -> str:
    return hashlib.sha256(store.collapse(text).encode("utf-8")).hexdigest()


def run(ad: LoadedAD, facts: list[str], live: bool) -> dict:
    """Extract one AD. live=False reads only the cache (DEMO_MODE). Returns the cache record."""
    path = cache_path(ad.ad_id)
    text = store.ad_text(ad)
    if not live:
        if not path.is_file():
            raise llm.LLMUnavailable(f"no cached extraction for {ad.ad_id} (demo mode)")
        return json.loads(path.read_text(encoding="utf-8"))
    messages = build_messages(ad.ad_id, text, facts)
    s = llm.settings()
    record = {"ad_id": ad.ad_id, "model": s.model["extraction"], "prompt_version": PROMPT_VERSION,
              "prompt_sha256": hashlib.sha256(json.dumps(messages).encode("utf-8")).hexdigest(),
              "text_sha256": sha256(text), "extracted_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "raw": None, "parsed": None, "error": None}
    try:
        record["raw"] = llm.complete("extraction", messages, s, ref=ad.ad_id)
        record["parsed"] = parse(record["raw"], ad.ad_id).model_dump()
    except llm.LLMUnavailable as e:
        record["error"] = f"llm: {e}"
    except (ValueError, TypeError, ValidationError) as e:
        record["error"] = f"invalid output: {str(e)[:500]}"
    if record["error"]:
        log.warning("extraction %s failed: %s", ad.ad_id, record["error"])
        if path.is_file():  # never overwrite a cached extraction with a failure: fall back to it
            cached = json.loads(path.read_text(encoding="utf-8"))
            return {**cached, "fallback_reason": record["error"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def evaluate_record(record: dict, ad: LoadedAD) -> dict:
    """Quote check + comparison with golden for one cache record."""
    if not record.get("raw"):
        return {"ad_id": ad.ad_id, "ok": False, "error": record.get("error") or "no LLM output"}
    try:  # re-parse the raw output every time: parsing is deterministic and may have been fixed since
        extracted = parse(record["raw"], ad.ad_id)
    except (ValueError, TypeError, ValidationError) as e:
        return {"ad_id": ad.ad_id, "ok": False, "error": f"invalid output: {str(e)[:500]}"}
    checks = store.field_checks(ad.model_copy(update={"golden": extracted}), store.ad_text(ad))
    rejected = [c for c in checks if c.check != store.QUOTE_FOUND]
    cmp = compare(extracted, ad.golden)
    return {"ad_id": ad.ad_id, "ok": True, "quotes_checked": len(checks), "quotes_rejected": len(rejected),
            "rejected": [f"{c.field}: {c.quote[:90]!r}" for c in rejected],
            "fields": cmp, "agreement": agreement(cmp),
            "usable": not rejected and all(f["agree"] for f in cmp.values())}
