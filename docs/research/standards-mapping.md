# Standards mapping

**KYM (Know Your Mandate)** is a proof-of-concept for a fictional bank, "Meridian Bank". All data is synthetic. Nothing here is compliant with, conformant to, or certified against any standard. Statements below describe what the demo code does, what it only simulates, and what is only a conceptual mapping.

- Verification date for the official URLs and version notes: **2026-11-26**. URLs were fetched and confirmed reachable on that date; where a version or status is noted it was read from the fetched page.
- Machine-readable counterpart: [`standards/standards.json`](../../standards/standards.json) (feeds the UI "Standards and regulatory mapping" page).
- The authorization server in the demo is a **sandbox**, not a certified or complete OAuth/OpenID server.

## How to read the columns

| Column | Meaning |
|---|---|
| Reused | A term, claim, format or concept from the standard is reused as-is |
| Implemented in KYM demo | Demo code implements the behaviour (sandbox quality) |
| Simulated | A sandbox adapter imitates the behaviour; not a complete implementation |
| Conceptually mapped | Documented correspondence only; no code |
| KYM proposes beyond it | KYM experimental extension that is not part of the standard |
| Interoperability tested? | Tested against independent implementations or conformance suites. **No** for every row unless stated |

## 1. IETF OAuth and related RFCs

| Standard | Official source | Reused | Implemented in KYM demo | Simulated | Conceptually mapped | KYM proposes beyond it | Interoperability tested? |
|---|---|---|---|---|---|---|---|
| RFC 6749 OAuth 2.0 Authorization Framework | https://www.rfc-editor.org/rfc/rfc6749 | Yes (roles, endpoints, error model) | Yes - sandbox AS, subset of flows | - | - | - | No |
| RFC 7636 PKCE | https://www.rfc-editor.org/rfc/rfc7636 | Yes | Yes - sandbox AS | - | - | - | No |
| RFC 7009 Token Revocation | https://www.rfc-editor.org/rfc/rfc7009 | Yes | Yes - sandbox AS | - | - | Mandate revocation checked on every request regardless of token validity | No |
| RFC 7662 Token Introspection | https://www.rfc-editor.org/rfc/rfc7662 | Yes | Yes - sandbox AS | - | - | - | No |
| RFC 8693 Token Exchange | https://www.rfc-editor.org/rfc/rfc8693 | Yes (`act` claim) | - | Yes - sandbox adapter | - | - | No |
| RFC 8705 mTLS client auth / certificate-bound tokens | https://www.rfc-editor.org/rfc/rfc8705 | - | - | - | Yes (mapped only; demo has no mTLS) | - | No |
| RFC 8707 Resource Indicators | https://www.rfc-editor.org/rfc/rfc8707 | Yes (audience) | Yes - implemented as an audience (`aud`) check | - | - | - | No |
| RFC 8785 JSON Canonicalization Scheme (Informational) | https://www.rfc-editor.org/rfc/rfc8785 | Yes | Yes - `rfc8785` library for ledger and mandate digests | - | - | - | No |
| RFC 9068 JWT Profile for OAuth 2.0 Access Tokens | https://www.rfc-editor.org/rfc/rfc9068 | Yes (claims) | Yes - real ES256 signatures (PyJWT); the evidence ledger uses Ed25519, RFC 9068-style claims, sandbox AS (not a certified server) | - | - | Mandate claims (see section 6) | No |
| RFC 9126 Pushed Authorization Requests | https://www.rfc-editor.org/rfc/rfc9126 | Yes | - | Yes - sandbox adapter | - | - | No |
| RFC 9396 Rich Authorization Requests | https://www.rfc-editor.org/rfc/rfc9396 | Yes (`authorization_details`) | Yes - parsing and validation in sandbox AS | - | - | `kym_financial_mandate` type (see section 6) | No |
| RFC 9449 DPoP | https://www.rfc-editor.org/rfc/rfc9449 | Yes | Yes - proof validation in sandbox AS: `cnf.jkt` binding, `htm`/`htu`/`iat`/`ath` checks, `jti` replay | - | - | - | No |
| RFC 9700 OAuth 2.0 Security BCP | https://www.rfc-editor.org/rfc/rfc9700 | Design guidance | - | - | Yes (no conformance assessment) | - | No |

## 2. OpenID Foundation

| Standard | Official source | Reused | Implemented in KYM demo | Simulated | Conceptually mapped | KYM proposes beyond it | Interoperability tested? |
|---|---|---|---|---|---|---|---|
| OpenID Connect Core 1.0 | https://openid.net/specs/openid-connect-core-1_0.html | - | - | Customer authentication is a simulated bank session, not OIDC | Yes | - | No |
| FAPI 2.0 Security Profile (Final, 2025-02-22 per page header) | https://openid.net/specs/fapi-security-profile-2_0.html | Building blocks (PKCE, DPoP) | - | PAR simulated | Yes. No FAPI 2.0 conformance or certification claimed | - | No |
| Grant Management for OAuth 2.0 (formerly "FAPI Grant Management"; page title shows Draft) | https://openid.net/specs/oauth-v2-grant-management.html | - | - | - | Yes (grant/mandate lifecycle) | - | No |
| Shared Signals Framework 1.0 | https://openid.net/specs/openid-sharedsignals-framework-1_0.html | - | - | - | Yes (revocation/risk signal propagation; no transmitter/receiver) | - | No |
| CAEP 1.0 | https://openid.net/specs/openid-caep-1_0.html | - | - | - | Yes (per-request revocation and risk re-evaluation; no events emitted) | - | No |

