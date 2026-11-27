# ADR-0008: Simulated customer authentication and consent, explicitly labelled

**Status:** accepted

Customer sign-in uses role sessions without passwords; consent and approvals are signed with server-held demo keys. Every consent receipt and approval grant carries `assurance: DEMO_SIMULATED_SESSION` and the legal note that a valid signature proves integrity and key control, not legally effective consent. The scenario runner performs customer approval steps as actor `demo_scenario_runner` (`customer_simulated_by_runner`) so evidence never looks like real customer consent. Production: OIDC login with passkeys (WebAuthn), step-up for approvals, customer-held signing keys or qualified signatures where law requires.
