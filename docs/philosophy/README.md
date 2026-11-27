# The philosophy of KYM, and why it stands against its critics

> **The agent proposes. The mandate authorizes. The bank enforces. The ledger remembers.**

## The problem in one paragraph

Software that can act is not new. What is new is *software with open-ended intent*: an AI agent can decide what to do next. Existing financial controls answer who the customer is (KYC), whether the caller is who it claims to be (authentication), what API a client may call (OAuth), and whether a transaction looks risky (KYT). **None of them records, as a checkable object, what authority a human actually handed to this software.** When something goes wrong, nobody can reconstruct who granted what, under which limits, and whether the bank respected it. KYM's thesis: *delegated financial authority deserves to be a first-class, governed object with a lifecycle.*

## Principles

1. **Authority is not identity, and not permission.** Four things are kept apart: identity, technical permission (a token), delegated authority (a mandate), execution (money moved). A valid token never implies an authorized operation.
2. **Separation of powers.** The agent *proposes* and cannot decide. The mandate *authorizes* and cannot execute. The bank *enforces* and cannot invent authority. The ledger *remembers* and cannot be edited silently. No component can authorize its own action.
3. **Enforce the observable, not the intention.** The bank cannot know whether an agent hallucinated, was injected or was compromised, and does not need to. It checks amounts, beneficiaries, budgets, time, state. This makes enforcement independent of the model.
4. **Deny by default; closed world at runtime.** Ontologies reason under an open world (absence ≠ falsity). Money cannot. Missing authority means denial; semantic technology is used for meaning and validation, never for the decision.
5. **Authority only attenuates.** Delegation can narrow, never widen (capability-security lineage: least privilege, attenuation). A child can never exceed its parent, and revoking a parent disables the children.
6. **Evidence over trust.** Claims should be checkable by someone who does not trust the bank: signed, hash-chained, replayable against the current engine, offline-verifiable (with keys pinned out of band; the verifier also binds the displayed transaction to the signed events). Evidence shows *who did what and under which version*; **it does not decide liability.**
7. **Humans decide exceptions, about exact things.** Approval is bound to the exact operation, single use, expiring, by distinct people where required. One-time approval never expands the mandate.
8. **Extend standards; do not replace them.** OAuth, DPoP, RAR, JSON-LD, SHACL, PROV-O, ODRL are reused. KYM-specific parts are labelled *proposed*.
9. **Honesty is a feature.** Simulated things say so in the UI and docs. Gaps are published (see the [risk register](../risk/risk-register.md)), including attacks KYM does **not** stop.
10. **Narrow claim, falsifiable proof.** KYM does not claim to make AI safe. It claims one thing (below), and ships code that tries to break it.

## The claim, stated narrowly

> A bank can hold an **independent, stateful, revocable representation of delegated authority**, evaluated deterministically on **every** request, that bounds what an agent can do with the bank's money **regardless of how the agent behaves or what credentials it holds**, and can later **prove** what happened.

Everything else (ontology, CNL, delegation graphs, dashboards) serves or illustrates that claim.

## Claims and how to falsify them

| Claim | How to falsify it | Proof in repo |
|---|---|---|
| A valid token cannot move money outside the mandate | Make a payment to a non-permitted beneficiary with a valid token succeed | Scenario C; `redteam: beneficiary_swap`; `tests/integration/test_enforcement.py` |
| Cumulative limits hold under concurrency | Exceed the monthly budget with parallel requests | Scenario H; `redteam: budget_race`; 8-thread test and a 4-process race (`make concurrency`) on SQLite and PostgreSQL. Serialization-based, so throughput-limited; multi-node is untested (O-03) |
| Revocation is immediate and cascades | Execute after revocation with an unexpired token, or via a child | Scenario F, G; `redteam: revoked_mandate` |
| A stolen token is useless to another party | Replay a token or DPoP proof from another key | `redteam: stolen_token`, `dpop_replay` |
| Approvals can't be substituted or replayed | Execute a changed payload, or reuse an approval | Scenario J; `redteam: approval_*` |
| A child can't exceed its parent | Create a wider child by any dimension | `tests/unit/test_properties.py` (Hypothesis); Scenario G |
| Evidence tampering is detectable | Alter, delete or re-hash an event without detection | Scenario L; `redteam: ledger_tamper` |
| Decisions can be reconstructed | Fail to reproduce a decision from stored inputs | Scenario M; `tests/integration` replay tests |
| KYM is more than OAuth + static RAR | Show a static design stopping the stateful attacks | `redteam` comparison (stateless static RAR 3/10 vs KYM 10/10 on the same attacks, 22/22 overall; the baseline is deliberately stateless) |
| **KYM cannot stop in-mandate misuse** (negative claim) | Show a mandate-level control that does | `redteam: in_mandate_malicious` (honest gap) |

Run `make redteam`. Results are written to [docs/redteam/latest.md](../redteam/latest.md).

## The critics, steelmanned

Each objection is stated at its strongest, answered, and then we say **where the critic is right**.

