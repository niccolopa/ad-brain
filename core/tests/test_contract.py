"""Every endpoint answers its contract example's request with the example's status and shape."""
import json

import pytest
from fastapi.testclient import TestClient

from app.api import EXAMPLES_DIR, app
from app.ontology import shape_errors

client = TestClient(app)
# error-not-found.json is covered by the 404 tests in test_api.py.
EXAMPLES = sorted(p for p in EXAMPLES_DIR.glob("*.json") if p.stem != "error-not-found")


@pytest.mark.parametrize("path", EXAMPLES, ids=[p.stem for p in EXAMPLES])
def test_endpoint_matches_example(path):
    ex = json.loads(path.read_text(encoding="utf-8"))
    req, resp = ex["request"], ex["response"]
    r = client.request(req["method"], req["path"], json=req.get("body"))
    assert r.status_code == resp["http_status"], r.text
    assert shape_errors(resp["body"], r.json()) == []


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "demo_mode": True}


@pytest.mark.parametrize("path", ["/proposals?status=PENDING", "/proposals/PR-0004/reject"])
def test_endpoints_without_example(path):
    method = "POST" if path.endswith("reject") else "GET"
    assert client.request(method, path, json={}).status_code == 200


def test_shape_errors_rejects_bad_bodies():
    good = {"citations": [], "reasoning_path": []}
    assert shape_errors(good, good) == []
    assert shape_errors(good, None) != []
    assert shape_errors(good, []) != []
    assert shape_errors(good, {"citations": []}) != []  # missing key
    assert shape_errors(good, {**good, "extra": 1}) != []  # unexpected key
    bad_cit = {"citations": [{"ad_id": "FAA:1", "quote": "", "file": "f", "occurrence": 0, "source_url": "u"}],
               "reasoning_path": []}
    assert shape_errors(good, bad_cit) != []
    bad_step = {"citations": [], "reasoning_path": [{"from": "a", "link": "owns", "to": "b",
                                                      "derived": False, "note": ""}]}
    assert shape_errors(good, bad_step) != []
    assert shape_errors({"error_code": "X", "message": "m", "details": {}},
                        {"error_code": "X", "message": "m", "details": {}, "trace": "..."}) != []
