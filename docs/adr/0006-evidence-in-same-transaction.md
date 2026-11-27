# ADR-0006: Evidence events share the transaction of the state change (instead of an outbox)

**Status:** accepted

The brief asks for a transactional outbox *or equivalent*. Because the accounting tables and the evidence ledger live in the same database, `ledger.append` runs inside the same `db.write()` transaction as the financial state change: both commit or neither does. If the ledger were a separate service, an outbox table drained by a relay with idempotent consumers would be required.
