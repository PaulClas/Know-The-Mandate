# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/) (0.x = experimental, anything may change).

## [Unreleased]

### Added
- Apache-2.0 `LICENSE` and `NOTICE`; community files (`CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `SUPPORT`, `GOVERNANCE`, `MAINTAINERS`, `ROADMAP`); issue/PR templates, CODEOWNERS, Dependabot, security workflow.
- `examples/` (runnable quickstart, CNL mandate library, curl walkthrough), `docs/getting-started.md`, `docs/testing.md`, generated API and reason-code references, configuration and deployment guides.
- Coverage measurement (`make coverage`; 82% line+branch measured), pre-commit, `.editorconfig`, `pip-audit` target.
- CI: coverage artifact, red-team run, lint, and a Docker Compose job running `scripts/docker_smoke.py`. Security workflow: pip-audit, npm audit, gitleaks, CodeQL. Workflows have not yet run on GitHub.
- `scripts/set_github_metadata.py` and `.github/repo-metadata.json` to apply the repository description, topics and private vulnerability reporting.
- Tests for examples, generated references, license consistency and community-health files.

- `docs/security/external-review.md` (honest status of independent review and how to commission one), `docs/media-guide.md` (what may and may not be claimed), author/contact details (a machine learning developer; email for questions).
- `scripts/concurrency_check.py` / `make concurrency`: four OS processes race one budget; run on SQLite and PostgreSQL 16 and in the Docker smoke test.
- Token exchange now requires the parent's co-signed proof of possession; decision certificates carry `tx_id`; signed decisions record an engine fingerprint so replay can report `engine_changed`.
- `transactions.executed_at` (migration `0002`); budgets are counted by execution time. Property tests for day/month windows across DST.

- **Agent transparency** (`transparency.py`, [spec](docs/specifications/agent-transparency.md)): signed, hash-chained activity reports reconciled against the bank's own transactions; commit-reveal for reasoning logs; dead-man's switch; violations restrict the agent. Migration `0003`. Five red-team attacks (`hidden_action`, `phantom_action`, `log_swap`, `silent_agent`, and the honest gap `out_of_band_action`), 13 tests, an example, open findings O-23 to O-26. Existing demo databases need `make reset-demo`.

### Changed
- README: badges, contents, quickstart, documentation map, contributing, security, citation and license sections.
- Docker Compose verified end to end (PostgreSQL 16 + API + web); `.dockerignore` files added.
- `pyproject.toml`: license, URLs, classifiers, coverage configuration.

## [0.1.0] - 2026-11-26

### Added
- Mandate ontology (OWL/Turtle), SHACL shapes, JSON-LD context; KYM-CNL controlled language and deterministic compiler; canonical mandate model and JSON Schema.
- Deterministic policy decision point, mandate lifecycle with cascading revocation, delegation with strict attenuation.
- Sandbox OAuth server (PAR, PKCE, RFC 9396 RAR, DPoP, introspection, revocation, token exchange); policy enforcement point and simulated open-banking gateway; double-entry payment engine requiring signed single-use decision certificates.
- Signed hash-chained evidence ledger with checkpoints; dispute reconstruction and offline-verifiable evidence packages; responsibility mapping.
- Web UI (13+ pages), scenarios A-M, agent sandbox, red-team harness comparing scope-only, OAuth+static-RAR and KYM (23 attacks at 0.1.0; 28 after transparency).
- Regulatory control mappings (CA, CA-QC, US), standards matrix, AP2 conceptual mapping, threat model, security review, risk register, philosophy, FAQ, glossary, `llms.txt`.

### Security
- Self-review fixed 15 findings, and an independent pre-publication review a further 6 (F-16 to F-24: empty-ledger truncation, payee-kind confusion, execution-time budget windows with a migration, narrower token grants, token-exchange key pinning and parent co-signature, evidence-package binding, cross-process write serialization, transaction-bound certificates), with regression tests; the red-team verdicts now require an explicit denial with the expected reason code (evidence verifier key pinning, ledger-flood cap, auth outside write lock, killable SPARQL, path traversal, per-install session secret, fail-closed `KYM_ENV`, and others). See [docs/security/security-review.md](docs/security/security-review.md).
