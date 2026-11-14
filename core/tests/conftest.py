"""Tests never write to the real evaluation log in data/runtime/: each test gets an in-memory log."""
import pytest

from app import api, evaluations


@pytest.fixture(autouse=True)
def memory_evaluation_log(monkeypatch):
    log = evaluations.EvaluationLog(None)
    monkeypatch.setattr(api, "EVAL_LOG", log)
    return log