## 3. W3C and semantic web

| Standard | Official source | Reused | Implemented in KYM demo | Simulated | Conceptually mapped | KYM proposes beyond it | Interoperability tested? |
|---|---|---|---|---|---|---|---|
| RDF 1.1 Concepts (RDF 1.2 Concepts page also exists) | https://www.w3.org/TR/rdf11-concepts/ | Yes | Yes - rdflib | - | - | KYM ontology v1 | No |
| OWL 2 | https://www.w3.org/TR/owl2-overview/ | Yes (constructs) | Vocabulary authored. **No reasoner is used for authorization** | - | Yes | KYM ontology v1 | No |
| JSON-LD 1.1 | https://www.w3.org/TR/json-ld11/ | Yes | Yes - rdflib | - | - | - | No |
| SHACL | https://www.w3.org/TR/shacl/ | Yes | Yes - pySHACL | - | - | KYM shapes | No |
| ODRL Information Model 2.2 | https://www.w3.org/TR/odrl-model/ | Yes (terms) | Terms reused in the ontology; no ODRL policy engine or profile conformance | - | - | - | No |
| PROV-O | https://www.w3.org/TR/prov-o/ | Yes (terms) | Terms reused for decision/evidence provenance | - | - | - | No |
| Verifiable Credentials Data Model v2.0 | https://www.w3.org/TR/vc-data-model-2.0/ | - | - | - | Yes (the KYM mandate is a signed JWT, not a VC) | - | No |

## 4. Financial data and agentic commerce

| Standard | Official source | Reused | Implemented in KYM demo | Simulated | Conceptually mapped | KYM proposes beyond it | Interoperability tested? |
|---|---|---|---|---|---|---|---|
| FDX API | https://financialdataexchange.org/ | - | - | - | Yes (data-access scopes; spec not reviewed in detail) | - | No |
| Google AP2 (v0.2.0 observed) | https://github.com/google-agentic-commerce/AP2 | - | - | - | Yes - see [ap2-mapping.md](ap2-mapping.md) | Bank-side constraints and execution evidence beyond AP2's merchant/payment focus | No |
| Visa Intelligent Commerce | https://developer.visa.com/docs/visa-intelligent-commerce | - | - | - | Yes (docs not reviewed in detail) | - | No |
| Visa Trusted Agent Protocol | https://github.com/visa/trusted-agent-protocol | - | - | - | Yes (repo not reviewed in detail) | - | No |
| Mastercard Agent Pay | https://www.mastercard.com/us/en/business/artificial-intelligence/mastercard-agent-pay.html | - | - | - | Yes (product page only) | - | No |
| Agentic Commerce Protocol (OpenAI / Stripe) | https://github.com/agentic-commerce-protocol/agentic-commerce-protocol (also https://www.agenticcommerce.dev/) | - | - | - | Yes (repo not reviewed in detail) | - | No |
| x402 | https://github.com/coinbase/x402 (project site https://x402.org/) | - | - | - | Yes | - | No |
| Model Context Protocol (MCP) - latest revision resolved to 2026-07-28 | https://modelcontextprotocol.io/specification/latest | Tool-list shape | - | Yes - restricted tool interface sandbox exposing a tool-list shape. **Discovery is not permission**: listing a tool grants no authority | Authorization spec: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization (not implemented) | Deny-by-default tool authorization via the PDP | No - not tested against real MCP clients |
| Agent2Agent (A2A) - page lists 1.0.0 as latest release | https://a2a-protocol.org/latest/specification/ | - | - | - | Yes | - | No |

## 5. Controlled language, policy engines, workload identity and security guidance

