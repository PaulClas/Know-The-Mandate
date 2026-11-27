# Roadmap

Honest status: a proof of concept. Items are ordered by how much they reduce the biggest disclosed risks, not by feature appeal. Nothing here is a commitment.

## Next (reduce disclosed risk)
- [ ] Independent security review and external replication of `make redteam` (O-21, D-5).
- [ ] Real customer authentication: OIDC with passkeys/WebAuthn; HttpOnly cookies + CSP in the UI (O-01, O-14).
- [ ] Row-level locking / serializable isolation so budgets hold across processes (O-03).
- [ ] Operator dual control and admin-read logging (O-04, O-19).
- [ ] Terse agent-facing denials to reduce policy reconnaissance (O-15).
- [ ] DPoP server nonces (O-06).

## Then (strengthen the evidence story)
- [ ] KMS/HSM-backed signing; WORM/RFC 3161/external witness for checkpoints (O-07).
- [ ] Mandate-level multi-signatory policy for businesses (O-05).
- [ ] DST/month-boundary property tests for budgets (O-20).
- [ ] Hash-locked dependencies, SBOM, SCA in CI (O-13).

## Explore
- [ ] User research on consent summaries and approval fatigue (risks C-1, C-2).
- [ ] Interoperability tests with a certified authorization server (FAPI 2.0) and an MCP client.
- [ ] Mapping KYM budgets/revocation onto emerging OAuth RAR + Grant Management practice, or retiring the KYM vocabulary if standards cover it (D-1).
- [ ] Optional Rego/Cedar backend behind the policy snapshot seam.

## Done
See [CHANGELOG.md](CHANGELOG.md).
