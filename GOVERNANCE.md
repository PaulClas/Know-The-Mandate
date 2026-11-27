# Governance

KYM is a **single-maintainer** experimental project. This document states how decisions are made so contributors know what to expect.

* **Decisions:** the maintainer decides; significant design changes are recorded as ADRs in [docs/adr](docs/adr/) with context, decision and consequences. Reversals are recorded as new ADRs.
* **Invariants:** the rules in [AGENTS.md](AGENTS.md) (deny by default, PDP purity, atomicity, honest labelling, etc.) change only via an ADR.
* **Claims discipline:** any claim in docs (counts, standards status, "blocked X of Y") must be backed by a command or test; `tests/unit/test_docs_consistency.py` enforces some of this.
* **Vocabulary stewardship:** the `https://example.org/kym/v1#` namespace is a **placeholder**, not a governed standard. Moving to a real namespace and a multi-party steward is a prerequisite for any standardization effort (see risk D-6 in the [risk register](docs/risk/risk-register.md)).
* **Disagreement:** open an issue or discussion with a reproducing test. Evidence beats opinion.
* **Code of conduct:** [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
