# External review: what exists, what does not, and how to commission one

**Status: no external audit, penetration test or independent code review has been performed.** Every result in this repository (the red-team table, the findings register, the test counts) was produced by the author, with the help of AI coding assistants, and checked by the author's own tooling and one AI-assisted "hostile" review whose findings are recorded as F-16 to F-24. That review found real defects the author had missed, which is the best argument that more eyes would find more.

## What would count as independent

| Kind | Independent of the author? | Status |
|---|---|---|
| Author's tests and red-team harness | No | Done (`make test`, `make redteam`) |
| AI-assisted hostile review | Partly (different prompt, no shared context) | Done once; findings F-16 to F-24 |
| Human code review by a security engineer | Yes | **Not done** |
| Penetration test or threat-model workshop | Yes | **Not done** |
| Cryptographic review (ledger, certificates, DPoP use) | Yes | **Not done** |
| Standards-body or regulator interoperability testing | Yes | **Not done** (no claim of conformance anywhere) |

## Scope an external reviewer should start with

1. **The enforcement path.** `apps/api/kym/gateway.py` (PEP), `policy.py` (PDP, pure function), `bank.py` (certificate-gated payment engine), `oauth.py` (sandbox OAuth/DPoP). Question: can any request reach money movement without a valid, single-use, transaction-bound decision?
2. **State and budgets.** Cumulative limits, approval consumption, idempotency, revocation, the global write lock (`db.py`). Question: can concurrent or replayed requests exceed a limit?
3. **The evidence ledger.** `ledger.py`, `disputes.py`: canonicalization (RFC 8785), signatures, hash chain, checkpoints, package verification. Question: can history be rewritten or forged without detection, given pinned keys?
4. **Delegation.** Attenuation rules and cascading revocation (`policy.py`, `mandates.py`).
5. **The claims.** [docs/philosophy/README.md](../philosophy/README.md) lists falsifiable claims, each with the test that would break it.

Out of scope by design: the UI's demo sessions (no passwords), key storage on disk, and anything listed as open in the [security review](security-review.md).

## Reproduce everything in five minutes

```bash
make install && make test && make scenarios && make redteam && make concurrency
```

A reviewer who can run these has the same evidence the author has. Then try to break it: new attack ideas belong in [`redteam.py`](../../apps/api/kym/redteam.py) (see [CONTRIBUTING](../../CONTRIBUTING.md)); an attack KYM fails is a contribution, not an embarrassment.

## Ways to help

* **Report a vulnerability privately:** see [SECURITY.md](../../SECURITY.md).
* **Propose an attack:** use the "Attack idea" issue template.
* **Commission or volunteer a review:** email the maintainer (address in the [README](../../README.md#contact)). A written report, even a short one, can be linked from this file with the reviewer's name, date and scope, and will be published unedited alongside any fixes.

## What this file will say when a review exists

It will list the reviewer, the date, the commit reviewed, the scope, the report link and the disposition of every finding. Until then, any statement that KYM is "audited", "verified", "certified" or "secure" is false. See the [media guide](../media-guide.md).
