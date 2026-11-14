"""In-memory ontology loaded from data/. Fails loudly on bad data: the golden set is human-checked,
so a missing quote or title is a data bug to fix, not to skip."""
import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.ontology import Aircraft, GoldenAD, LoadedAD, LogbookRow, ValidatedField

log = logging.getLogger("adbrain.store")

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
GOLDEN_DIR = DATA / "golden"
GOLDEN_TEMPLATE = "TEMPLATE.json"
GOLDEN_DRAFTS_DIR = GOLDEN_DIR / "drafts"  # unchecked drafts: never loaded by load()
ADS_DIR = DATA / "raw" / "ads"
INDEX_MD = DATA / "raw" / "INDEX.md"
SOURCES_CSV = ADS_DIR / "SOURCES.csv"
FLEET_CSV = DATA / "registry" / "italian-fleet.csv"
REAL_CSV = DATA / "registry" / "demo-aircraft.csv"
LOGBOOK_CSV = DATA / "registry" / "demo-logbooks.csv"
AD_ID_PREFIXES = ("FAA:", "EASA:")
CSV_TRUE, CSV_FALSE = "true", "false"
# Demo moment 2: this AD is ingested live, so the demo state starts without it.
NOT_LOADED_AT_RESET = frozenset({"FAA:2012-02-02"})
QUOTE_FOUND, QUOTE_NOT_FOUND = "quote found in text", "quote not found in text"


class DataError(Exception):
    """A data file is missing, malformed or inconsistent."""


@dataclass
class State:
    available: dict[str, LoadedAD]  # every golden AD (the demo-mode "cache")
    ads: dict[str, LoadedAD]  # active: loaded at reset or ingested since
    aircraft: dict[str, Aircraft]
    logbook: list[LogbookRow]
    ingest_runs: int = 0


def ad_text(ad: LoadedAD) -> str:
    return (REPO / ad.file).read_text(encoding="utf-8")


def field_checks(ad: LoadedAD, text: str) -> list[ValidatedField]:
    """Every field of a golden AD with its quote, each checked against the AD text."""
    g, fq = ad.golden, ad.golden.field_quotes
    items: list[tuple[str, object, list[str]]] = [
        ("applicability", {"model": r.model, "serial_from": r.serial_from, "serial_to": r.serial_to}, [r.quote])
        for r in g.applicability]
    items += [("conditions", {"kind": c.kind, "fact": c.fact, "applies_when": c.applies_when, "value": c.value},
               [c.quote]) for c in g.conditions]
    items.append(("effective_date", g.effective_date, fq.get("effective_date", [])))
    if g.supersedes:
        items.append(("supersedes", g.supersedes, fq.get("supersedes", [])))
    if g.revises:
        items.append(("revises", g.revises, fq.get("revises", [])))
    items.append(("compliance_time", g.compliance_time_text, fq.get("compliance_time_text", [])))
    items += [("not_evaluated", n.clause, [n.quote]) for n in g.not_evaluated]
    out = []
    for name, value, quotes in items:
        for q in quotes or [""]:  # a value with no quote is rejected, never silently accepted
            found = bool(q) and quote_count(q, text) > 0
            out.append(ValidatedField(field=name, value=value, quote=q, file=ad.file, occurrence=1,
                                      check=QUOTE_FOUND if found else QUOTE_NOT_FOUND))
    for c in g.credited_compliance:
        found = quote_count(c.quote, text) >= c.occurrence
        out.append(ValidatedField(field="credited_compliance", value=c.ad_id, quote=c.quote, file=ad.file,
                                  occurrence=c.occurrence, check=QUOTE_FOUND if found else QUOTE_NOT_FOUND))
    return out


def collapse(text: str) -> str:
    """contract/README.md: quotes match after collapsing every whitespace run to one space."""
    return " ".join(text.split())


def parse_index_titles(markdown: str) -> dict[str, str]:
    """AD id → Subject column of the tables in data/raw/INDEX.md."""
    titles = {}
    for line in markdown.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].startswith(AD_ID_PREFIXES):
            if not cells[1]:
                raise DataError(f"INDEX.md: empty Subject for {cells[0]}")
            titles[cells[0]] = cells[1]
    return titles


def quote_count(quote: str, text: str) -> int:
    return collapse(text).count(collapse(quote))


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise DataError(f"{path.name}: missing columns {sorted(missing)}")
        return list(reader)


def _bool(value: str, where: str) -> bool:
    if value not in (CSV_TRUE, CSV_FALSE):
        raise DataError(f"{where}: expected {CSV_TRUE}/{CSV_FALSE}, got {value!r}")
    return value == CSV_TRUE


