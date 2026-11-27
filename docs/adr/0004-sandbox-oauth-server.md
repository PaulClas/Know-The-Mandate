# ADR-0004: Sandbox OAuth/OIDC adapter built on maintained crypto libraries

**Status:** accepted · **Limitation recorded**

The brief says to integrate a maintained OAuth server and not to create production authentication primitives. In an offline, dependency-light demo, the available Python servers (e.g. Authlib) do not provide RFC 9449 DPoP + RFC 9396 RAR + PAR together out of the box, and running Keycloak/Hydra would break the "start with `make demo`, no external services" goal.

**Decision.** `oauth.py` is a clearly labelled **sandbox adapter**: all signing/verification uses PyJWT and `cryptography` (no custom crypto); protocol logic is minimal and documented. It implements auth-code + PKCE (S256), PAR (simplified, required), confidential clients, RAR validation against the approved mandate, DPoP validation (typ, alg, jwk, signature, htm, htu, iat window, ath, cnf.jkt, jti replay), introspection, revocation, simplified RFC 8693 exchange, ES256 JWT access tokens with `act`, `cnf` and KYM claims. Not implemented: mTLS, refresh tokens, JARM, request objects, dynamic registration, FAPI conformance. Interoperability with third-party clients has **not** been tested.

**Production path.** Keep KYM as the mandate/policy layer; put a FAPI 2.0-certified authorization server in front; map `kym_financial_mandate` RAR + claims through it.
