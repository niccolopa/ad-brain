"""End-to-end smoke test against a RUNNING core server.

Usage: python scripts/smoke.py [base_url]   (default http://127.0.0.1:8000)
Calls /health and every request in contract/examples/, checks status + contract shape.
POST /demo/reset runs first and last, so the server is left in the demo state.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "core"))
from app.ontology import shape_errors  # noqa: E402

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
TIMEOUT_S = 10
EXAMPLES_DIR = REPO / "contract" / "examples"
SKIP = {"error-not-found"}  # v0 fakes have no 404 yet; removed in v1


def call(base: str, method: str, path: str, body: object = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL).rstrip("/")
    try:
        status, body = call(base, "GET", "/health")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        print(f"FAIL server not reachable at {base}: {e}")
        return 1
    failures = 0 if (status, body) == (200, {"ok": True, "demo_mode": True}) else 1
    print(("ok  " if not failures else "FAIL") + " GET /health")

    examples = sorted((p for p in EXAMPLES_DIR.glob("*.json") if p.stem not in SKIP),
                      key=lambda p: p.stem != "demo-reset")
    for path in [*examples, EXAMPLES_DIR / "demo-reset.json"]:
        ex = json.loads(path.read_text(encoding="utf-8"))
        req, resp = ex["request"], ex["response"]
        status, body = call(base, req["method"], req["path"], req.get("body"))
        errors = [] if status == resp["http_status"] else [f"status {status} != {resp['http_status']}"]
        errors += shape_errors(resp["body"], body)
        failures += bool(errors)
        print(f"{'FAIL' if errors else 'ok  '} {req['method']} {req['path']}  ({path.name})")
        for e in errors:
            print(f"       {e}")
    print(f"\n{'PASS' if not failures else 'FAIL'}: {failures} failing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
