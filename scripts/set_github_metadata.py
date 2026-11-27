#!/usr/bin/env python3
"""Apply .github/repo-metadata.json to the GitHub repository (description, topics, private vulnerability reporting).

Needs a token with repository administration rights in GITHUB_TOKEN (fine-grained: "Administration: write").
  GITHUB_TOKEN=... python3 scripts/set_github_metadata.py            # apply
  python3 scripts/set_github_metadata.py --dry-run                   # show what would be sent
Idempotent: safe to run repeatedly. Topics are validated locally (GitHub: lowercase, <=50 chars, <=20 topics).
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

META = json.loads((Path(__file__).resolve().parents[1] / ".github" / "repo-metadata.json").read_text())
API = "https://api.github.com"


def validate(meta: dict) -> None:
    topics = meta["topics"]
    assert len(topics) <= 20, "GitHub allows at most 20 topics"
    assert len(set(topics)) == len(topics), "duplicate topics"
    for t in topics:
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", t), f"invalid topic {t!r}"
    assert len(meta["description"]) <= 350, "GitHub description limit is 350 characters"


def call(method: str, path: str, token: str, body: dict | None = None) -> int:
    req = urllib.request.Request(f"{API}{path}", method=method, data=json.dumps(body).encode() if body is not None else None, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        print(f"  {method} {path} -> HTTP {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        return e.code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    validate(META)
    repo = META["repository"]
    plan = [("PATCH", f"/repos/{repo}", {"description": META["description"], **({"homepage": META["homepage"]} if META["homepage"] else {})}),
            ("PUT", f"/repos/{repo}/topics", {"names": META["topics"]})]
    if META.get("private_vulnerability_reporting"):
        plan.append(("PUT", f"/repos/{repo}/private-vulnerability-reporting", None))
    if a.dry_run:
        for m, p, b in plan:
            print(m, p, json.dumps(b))
        print(f"OK: metadata valid ({len(META['topics'])} topics, description {len(META['description'])} chars)")
        return 0
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is not set.\n"
              "  1. Create a fine-grained token: https://github.com/settings/personal-access-tokens/new\n"
              "     (Repository access: only PaulClas/Know-Your-Mandate; Permissions > Repository > Administration: Read and write)\n"
              "  2. Run:  GITHUB_TOKEN=<token> python3 scripts/set_github_metadata.py\n"
              "  3. Delete the token afterwards.\n"
              "No token? Do it by hand: see docs/discoverability.md#applying-the-github-metadata. Use --dry-run to preview.", file=sys.stderr)
        return 2
    bad = 0
    for m, p, b in plan:
        s = call(m, p, token, b)
        print(f"{m} {p} -> {s}")
        bad += 0 if 200 <= s < 300 else 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
