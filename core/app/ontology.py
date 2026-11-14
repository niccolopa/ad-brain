"""Shared shapes from contract/README.md ("Shared shapes"). The UI generates its types from these."""
from typing import Literal

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
