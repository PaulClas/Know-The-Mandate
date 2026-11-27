"""Smoke test for a running `docker compose up` stack (API :8000, web :3000). Exits non-zero on any failure.

    docker compose up --build -d --wait && python3 scripts/docker_smoke.py

Standard library only. It runs the 13 scenarios and the red-team through the containerised API, verifies the evidence
ledger, and checks that the web container proxies the API.
"""
import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:3000"


def call(method: str, url: str, body: dict | None = None, token: str | None = None, timeout: int = 300):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def check(ok: bool, label: str) -> None:
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        sys.exit(1)


def main() -> None:
    for _ in range(60):
        try:
            if call("GET", f"{API}/health", timeout=5)[0] == 200:
                break
        except (urllib.error.URLError, OSError):
            time.sleep(2)
    else:
        check(False, "API became healthy")
    token = json.loads(call("POST", f"{API}/api/session", {"user_id": "admin_001"})[1])["token"]

    failed = []
    for sid in "ABCDEFGHIJKLM":
        res = json.loads(call("POST", f"{API}/api/scenarios/{sid}/run", token=token)[1])
        if not res["passed"]:
            failed.append(sid)
    check(not failed, f"scenarios A-M passed (failed: {failed})")

    rt = json.loads(call("POST", f"{API}/api/redteam/run", token=token)[1])["summary"]
    check(rt["errors"] == [], "red-team harness ran without errors")
    check(rt["kym"]["blocked"] == rt["kym"]["applicable"], f"KYM blocked {rt['kym']['blocked']}/{rt['kym']['applicable']} applicable attacks")
    check(rt["scope_only"]["blocked"] == 0, f"scope-only baseline blocked {rt['scope_only']['blocked']}/{rt['scope_only']['applicable']}")

    ledger = json.loads(call("POST", f"{API}/api/ledger/verify", token=token)[1])
    check(ledger["ok"] and not ledger["problems"], f"ledger verified ({ledger['events_checked']} events)")

    check(call("GET", f"{WEB}/")[0] == 200, "web serves /")
    check(call("GET", f"{WEB}/llms.txt")[0] == 200, "web serves /llms.txt")
    check(json.loads(call("GET", f"{WEB}/api/overview", token=token)[1]) is not None, "web proxies /api/overview to the API")
    print("docker smoke test passed")


if __name__ == "__main__":
    main()
