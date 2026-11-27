# ADR-0001: Modular monolith instead of microservices

**Status:** accepted · **Date:** 2026-11-26

**Context.** The brief lists 17 logical components (identity, registry, attestation, compiler, ontology, registry, consent, OAuth, PDP, PEP, risk, approvals, gateway, payment engine, ledger, disputes, regulatory mapping) and warns against unnecessary microservices and empty abstractions.

**Decision.** One FastAPI process with explicit module boundaries (see `AGENTS.md`). Pure modules (`policy`, `risk`, `canon`) have no I/O. Money movement is reachable only through `gateway.handle` → `bank.execute_authorized`. The agent side (`agent_sdk`, `sandbox`) talks HTTP only, in-process via an ASGI client or over the network.

**Consequences.** Atomic "decide + reserve + execute + record evidence" in one transaction; trivial local startup. A real deployment would put the payment engine and evidence ledger behind separate trust boundaries with mutual authentication (gap analysis §Isolation). The directory layout in the brief (`services/*`) is not materialized to avoid empty placeholders.
