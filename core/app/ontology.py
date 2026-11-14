"""Shared shapes from contract/README.md ("Shared shapes"). The UI generates its types from these."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EpistemicClass = Literal["REGULATION", "DECISION", "OBSERVATION", "HYPOTHESIS", "QUESTION"]
Status = Literal["active", "superseded", "contested"]
AircraftStatus = Literal["green", "amber", "red", "no_records"]
Urgency = Literal["low", "medium", "high", "overdue"]
LinkType = Literal[
    "supersedes", "revises", "appliesTo", "hasInstalled",
    "satisfies", "madeBy", "justifiedBy", "contradicts",
]


class Citation(BaseModel):
    """An exact AD sentence. `quote` matches `file` after collapsing whitespace; `occurrence` = which match (1 = first)."""
    model_config = ConfigDict(extra="forbid")
    ad_id: str
    quote: str = Field(min_length=1)
    file: str
    occurrence: int = Field(ge=1)
    source_url: str


class ReasoningStep(BaseModel):
    """One graph edge: object → link → object. `derived` = inferred link (drawn dashed)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: str = Field(alias="from")
    link: LinkType
    to: str
    derived: bool
    note: str


class Error(BaseModel):
    """Every error body. `error_code` is stable; `message` is for humans."""
    model_config = ConfigDict(extra="forbid")
    error_code: str
    message: str
    details: dict = {}


# ---------- Inputs, validated at load (data/golden/*.json, data/registry/*.csv) ----------

FactValue = Literal["yes", "no", "embodied", "not_embodied"]
OPPOSITE: dict[str, str] = {"yes": "no", "no": "yes", "embodied": "not_embodied", "not_embodied": "embodied"}


class GoldenApplicability(BaseModel):
    """One applicability row: model + serial range. serial_from/to None = all serial numbers."""
    model: str = Field(min_length=1)
    serial_from: str | None
    serial_to: str | None
    series: bool = False  # True: `model` is an engine series ('IO-360' matches 'IO-360-L2A')
    quote: str = Field(min_length=1)


class GoldenCondition(BaseModel):
    """The AD applies only if logbook fact `fact` has value `applies_when` (all conditions AND)."""
    kind: Literal["equipment_installed", "modification_not_embodied", "part_installed", "serial_listed"]
    fact: str = Field(min_length=1)
    applies_when: FactValue
    value: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class NotEvaluated(BaseModel):
    """A clause of the AD the rules do not evaluate. Shown in every answer where the AD applies."""
    clause: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class CreditedCompliance(BaseModel):
    """Compliance with `ad_id` (e.g. a superseded AD) satisfies this AD."""
    ad_id: str = Field(pattern=r"^(FAA|EASA):\S+$")
    quote: str = Field(min_length=1)


class GoldenAD(BaseModel):
    """Human-checked AD record (data/golden/<file>.json)."""
    ad_number: str = Field(pattern=r"^(FAA|EASA):\S+$")
    effective_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    supersedes: list[str] = []
    revises: list[str] = []
    applicability: list[GoldenApplicability] = Field(min_length=1)
    conditions: list[GoldenCondition] = []
    not_evaluated: list[NotEvaluated] = []
    credited_compliance: list[CreditedCompliance] = []
    compliance_time_text: str
    field_quotes: dict[str, list[str]] = {}


class LogbookRow(BaseModel):
    """A synthetic logbook entry: a compliance record or an observation of one fact."""
    id: str = Field(min_length=1)
    aircraft_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    ad_id: str
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    kind: Literal["compliance", "observation"]
    text: str
    fact: str | None = None
    value: FactValue | None = None


class LoadedAD(BaseModel):
    """A golden AD plus what the store adds: title (INDEX.md), file, source_url (SOURCES.csv)."""
    golden: GoldenAD
    title: str
    file: str  # repo-relative, as in Citation.file
    source_url: str

    @property
    def ad_id(self) -> str:
        return self.golden.ad_number

    def cite(self, quote: str) -> Citation:
        # ponytail: occurrence 1 — the store checks every golden quote is found; golden quotes are unique.
        return Citation(ad_id=self.ad_id, quote=quote, file=self.file, occurrence=1, source_url=self.source_url)


# ---------- Contract objects (contract/README.md, "Object types") ----------

class Aircraft(BaseModel):
    id: str
    registration: str
    model: str
    serial: str
    engine_model: str
    synthetic: bool
    base: str | None
    arc_review_due: str | None


class AirworthinessDirective(BaseModel):
    ad_id: str
    authority: Literal["FAA", "EASA"]
    title: str
    effective_date: str
    status: Status
    supersedes: list[str]
    superseded_by: str | None
    revises: str | None
    source_url: str
    file: str


