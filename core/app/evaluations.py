"""Evaluation records: every computed aircraft status is recorded with the rule version that decided it, a hash of
its inputs and the inputs themselves, in an append-only log. Replay recomputes from the recorded inputs with the
current rules and says whether the decision is the same and which part of the rule version changed.
An evaluation is a computed result, not a DECISION (a DECISION is made by a person with a role)."""
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app import rules, store
from app.ontology import Aircraft, LoadedAD, LogbookRow

log = logging.getLogger("adbrain.evaluations")

RULES_PY = Path(rules.__file__).resolve()
RUNTIME_DIR = store.DATA / "runtime"
LOG_FILE = RUNTIME_DIR / "evaluations.jsonl"
ID_PREFIX = "EV-"


def file_sha256(path: Path) -> str:
    """sha256 of a text file with line endings normalised to LF: same hash on Windows and macOS checkouts."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def canonical_sha256(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def golden_path(ad: LoadedAD) -> Path:
    p = Path(ad.golden_file)
    return p if p.is_absolute() else store.REPO / p


def rules_version(ads: list[LoadedAD]) -> dict:
    """rules.py hash + every active AD's id (which carries its revision, e.g. EASA:2024-0152R1) and golden hash."""
    manifest = {"rules_py": file_sha256(RULES_PY),
                "ads": sorted(({"ad_id": ad.ad_id, "sha256": file_sha256(golden_path(ad))} for ad in ads),
                              key=lambda x: x["ad_id"])}
    return {**manifest, "id": canonical_sha256(manifest)}


def snapshot_inputs(aircraft: Aircraft, logbook: list[LogbookRow], as_of: date) -> dict:
    rows = sorted((r.model_dump() for r in logbook if r.aircraft_id == aircraft.id), key=lambda r: r["id"])
    return {"aircraft": aircraft.model_dump(), "logbook": rows, "as_of_date": as_of.isoformat()}


def decision_of(a: rules.Assessment) -> dict:
    """What 'the same decision' means: the status and every per-AD verdict."""
    return {"status": a.status, "verdicts": {k: r.verdict for k, r in sorted(a.results.items())}}


def decide(inputs: dict, ads: list[LoadedAD]) -> rules.Assessment:
    aircraft = Aircraft.model_validate(inputs["aircraft"])
    logbook = [LogbookRow.model_validate(r) for r in inputs["logbook"]]
    return rules.assess(aircraft, ads, logbook, date.fromisoformat(inputs["as_of_date"]))


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Replay:
    record: dict
    after: dict
    rules_version_after: dict
    new_record: dict

    @property
    def same(self) -> bool:
        return decision_of_record(self.record) == self.after

    def changed(self) -> dict:
        before, after = self.record["rules_version"], self.rules_version_after
        old = {a["ad_id"]: a["sha256"] for a in before["ads"]}
        new = {a["ad_id"]: a["sha256"] for a in after["ads"]}
        return {"rules_version": before["id"] != after["id"], "rules_py": before["rules_py"] != after["rules_py"],
                "ads_added": sorted(set(new) - set(old)), "ads_removed": sorted(set(old) - set(new)),
                "ads_changed": sorted(k for k in set(old) & set(new) if old[k] != new[k])}


def decision_of_record(record: dict) -> dict:
    return {"status": record["status"], "verdicts": record["verdicts"]}


class EvaluationLog:
    """Append-only: records and reset markers are only ever appended, in memory and to a JSONL file.
    A record with the same rules version and inputs as an earlier one is not written again (UI polling)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.records: dict[str, dict] = {}
        self._by_key: dict[tuple[str, str], str] = {}
        self._next = 1
        if path is not None and path.is_file():
            self._load(path)

    def _load(self, path: Path) -> None:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                log.warning("%s line %d: not JSON, skipped (the log is append-only: fix by hand)", path.name, n)
                continue
            if row.get("event") == "evaluation":
                self._index(row)

    def _index(self, row: dict) -> None:
        self.records[row["id"]] = row
        self._by_key[(row["rules_version"]["id"], row["inputs_hash"])] = row["id"]
        self._next = max(self._next, int(row["id"].removeprefix(ID_PREFIX)) + 1)

    def _append(self, row: dict) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            log.exception("could not append to %s; the record stays in memory only", self.path)

    def record(self, a: rules.Assessment, inputs: dict, ads: list[LoadedAD], replay_of: str | None = None) -> dict:
        version, inputs_hash = rules_version(ads), canonical_sha256(inputs)
        existing = self._by_key.get((version["id"], inputs_hash))
        if existing is not None:
            return self.records[existing]
        row = {"event": "evaluation", "id": f"{ID_PREFIX}{self._next:04d}", "aircraft_id": a.aircraft.id,
               "as_of_date": inputs["as_of_date"], **decision_of(a), "rule_ids_fired": a.rule_ids,
               "rules_version": version, "inputs_hash": inputs_hash, "inputs": inputs,
               "decided_at": now_utc(), "replay_of": replay_of}
        self._index(row)
        self._append(row)
        return row

    def mark_reset(self) -> None:
        self._append({"event": "reset", "at": now_utc()})

    def replay(self, record: dict, ads: list[LoadedAD]) -> Replay:
        """Same recorded inputs, current rules.py and current active ADs. Old code is not re-run: if rules.py
        changed, the replay says so and decides with the current code."""
        if canonical_sha256(record["inputs"]) != record["inputs_hash"]:
            raise ValueError(f"{record['id']}: recorded inputs do not match their hash (log edited?)")
        a = decide(record["inputs"], ads)
        new = self.record(a, record["inputs"], ads, replay_of=record["id"])
        return Replay(record, decision_of(a), rules_version(ads), new)