| Standard | Official source | Reused | Implemented in KYM demo | Simulated | Conceptually mapped | KYM proposes beyond it | Interoperability tested? |
|---|---|---|---|---|---|---|---|
| ASD-STE100 Simplified Technical English | https://asd-ste100.org/ | - | - | - | Yes (inspiration only; KYM-CNL claims no STE conformance) | KYM-CNL | No |
| SPIFFE / SPIRE | https://spiffe.io/docs/latest/spiffe-about/overview/ | - | - | - | Yes (not used; demo keys in local files) | - | No |
| Open Policy Agent | https://www.openpolicyagent.org/docs | - | **Not used** (typed Python policy engine) | - | Yes (mapping documented conceptually) | - | No |
| Cedar (AWS) | https://docs.cedarpolicy.com/ | - | **Not used** (typed Python policy engine) | - | Yes (mapping documented conceptually) | - | No |
| NIST SP 800-63-4 | https://pages.nist.gov/800-63-4/ | - | - | Customer session simulated; no passkeys; no assurance level claimed | Yes | - | No |
| NIST SP 800-207 Zero Trust Architecture | https://csrc.nist.gov/pubs/sp/800/207/final | - | - | - | Yes (deny-by-default PDP, per-request evaluation) | - | No |
| NIST AI Risk Management Framework | https://www.nist.gov/itl/ai-risk-management-framework | - | - | - | Yes (no AI RMF assessment performed) | - | No |
| OWASP Top 10 for Agentic Applications 2026 / Agentic AI Threats and Mitigations | https://genai.owasp.org/top-10-for-agentic-applications-2026/ ; https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/ | - | - | - | Yes (threat model references item names) | - | No |
| OWASP Top 10 for LLM Applications | https://genai.owasp.org/llm-top-10/ | - | - | - | Yes (threat model references item names) | - | No |
| OWASP API Security Top 10 2023 | https://owasp.org/API-Security/editions/2023/en/0x11-t10/ | - | - | - | Yes | - | No |
| RFC 3161 Time-Stamp Protocol | https://www.rfc-editor.org/rfc/rfc3161 | - | - | - | Production-hardening option; not implemented | - | No |
| RFC 6962 Certificate Transparency | https://www.rfc-editor.org/rfc/rfc6962 | - | - | - | Reference for a Merkle transparency log; not implemented | - | No |

## 6. KYM experimental extensions (proposed, not standards)

These use the non-resolving placeholder namespace `https://example.org/kym/...`. They are not registered with IANA or any standards body.

| Extension | Where it plugs in | Status | Interoperability tested? |
|---|---|---|---|
| `kym_financial_mandate` RAR `authorization_details` type | RFC 9396 | Proposed; parsed and validated in the sandbox AS | No |
| KYM mandate JWT claims (`https://example.org/kym/mandate_id` and related claims) | RFC 9068-style access tokens | Proposed | No |
| KYM ontology v1 (`https://example.org/kym/v1#`) | RDF / OWL 2 / SHACL / PROV-O / ODRL | Proposed | No |
| KYM-CNL | Controlled natural language for mandates | Proposed | No |
| KYM Evidence Ledger | RFC 8785 canonical JSON; Ed25519-signed, hash-chained, signed checkpoints | Proposed | No |

## 7. Enterprise identity references

The demo signs tokens and ledger entries with **demo keys stored in local files** and issues agent identities from a sandbox. A real deployment would replace these with platform-issued workload identity. The pages below were fetched and confirmed to exist on 2026-11-26; the "how it could be used" text is KYM's design suggestion, not a statement by the vendors, and no integration has been built or tested.

| Reference | Official URL | How real workload identity could replace demo keys |
|---|---|---|
| SPIFFE / SPIRE concepts | https://spiffe.io/docs/latest/spire-about/spire-concepts/ ; https://spiffe.io/docs/latest/spiffe-specs/spiffe/ | Agent runtimes obtain short-lived SPIFFE identities (SVIDs) attested by the platform instead of a static key file; the PDP and payment engine verify the SPIFFE ID and bind it to the agent record. |
| AWS STS and IAM OIDC federation | https://docs.aws.amazon.com/STS/latest/APIReference/ ; https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_oidc.html | Agent workloads on AWS exchange an OIDC token for short-lived role credentials instead of holding long-lived secrets; signing keys for decisions and ledger would sit in a managed key service (an HSM/KMS is a production-hardening item, not in the demo). |
| Amazon Bedrock AgentCore Identity | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/identity.html | Vendor documentation on identity and credential management for agent applications; a candidate source of agent identity assertions for the "agent identity" input to KYM. Not evaluated in depth. |
| Microsoft Entra Agent ID and Workload ID | https://learn.microsoft.com/en-us/entra/agent-id/what-are-agent-identities ; https://learn.microsoft.com/en-us/entra/workload-id/workload-identities-overview | Agents registered as non-human identities in the enterprise directory, with lifecycle and revocation, could populate the KYM agent registry; this would help with non-human identity sprawl. |
| Google Cloud Workload Identity Federation and Agent Identity | https://docs.cloud.google.com/iam/docs/workload-identity-federation ; https://docs.cloud.google.com/iam/docs/agent-identity-overview | External or cloud workloads federate to short-lived credentials without service-account keys; agent identity could be the verified source of the agent subject in tokens. |

**Not included:** IBM and Anthropic enterprise agent-identity documentation. No specific official page was verified for these during research, so none is listed. (The MCP authorization specification above is a protocol document, not an Anthropic enterprise identity guide.)

## 8. Open items

- Details of FDX, Visa, Mastercard, ACP and x402 specifications were not reviewed beyond confirming that the official pages exist; the mapping rows above for those are placeholders for future review.
- No interoperability or conformance testing has been performed against any standard.
