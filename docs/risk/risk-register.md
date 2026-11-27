# KYM risk register and disclosures

This register covers **everything the authors believe could go wrong with KYM**: attacks, insider abuse, design flaws, legal exposure, adoption failure and ways the idea itself could be wrong or misused. It is written to be read by critics. Technical findings with proofs are in [../security/security-review.md](../security/security-review.md).

Scoring is qualitative (L = low, M = medium, H = high), by the authors, **before external review**. "Residual" is the risk left after the described mitigation *as implemented in this repository*.

## A. Disclosures up front

1. **Experimental, synthetic, self-assessed.** No real money, customers or regulators were involved. No external security audit, penetration test, formal verification or production pilot has occurred.
2. **Not compliant, certified or legal advice.** Regulatory mappings are research aids; several items are marked unverified.
3. **Sandbox security mechanisms.** The OAuth server is a sandbox adapter; customer authentication and consent are simulated; keys are files.
4. **KYM does not make agents safe.** It limits what an agent can *do with the bank's money*. It does not make the agent correct, honest or aligned.
5. **KYM can be misused.** A bank could use broad "consent receipts" to shift blame to customers (see C-9).
6. **The namespace is a placeholder** (`https://example.org/kym/v1#`), not a governed vocabulary.
7. **The red-team baselines are simple models** of common designs. They demonstrate specific gaps; they are not a market comparison.

## B. Security and hacking risks

| ID | Risk | L | I | Mitigation in repo | Residual |
|---|---|---|---|---|---|
| S-1 | Stolen or shared access token | M | H | DPoP sender-constraint, short TTL, per-request mandate checks | **L–M**: key theft from the agent host still works within the mandate |
| S-2 | Compromised agent runtime or key | M | H | Blast radius bounded by amounts, beneficiaries, budget, expiry, approvals | **M**: attacker can spend the whole budget at allowed beneficiaries |
| S-3 | Prompt injection / hallucination | H | M | Deterministic enforcement; injected content cannot widen authority | **M**: in-mandate harm is undetectable by design (proof `in_mandate_malicious`) |
| S-4 | Operator/insider abuse (reverse payments, clear reviews, suspend agents, read evidence) | M | H | Role checks, evidence events for actions | **H**: no maker–checker, no admin-read logging (O-04, O-19) |
| S-5 | Host or database compromise | M | H | Signed decisions, hash chain, checkpoints | **H**: plaintext keys, single trust domain (O-02, O-16) |
| S-6 | Ledger rewriting by an attacker who owns DB and keys | L | H | Signed checkpoints with witness key, exported checkpoint files | **M–H**: needs WORM/external witness (O-07) |
| S-7 | Forged or misleading evidence package | M | H | Pinned-key verification (fixed F-01) | **L** if verifiers pin keys; **H** if they trust embedded keys |
| S-8 | Denial of service (write lock, ledger flood, SPARQL, auth CPU) | M | M | Rate limits, caps, subprocess sandbox, auth outside lock | **M**: single-process design (O-03, O-10) |
| S-9 | Reconnaissance via denial reasons | H | L–M | None (disclosed) | **M** (O-15) |
| S-10 | Replay of approvals/proofs | L | M | Operation-hash binding, single use, jti cache | **L**; DPoP nonce absent (O-06) |
| S-11 | Supply-chain compromise | M | H | Few well-known libraries, pinned | **M** (O-13) |
| S-12 | Web-UI token theft (XSS) | L | H | React escaping, no HTML injection paths | **M**: `localStorage` + no CSP (O-14) |
| S-13 | Time-boundary budget errors | L | M | Calendar windows in IANA zones | **M**: limited DST tests (O-20) |
| S-14 | Decision-snapshot manipulation by a compromised gateway | L | H | Replay detects non-determinism | **M**: garbage-in not detectable (O-17) |
| S-15 | Deceptive or erroneous consent rendering | M | H | Digest-bound receipt, EN/FR summaries, tests on content | **M–H** (O-18) |

## C. Design flaws and "ways KYM could fail as an idea"

