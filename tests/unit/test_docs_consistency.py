"""Docs are claims. This keeps the numbers, links and generated artifacts honest."""
import json
import re
from pathlib import Path

from kym import redteam

ROOT = Path(__file__).resolve().parents[2]


def read(p):
    return (ROOT / p).read_text()


def test_attack_count_is_consistent_across_docs():
    n = len(redteam.ATTACKS)
    for p in ("README.md", "docs/faq.md", "llms.txt", "docs/security/security-review.md"):
        assert f"{n} attacks" in read(p) or f"{n} executable attacks" in read(p), p


def test_findings_counts_match_the_register():
    sec = read("docs/security/security-review.md")
    fixed = len(re.findall(r"^\| F-\d+ ", sec, re.M))
    openi = len(re.findall(r"^\| O-\d+ ", sec, re.M))
    for p in ("README.md", "docs/faq.md", "llms.txt"):
        t = read(p)
        assert f"{fixed} " in t and f"{openi} " in t, p


def test_llms_txt_links_resolve_to_files():
    for path in re.findall(r"github\.com/PaulClas/Know-The-Mandate/(?:blob|tree)/main/([^)\s]+)", read("llms.txt")):
        assert (ROOT / path).exists(), path


def test_llms_full_is_current():
    import importlib.util

    spec = importlib.util.spec_from_file_location("b", ROOT / "scripts" / "build_llms_full.py")
    before = read("llms-full.txt")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert read("llms-full.txt") == before, "llms-full.txt was stale: run `make llms-full` and commit"


def test_committed_redteam_results_match_the_harness_and_claims():
    rep = json.loads(read("docs/redteam/latest.json"))
    assert {a["id"] for a in rep["attacks"]} == {a[0] for a in redteam.ATTACKS}
    assert rep["summary"]["kym_not_blocked"] == ["in_mandate_malicious"] and rep["summary"]["errors"] == []
    s = rep["summary"]
    assert f"{s['kym']['blocked']}/{s['kym']['applicable']}" == "22/22"
    assert f"{s['rar_static']['blocked']}/{s['rar_static']['applicable']}" == "3/10" and f"{s['scope_only']['blocked']}/{s['scope_only']['applicable']}" == "0/10"


def test_every_doc_states_the_experimental_status():
    for p in ("README.md", "docs/faq.md", "llms.txt", "docs/risk/risk-register.md", "docs/philosophy/README.md"):
        assert re.search(r"experimental|synthetic", read(p), re.I), p


def test_generated_reference_docs_are_current():
    import runpy

    paths = ("docs/reference/api.md", "docs/reference/reason-codes.md")
    before = [read(p) for p in paths]
    runpy.run_path(str(ROOT / "scripts" / "build_reference.py"))
    assert [read(p) for p in paths] == before, "docs/reference was stale: run `make reference` and commit"


def test_license_is_apache_2_and_declared_consistently():
    assert "Apache License" in read("LICENSE") and "Version 2.0" in read("LICENSE")
    assert 'license = "Apache-2.0"' in read("pyproject.toml")
    assert json.loads(read("apps/web/package.json"))["license"] == "Apache-2.0"
    assert "license: Apache-2.0" in read("CITATION.cff")
    assert json.loads(read("codemeta.json"))["license"].endswith("Apache-2.0")
    assert "Apache-2.0" in read("README.md")


def test_community_health_files_exist():
    for p in ("LICENSE", "NOTICE", "README.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md", "SUPPORT.md", "CHANGELOG.md", "GOVERNANCE.md", "MAINTAINERS.md",
              ".github/pull_request_template.md", ".github/CODEOWNERS", ".github/dependabot.yml", ".github/workflows/ci.yml", ".github/workflows/security.yml"):
        assert (ROOT / p).exists(), p


def test_dockerfile_pins_match_pyproject():
    """The image pins its own dependencies; they must not drift from pyproject.toml."""
    import tomllib

    proj = tomllib.loads(read("pyproject.toml"))["project"]
    declared = set(proj["dependencies"]) | set(proj["optional-dependencies"]["postgres"])
    pinned = set(re.findall(r'"([^"\s]+==[^"\s]+)"', read("docker/Dockerfile.api")))
    assert declared == pinned, f"only in pyproject: {declared - pinned}; only in Dockerfile: {pinned - declared}"