def load_ads(golden_dir: Path | None = None) -> dict[str, LoadedAD]:
    """Golden ADs in golden_dir (default GOLDEN_DIR; not recursive, so drafts/ is never loaded)."""
    titles = parse_index_titles(INDEX_MD.read_text(encoding="utf-8"))
    sources = {r["id"]: r for r in _read_csv(SOURCES_CSV, {"id", "file", "source_url"})}
    ads: dict[str, LoadedAD] = {}
    for path in sorted((golden_dir or GOLDEN_DIR).glob("*.json")):
        if path.name == GOLDEN_TEMPLATE:
            continue
        try:
            golden = GoldenAD.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (ValidationError, json.JSONDecodeError) as e:
            raise DataError(f"{path.name}: {e}") from e
        ad_id = golden.ad_number
        if ad_id not in titles:
            raise DataError(f"{ad_id}: no Subject in INDEX.md")
        if ad_id not in sources:
            raise DataError(f"{ad_id}: not in SOURCES.csv")
        txt = ADS_DIR / sources[ad_id]["file"]
        if not txt.is_file():
            raise DataError(f"{ad_id}: {txt.name} missing")
        text = txt.read_text(encoding="utf-8")
        quotes = [r.quote for r in golden.applicability] + [c.quote for c in golden.conditions]
        quotes += [q for qs in golden.field_quotes.values() for q in qs]
        quotes += [n.quote for n in golden.not_evaluated]
        for q in quotes:
            n = quote_count(q, text)
            if n == 0:
                raise DataError(f"{ad_id}: quote not found in {txt.name}: {q[:80]!r}")
            if n > 1:
                log.warning("%s: quote found %d times, citing the first: %r", ad_id, n, q[:80])
        for c in golden.credited_compliance:
            if quote_count(c.quote, text) < c.occurrence:
                raise DataError(f"{ad_id}: credit quote not found {c.occurrence} time(s) in {txt.name}: {c.quote[:80]!r}")
        golden_file = path.relative_to(REPO).as_posix() if path.is_relative_to(REPO) else str(path)
        ads[ad_id] = LoadedAD(golden=golden, title=titles[ad_id], file=txt.relative_to(REPO).as_posix(),
                              golden_file=golden_file,
                              source_url=sources[ad_id]["source_url"])
    return ads


def load_aircraft() -> dict[str, Aircraft]:
    planes = []
    for r in _read_csv(FLEET_CSV, {"mark", "synthetic", "base", "model", "serial", "engine_model", "arc_review_due"}):
        planes.append(Aircraft(id=r["mark"], registration=r["mark"], model=r["model"], serial=r["serial"],
                               engine_model=r["engine_model"], synthetic=_bool(r["synthetic"], r["mark"]),
                               base=r["base"] or None, arc_review_due=r["arc_review_due"] or None))
    for r in _read_csv(REAL_CSV, {"registration", "serial", "model", "engine_model"}):
        planes.append(Aircraft(id=r["registration"], registration=r["registration"], model=r["model"],
                               serial=r["serial"], engine_model=r["engine_model"], synthetic=False,
                               base=None, arc_review_due=None))
    by_id = {a.id: a for a in planes}
    if len(by_id) != len(planes):
        raise DataError("duplicate aircraft id")
    return by_id


def load_logbook(aircraft: dict[str, Aircraft]) -> list[LogbookRow]:
    rows = []
    for r in _read_csv(LOGBOOK_CSV, {"id", "aircraft_id", "subject_id", "ad_id", "date", "kind", "text",
                                     "synthetic", "fact", "value"}):
        try:
            row = LogbookRow.model_validate({**r, "fact": r["fact"] or None, "value": r["value"] or None})
        except ValidationError as e:
            raise DataError(f"logbook {r.get('id')}: {e}") from e
        if row.aircraft_id not in aircraft:
            raise DataError(f"logbook {row.id}: unknown aircraft {row.aircraft_id}")
        if not row.ad_id.startswith(AD_ID_PREFIXES):
            raise DataError(f"logbook {row.id}: bad AD id {row.ad_id!r}")
        if row.kind == "observation" and (row.fact is None or row.value is None):
            raise DataError(f"logbook {row.id}: an observation needs fact and value")
        rows.append(row)
    return rows


def load() -> State:
    aircraft = load_aircraft()
    available = load_ads()
    missing = NOT_LOADED_AT_RESET - set(available)
    if missing:
        raise DataError(f"NOT_LOADED_AT_RESET names ADs with no golden file: {sorted(missing)}")
    ads = {k: v for k, v in available.items() if k not in NOT_LOADED_AT_RESET}
    return State(available=available, ads=ads, aircraft=aircraft, logbook=load_logbook(aircraft))
