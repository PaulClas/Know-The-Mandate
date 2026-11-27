# Benchmarks

`make benchmark` measures authorization latency with real calls, no estimates, and writes [latest.json](latest.json). It does not benchmark throughput under concurrency.

| Path | p50 | p95 | p99 | n |
|---|---|---|---|---|
| Pure PDP evaluation (`policy.evaluate`) | 0.076 ms | 0.088 ms | 0.135 ms | 20,000 |
| HTTP read, end to end through gateway | 6.7 ms | 8.1 ms | 9.5 ms | 300 |
| HTTP payment, end to end (token checks, PDP, ledger, double-entry posting, signed evidence) | 18.9 ms | 24.7 ms | 37.0 ms | 300 |

## Read these numbers carefully

* Single process, SQLite, in-process ASGI test client, one laptop. They indicate order of magnitude only.
* The pure PDP is cheap because it is a deterministic function over a JSON snapshot. Most payment time is database writes and Ed25519 signing, not policy evaluation.
* No network latency, no PostgreSQL, no concurrent load, no real identity provider.
* Re-run on your hardware before quoting anything. Numbers in this file are overwritten by `make benchmark`.
