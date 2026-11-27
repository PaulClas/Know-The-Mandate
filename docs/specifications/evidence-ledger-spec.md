# KYM Evidence Ledger specification (experimental)

Records the *exercise of authority* (distinct from the double-entry accounting ledger). Event fields: `event_id, sequence, event_type, timestamp (server, monotonic), actor_id, actor_type, principal_id, agent_id, mandate_id, mandate_version, transaction_id, correlation_id, policy_version, ontology_version, payload_digest, previous_hash, signer_id, signing_key_id` + `event_hash` + `signature`.

* Canonicalization: RFC 8785 (`rfc8785`).
* Hash: `SHA-256( len(domain)[2 bytes] || domain || JCS(body) )`, domain `KYM-EVIDENCE-EVENT-V1`.
* Signature: Ed25519 over `KYM-EVIDENCE-SIG-V1\0 || hash`.
* Checkpoints: `{checkpoint_id, sequence, head_hash, event_count, created_at, ontology_version}`, signed by the ledger key and an independent witness key over `KYM-CHECKPOINT-V1\0 || JCS(body)`; exported to `.kym-data/checkpoints/`.
* Verification (`ledger.verify`, pure, works on copies/packages): hash chain, hashes, signatures, sequence continuity, timestamp ordering, payload digests, checkpoint signatures/head hashes/truncation. `make verify-ledger`, `POST /api/ledger/verify`, offline package verification `POST /api/evidence/verify`.
* Event types: CUSTOMER_VERIFIED, AGENT_REGISTERED/VERIFIED/SUSPENDED, MANDATE_PROPOSED/VALIDATED/APPROVAL_REQUESTED/APPROVED/ACTIVATED/AMENDED/DELEGATED/SUSPENDED/REVOKED/EXPIRED/SUPERSEDED/REJECTED, TOKEN_ISSUED/REJECTED/REVOKED, ACTION_REQUESTED/DENIED, POLICY_EVALUATED, RISK_EVALUATED, HUMAN_APPROVAL_REQUESTED/GRANTED/REJECTED, PAYMENT_EXECUTED/FAILED, DISPUTE_OPENED.
* Privacy: events carry identifiers and digests; payloads sit in a protected store and can be erased without breaking the chain. Reusable tokens and private keys are never stored.

Guarantee level: tamper-**evident** under the assumption that the signing keys or exported checkpoints are not also compromised. See ADR-0005 for production alternatives.
