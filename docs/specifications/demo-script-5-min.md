# Five-minute live demonstration

Setup: `make demo`, open http://localhost:3000, `make reset-demo` first for a clean state. Use the header user switcher.

| Min | Page / user | Say | Show |
|---|---|---|---|
| 0:00 | Overview (admin) | "Banks already answer who the customer is, who the agent is and what API a client can call. They don't capture the *delegated authority*. KYM makes the mandate a governed object." | Tagline, KPIs, ledger integrity badge, synthetic-demo notice |
| 0:45 | **Scenarios → C** (admin) | "Valid token, valid agent — still denied." | Run C: OAuth verification PASS (introspection active, `payments.initiate` in scope), mandate verification FAIL `BENEFICIARY_NOT_AUTHORIZED`, no funds moved |
| 1:30 | Mandate studio (Alice) | "A vague instruction can't become authority." | Paste the vague sentence → unresolved ambiguities. Load the CNL example → normalized CNL, JSON mandate, JSON-LD, SHACL conforms, scopes vs RAR vs "what scopes cannot express", EN/FR consent summary, digest |
| 2:15 | Create → Portal (Alice) | "Approval happens in the bank's interface, not the agent's chat." | Create mandate → Approve (digest-bound receipt, assurance label "simulated session") → Activate |
| 2:45 | Sandbox (Alice) | "The agent proposes." | Household Bill Payment Agent: "Pay CAD 85 to Hydro-Québec" (executes), "Pay CAD 180…" (approval needed), "Pay CAD 50 to Vidéotron" (denied) — stepper shows OAuth → mandate → risk → decision → ledger |
| 3:30 | Portal (Alice) | "One-time approval doesn't widen the mandate." | Approve the CAD 180 once; then Revoke the mandate |
| 4:00 | Scenarios → F, J | "Revocation beats a still-valid token; an approval can't be substituted." | F: retry denied `MANDATE_REVOKED`. J: CAD 190 vs approved CAD 180 rejected |
| 4:20 | Ledger → Verify integrity; Scenario L | "The ledger remembers." | Chain verifies; tampered copies fail |
| 4:40 | Disputes | "Who did what, provably — and what remains a legal question." | Pick a transaction → timeline, responsibility matrix, can/cannot establish, download package |
| 5:00 | Close | "The agent proposes. The mandate authorizes. The bank enforces. The ledger remembers." | |

Honest caveats to state: synthetic data; sandbox OAuth; simulated approvals; not compliant or certified.