### 1. "OAuth with Rich Authorization Requests already does this."
*Strongest form:* RFC 9396 lets a token carry exactly which account, beneficiary and maximum amount; FAPI and DPoP exist; this is reinvention.
*Answer:* We agree and use them as the carrier. But RAR is a **grant format**: it is static, evaluated against the token, and has no notion of cumulative budgets, mandate revocation independent of the token, approval binding or delegation lineage. In the proof, a design with scopes + static RAR stops swaps and per-payment limits (3 of 10 applicable attacks) and fails budget drain, races, revocation, stolen tokens and approvals. KYM adds the **state** (budgets, lifecycle, approvals) and the **per-request decision**.
*Critic is right that:* if all you need is a per-payment cap, RAR is enough and KYM is overkill.

### 2. "Banks already have limits, SCA and fraud engines."
*Answer:* Those control instruments and transactions; they do not know that a **delegated software actor** is exercising authority for a **named purpose**, nor can they reconstruct delegation. KYM's risk engine is deliberately separate: authorization and risk are different questions.
*Critic is right that:* KYM must integrate with, not replace, existing controls; its risk engine here is synthetic.

### 3. "Mandates and approvals are consent theatre; people click through."
*Answer:* Approvals are bound to the **exact operation**, single use, and rare by design (budgets and thresholds mean most payments need none). That addresses substitution and replay, not fatigue.
*Critic is right that:* approval fatigue is real and unmeasured here. This is the weakest part of the human-in-the-loop story (risk C-1).

### 4. "The real problem is agents being wrong *inside* their permissions."
*Answer:* Correct, and we ship the attack that shows it (`in_mandate_malicious`). Mandates **bound the blast radius**; they do not verify correctness. Defence layers: tight limits, thresholds, notifications, risk models.
*Critic is right.* KYM must never be sold as preventing in-mandate harm.

### 5. "Ontologies, OWL and SHACL are over-engineering. JSON Schema plus code is enough."
*Answer:* The runtime decision does **not** use the ontology (ADR-0003). It earns its place only for interoperable meaning, validation of mandate graphs, explanation and SPARQL queries across mandates, delegation and evidence (e.g. "which mandates depend on a revoked parent?").
*Critic is right that:* a deployment with no need for shared semantics can drop it and keep everything else.

### 6. "A hash chain is blockchain theatre; logs are fine."
*Answer:* No blockchain is used. Signed hash chains make *silent* edits detectable, and the proof tampers four ways and fails to evade detection. Evidence packages verify offline.
*Critic is right that:* an operator who controls the database, keys and exported checkpoints can rewrite history; real assurance needs WORM storage, timestamping and external witnesses. Also right that an unpinned verifier is fooled (we found and fixed that, F-01).

### 7. "Networks and wallets (AP2, Visa, Mastercard) will own agentic commerce; banks will be bypassed."
*Answer:* The account-holding bank remains the final authority over its own accounts, and AP2-style artifacts map onto KYM concepts (see [AP2 mapping](../research/ap2-mapping.md)). Layers are complementary: merchant-side intent proofs vs. bank-side authority enforcement.
*Critic is right that:* if payments route around the bank's decision, KYM is irrelevant there (risk D-2).

### 8. "LLM guardrails and alignment are the answer."
*Answer:* Guardrails are probabilistic and bypassable; KYM is deterministic and model-independent. They are complementary: guardrails reduce harmful attempts, mandates cap consequences when guardrails fail.
*Critic is right that:* guardrails also address harms KYM does not (misinformation, privacy, in-mandate misuse).

### 9. "Centralized enforcement is a single point of failure and a gatekeeping tool."
*Answer:* Fail-closed is intentional for money. High availability and fair-access policy are engineering and regulatory matters.
*Critic is right.* No HA design exists here, and gatekeeping risk is real (C-5, C-11).

### 10. "'Mandate' has legal meaning; an AI can't be a mandatary."
*Answer:* Agreed, and KYM says so: the AI is not a legal person; the responsible operator is modelled separately; evidence is not a liability finding; nothing claims legal effect.
*Critic is right that:* terminology invites misreading; legal review is required (D-4).

### 11. "This is a self-graded demo."
*Answer:* Yes. The response is to make claims **falsifiable and reproducible** (`make redteam`, public tests, published gaps) and to invite external attack.
*Critic is right.* Until independently tested, KYM is a hypothesis with working code.

### 12. "Too complex for the benefit."
*Answer:* It need not be adopted whole.

## Adoption ladder

| Level | What | Gain | Cost |
|---|---|---|---|
| 0 | Scopes + consent management | Data access control | Low |
| 1 | + RAR (static account/beneficiary/amount) + DPoP | Stops swaps, over-limit, token theft | Low–Med |
| 2 | + Mandate registry, PDP, budgets, revocation | Stateful limits, instant revocation, approvals | Med |
| 3 | + Evidence ledger, replay, dispute packages | Provable reconstruction | Med–High |
| 4 | + Delegation, ontology/SPARQL, CNL studio | Multi-agent governance, shared semantics | High |

## What would change our mind

* A realistic attack in the red-team harness that a *simpler* design stops and KYM does not.
* Evidence that approvals degrade to rubber-stamping at scale, with no UX fix.
* A standard (RAR + Grant Management + a budget extension) that supplies state, revocation and evidence with less machinery.
* A legal conclusion that such evidence has no value.

If any of these occurs, the right response is to simplify or stop, not to rebrand.
