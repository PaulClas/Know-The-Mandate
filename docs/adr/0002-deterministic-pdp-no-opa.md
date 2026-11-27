# ADR-0002: Typed Python policy engine rather than OPA/Rego

**Status:** accepted

**Context.** OPA is preferred "if practical". The authorization decision must be (a) deterministic, (b) explainable per check with structured reason codes, (c) replayable from a stored snapshot and (d) testable with property-based tests in the same language as the rest of the system.

**Decision.** `policy.evaluate(inputs) -> decision` is a pure Python function over a JSON snapshot. Mandates are compiled to an indexed runtime form (`policy.runtime_policy`, cached by digest). Prohibitions are evaluated first; missing permissions deny; effective authority is the intersection across the delegation chain.

**Consequences.** No cross-process policy server or Rego toolchain; the Hypothesis suite checks invariants (narrowing, attenuation, revocation, cumulative limits, prohibition precedence). Cedar/OPA remain valid production options; the snapshot format is the integration seam.
