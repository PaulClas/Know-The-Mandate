# ADR-0007: Atomic budgets via a serialized write transaction

**Status:** accepted · **Limitation recorded**

Policy evaluation, budget accounting (executed + reserved, calendar day/month in the mandate's budget timezone, summed across the delegation chain), reservation and execution run inside one `db.write()` transaction guarded by a process-level `RLock`. Scenario H and an 8-thread integration test show exactly as many payments succeed as the budget allows.

**Limitation.** The lock is per process. Multi-process or multi-node deployment needs database-level concurrency control (`SELECT … FOR UPDATE` on mandate budget rows, or serializable isolation with retry). SQLite and PostgreSQL 14 (single process) were exercised.
