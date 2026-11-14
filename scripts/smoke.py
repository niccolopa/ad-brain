"""End-to-end smoke test: starts the core server in-process on 127.0.0.1:8000, calls /health and every request
in contract/examples/, checks status + contract shape, then stops the server.

    python scripts/smoke.py              # start a fresh server (fails loudly if port 8000 is already in use)
    python scripts/smoke.py --url URL    # test a server you started yourself (no port check)

The port check exists because a leftover server would answer instead of the code under test.
POST /demo/reset runs first and last, so the server is left in the demo state.
"""
import argparse
import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "core"))
from app.ontology import shape_errors

HOST, PORT = "127.0.0.1", 8000
TIMEOUT_S = 10
STARTUP_TIMEOUT_S = 20
EXAMPLES_DIR = REPO / "contract" / "examples"
SKIP: set[str] = set()  # example files not to call


def call(base: str, method: str, path: str, body: object = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return True
    return False


def start_server():
    import uvicorn
    from app.api import app
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.1)
    return server, thread


def run_checks(base: str) -> int:
    try:
        status, body = call(base, "GET", "/health")
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        print(f"FAIL server not reachable at {base}: {e}")
        return 1
    failures = 0 if (status, body) == (200, {"ok": True, "demo_mode": True}) else 1
    print(("ok  " if not failures else "FAIL") + f" GET /health  ({body})")

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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", help="test an already running server instead of starting one")
    args = p.parse_args()
    if args.url:
        return run_checks(args.url.rstrip("/"))
    if port_in_use(HOST, PORT):
        print(f"FAIL port {PORT} is already in use: a leftover server would answer instead of the code under test.\n"
              f"     Stop it first (Windows: Get-NetTCPConnection -LocalPort {PORT} -State Listen | "
              f"% {{ taskkill /PID $_.OwningProcess /T /F }} ; macOS/Linux: kill $(lsof -t -i :{PORT})),\n"
              f"     or test it on purpose with: python scripts/smoke.py --url http://{HOST}:{PORT}")
        return 2
    server, thread = start_server()
    try:
        return run_checks(f"http://{HOST}:{PORT}")
    finally:
        server.should_exit = True
        thread.join(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