| ID | Risk | L | I | Assessment |
|---|---|---|---|---|
| C-1 | **Approval fatigue / consent theatre.** Frequent prompts train humans to click Approve. | H | H | Mitigated only partially by thresholds, exact-operation binding and limits that keep approvals rare. Approval rate is measured (`human_approval_rate` metric) but **no user study exists**. This is probably the biggest practical threat to the human-in-the-loop claim. |
| C-2 | **Customers misunderstand mandates.** The summary says X, the customer thinks Y; CNL and ontologies are not consumer language. | H | H | EN/FR plain summaries and ambiguity detection help; unvalidated with real users. |
| C-3 | **Mandate over-breadth.** Customers/agents/banks default to broad mandates; the control degrades to "yes". | M | H | Bank policy caps (per-payment cap, validity, forbidden actions) and mandatory aggregate limits exist; policy tuning is unproven. |
| C-4 | **False sense of security.** Teams relax other controls because "there is a mandate". | M | M | Documentation stresses defence in depth; cannot be enforced technically. |
| C-5 | **Fail-closed availability.** If the PDP, ledger or registry is down, agent payments stop. | M | M | Deliberate trade-off; no HA design exists. |
| C-6 | **Operational complexity and cost.** Ontology + SHACL + CNL + OAuth + ledger + registry is a lot to operate. | H | M | Mitigated by the adoption ladder in [philosophy](../philosophy/README.md#adoption-ladder): the ontology is optional (ADR-0003). |
| C-7 | **Performance and hot-row contention** (per-request budget aggregation across delegation chains). | M | M | Measured in-process (PDP 0.08 ms; gateway payment p50 19 ms single-process); not load-tested at scale. |
| C-8 | **Policy errors.** A wrong bank policy or wrong CNL compile silently authorizes the wrong thing. | M | H | Deterministic compile, SHACL + bank checks, replay; correctness of the *policy* is human. |
| C-9 | **Blame shifting / dark patterns.** Consent receipts could be used to claim the customer "authorized" harm. | M | H | Receipts carry assurance level and a legal note; bank caps limit exposure; but incentives are outside software. Regulators and law, not code, must allocate liability. |
| C-10 | **Privacy tension.** Immutable logs vs. erasure rights; hashes of low-entropy fields are guessable. | M | M | Payload store is erasable; chain commits to digests. Snapshots are not minimised (O-08). |
| C-11 | **Concentrated power.** KYM strengthens the bank's role as gatekeeper for agent access and could be used anti-competitively against third-party agents. | M | M | Not addressable in code; relevant to open-banking policy. |

## D. Strategic and "downfall" risks

| ID | Risk | L | I | Assessment |
|---|---|---|---|---|
| D-1 | **Standards absorb or bypass it.** OAuth RAR/Grant Management, AP2, networks' agent-payment schemes could cover the same ground, leaving KYM as an orphan vocabulary. | M | H | KYM is designed as a layer *on* RAR/DPoP and maps AP2; its own namespace is the least durable part. If the standards win, the architecture lessons survive, the vocabulary may not. |
| D-2 | **Coverage gap.** Agentic commerce may route authority through merchants, wallets or networks that never ask the account-holding bank. KYM governs only the bank's own rails. | M | H | Real limit on relevance. |
| D-3 | **Adoption chicken-and-egg.** Banks adopt only if agents exist; agents adopt only if banks offer it. | H | H | Unaddressed. |
| D-4 | **Legal non-recognition.** Courts or regulators may not treat the evidence or mandate semantics as meaningful; "mandate" has defined meaning in some jurisdictions (e.g. Québec). The AI is not a legal person; this is stated everywhere. | M | M–H | Not resolved by technology. |
| D-5 | **Unproven.** One implementation, authored and attacked by the same team, no pilot. | H | H | Biggest strategic risk. The proof harness makes claims *falsifiable*; external replication is invited. |
| D-6 | **Governance vacuum.** No steward for the vocabulary, policy catalogue or reference implementation. | H | M | Open. |

## E. When you should NOT use KYM

* Your agents only **read** data and never initiate money movement: scopes plus consent management are enough.
* You need only a single per-transaction cap and nothing stateful: OAuth with RAR (or card-network limits) is simpler (the proof shows static RAR stops swaps and over-limit payments).
* You cannot operate a low-latency, highly available enforcement point on the bank's critical path.
* You expect it to prevent harm from within-mandate mistakes or malicious-but-permitted requests.

## F. Pre-mortem: the most likely story of failure

*Banks built it and customers ignored the summaries; most approvals were clicked through; mandates were broad because narrow ones were annoying; incidents occurred inside mandates; the bank's lawyers used the receipts to argue consent; payment networks shipped their own agent credentials and banks had no say.* None of that is prevented by this code. The mitigations are product design, regulation and ecosystem politics, which is why the repository labels itself a proof of concept for a *control-plane idea*, not a solution to agentic risk.

## G. How to challenge this register

Run `make redteam`, read [docs/redteam/latest.md](../redteam/latest.md), and add attacks to `apps/api/kym/redteam.py`. Pull requests that add a failing attack are more valuable than praise.
