"""The README diagrams cannot drift from the code: every repo path they name exists, and every API route they
name is a real route."""
import re

from app import store
from app.api import app

README = store.REPO / "README.md"
MERMAID_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
PATH_RE = re.compile(r"(?<![\w/.])((?:core|data|docs|ui|scripts|contract)/[\w./-]*)")
ROUTE_RE = re.compile(r"(?:(?<=\s)|(?<=·)|(?<=\")|(?<=>))(/[a-z][\w\-/{}]*)")  # after space, ·, quote or <br/>
PARAM_RE = re.compile(r"\{[^}]*\}")


def diagrams() -> list[str]:
    blocks = MERMAID_RE.findall(README.read_text(encoding="utf-8"))
    assert len(blocks) >= 2, "expected the architecture and the decision-flow diagrams"
    return blocks


def test_every_path_in_the_diagrams_exists():
    paths = {p.rstrip(".,)") for block in diagrams() for p in PATH_RE.findall(block)}
    assert len(paths) >= 10
    missing = sorted(p for p in paths if not (store.REPO / p).exists())
    assert missing == []


def test_every_route_in_the_diagrams_exists():
    routes = {PARAM_RE.sub("{}", r.path) for r in app.routes if hasattr(r, "methods")}
    named = {PARAM_RE.sub("{}", r) for block in diagrams() for r in ROUTE_RE.findall(block)}
    assert len(named) >= 8
    unknown = sorted(n for n in named if not any(route == n or route.startswith(n + "/") for route in routes))
    assert unknown == []


def test_regexes_catch_a_wrong_path_and_route():
    block = 'X["core/app/nope.py · /nowhere/{id}"]'
    assert PATH_RE.findall(block) == ["core/app/nope.py"] and not (store.REPO / "core/app/nope.py").exists()
    assert ROUTE_RE.findall(block) == ["/nowhere/{id}"]
