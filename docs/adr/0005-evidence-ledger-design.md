# ADR-0005: Signed hash chain with external checkpoints (no blockchain)

**Status:** accepted

Events are canonicalized with RFC 8785, hashed with SHA-256 under a length-prefixed domain separator (`KYM-EVIDENCE-EVENT-V1`), chained via `previous_hash`, and signed with Ed25519 (`KYM-EVIDENCE-SIG-V1`). Payloads live in a separate protected store; the chain commits to `payload_digest`, so payloads can be erased (crypto-shredding style) without breaking verification. Signed checkpoints (ledger key + independent witness key) are exported to files outside the database so truncation and history rewriting are detectable even if the database is edited.

**Not provided:** protection against an administrator who replaces the database **and** all keys and checkpoints. Production alternatives: HSM-backed signing, WORM storage, RFC 3161 timestamping, Merkle transparency logs, external audit witnesses, permissioned ledgers only where justified. A public blockchain is deliberately not used.