class Question(BaseModel):
    """An unknown that blocks a sign-off. deadline/days_left/urgency are None for real aircraft
    (no ARC review date in this system)."""
    id: str
    text: str
    aircraft_id: str
    ad_id: str
    blocks: str
    deadline: str | None
    deadline_driver: str | None
    days_left: int | None
    urgency: Urgency | None
    epistemic_class: Literal["QUESTION"] = "QUESTION"
    status: Status = "active"
    synthetic: bool
    answer_with: str = "AnswerQuestion"
    citations: list[Citation]


class ComplianceState(BaseModel):
    state: Literal["no_record", "complied"]
    record_id: str | None


class Due(BaseModel):
    text: str
    citation: Citation | None
    overdue: bool | None  # None for real aircraft: no records, so no judgement


class ApplicableAD(BaseModel):
    ad_id: str
    title: str
    epistemic_class: EpistemicClass = "REGULATION"
    status: Status
    applies_because: str
    compliance: ComplianceState
    due: Due
    citations: list[Citation]


class AircraftStatusResponse(BaseModel):
    """Q1 — GET /aircraft/{id}/status."""
    aircraft: Aircraft
    status: AircraftStatus
    summary: str
    summary_source: Literal["template", "llm"]
    applicable_ads: list[ApplicableAD]
    superseded_ads: list[str]
    open_questions: list[Question]
    hypotheses: list[dict]
    citations: list[Citation]
    reasoning_path: list[ReasoningStep]
    computed_at: str


class AffectedAircraft(BaseModel):
    aircraft_id: str
    model: str
    serial: str
    via: Literal["serial_range", "all_serials", "installed_engine"]
    why: str
    status_now: AircraftStatus


class NotAffected(BaseModel):
    aircraft_id: str
    why: str


class AffectedAircraftResponse(BaseModel):
    """Q2 — GET /ads/{ad_id}/affected-aircraft."""
    ad: AirworthinessDirective
    checked_aircraft: int
    affected: list[AffectedAircraft]
    not_affected: list[NotAffected]
    open_questions: list[Question]
    citations: list[Citation]
    reasoning_path: list[ReasoningStep]


class FleetAircraft(Aircraft):
    """One row of the fleet board: identity + status + one-line reason."""
    status: AircraftStatus
    reason: str
    open_questions: int


class FleetResponse(BaseModel):
    """GET /fleet."""
    aircraft: list[FleetAircraft]
    computed_at: str


class QuestionsResponse(BaseModel):
    """Q5 — GET /questions, sorted by urgency, then days_left."""
    questions: list[Question]
    urgency_rule: str


class ValidatedField(BaseModel):
    """One extracted field and the check of its quote against the AD text."""
    field: str
    value: Any
    quote: str
    file: str
    occurrence: int
    check: Literal["quote found in text", "quote not found in text"]


class StatusChange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    aircraft_id: str
    from_: AircraftStatus = Field(alias="from")
    to: AircraftStatus


class IngestChanges(BaseModel):
    superseded: list[str]
    aircraft_status_changed: list[StatusChange]


class IngestResponse(BaseModel):
    """Q2 — POST /ads/{ad_id}/ingest. A pipeline run, not an action. Demo mode: source = golden, no LLM."""
    run_id: str
    ad_id: str
    source: Literal["golden", "cache", "llm"]
    validated_fields: list[ValidatedField]
    rejected_fields: list[ValidatedField]
    changes: IngestChanges
    citations: list[Citation]
    reasoning_path: list[ReasoningStep]


class ResetCounts(BaseModel):
    ads: int
    aircraft: int
    questions: int
    decisions: int
    proposals: int
    logbook_records: int


class DemoResetResponse(BaseModel):
    ok: bool
    state: str
    reset_at: str
    counts: ResetCounts
    not_loaded: list[str]
    aircraft_status: dict[str, AircraftStatus]


def shape_errors(expected: dict, actual: object) -> list[str]:
    """Contract check used by tests and scripts/smoke.py: same top-level keys as the example,
    and every citation / reasoning step / error validates against the shared shapes."""
    if not isinstance(actual, dict):
        return [f"body is {type(actual).__name__}, not an object"]
    errors = [f"missing key {k!r}" for k in expected if k not in actual]
    errors += [f"unexpected key {k!r}" for k in actual if k not in expected]
    if "error_code" in expected:
        errors += _validate(Error, actual, "body")

    def walk(node: object, where: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{where}.{key}"
                if key == "citations" and isinstance(value, list):
                    for i, c in enumerate(value):
                        errors.extend(_validate(Citation, c, f"{here}[{i}]"))
                elif key == "citation" and value is not None:
                    errors.extend(_validate(Citation, value, here))
                elif key == "reasoning_path" and isinstance(value, list):
                    for i, s in enumerate(value):
                        errors.extend(_validate(ReasoningStep, s, f"{here}[{i}]"))
                else:
                    walk(value, here)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{where}[{i}]")

    walk(actual, "body")
    return errors


def _validate(model: type[BaseModel], value: object, where: str) -> list[str]:
    try:
        model.model_validate(value)
        return []
    except ValueError as exc:  # pydantic.ValidationError is a ValueError
        return [f"{where}: {exc}"]
