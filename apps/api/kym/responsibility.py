"""Responsibility mapping: factual attribution of who did and controlled what. It NEVER determines legal liability."""
from __future__ import annotations

ROLES = [
    ("customer", "Customer", "Grants authority; holds the consent receipt copy"),
    ("bank", "Bank (Meridian)", "Governs access to its infrastructure; evaluates mandates; executes payments; holds the evidence ledger"),
    ("agent_developer", "Agent developer", "Built the agent software; supplies build provenance"),
    ("agent_operator", "Agent operator", "Operates the deployed agent; protects its credentials"),
    ("model_provider", "Model provider", "Provides the model the agent uses; not involved in authorization"),
    ("payment_processor", "Payment processor", "Executes settlement (simulated by the Meridian payment engine)"),
    ("merchant", "Merchant / beneficiary", "Receives funds; supplies invoice or checkout details"),
    ("open_banking_intermediary", "Open banking intermediary", "Carries data/payment requests (here: the bank gateway itself)"),
    ("authentication_provider", "Authentication provider", "Authenticates the customer (simulated bank session)"),
    ("human_approver", "Human approver", "Approves a specific operation"),
]

STEPS = [
    ("requested", "Who requested the operation", "agent_operator"),
    ("granted", "Who granted authority", "customer"),
    ("authenticated", "Who authenticated the customer", "authentication_provider"),
    ("agent_verified", "Who verified the agent", "bank"),
    ("mandate_evaluated", "Who evaluated the mandate", "bank"),
    ("screened", "Who performed transaction screening", "bank"),
    ("approved", "Who approved the operation", "human_approver"),
    ("executed", "Who executed the payment", "payment_processor"),
    ("evidence_held", "Who holds the relevant evidence", "bank"),
]

FAULTS = [
    {"id": "agent_exceeded_authority", "title": "Agent exceeded delegated authority",
     "factual": "Compare the requested operation with the mandate version and the policy decision trace. If the bank denied it, no funds moved.",
     "contractual": "Operator terms, agent developer terms and customer agreement allocate responsibility for agent behavior.",
     "potential_legal": "Agency/mandate law of the applicable jurisdiction (e.g. Civil Code of Québec arts. 2130 ff. where applicable) and consumer protection rules may apply.",
     "evidence": ["mandate document and digest", "policy decision trace", "operation payload hash", "ledger events"]},
    {"id": "bank_executed_despite_denial", "title": "Bank executed an operation despite a policy denial",
     "factual": "Look for a PAYMENT_EXECUTED event whose decision certificate is not ALLOW or whose operation hash differs. The payment engine is designed to reject this.",
     "contractual": "Account agreement, open banking participant agreements.",
     "potential_legal": "Payment-service and consumer-protection rules; operational resilience and third-party risk expectations.",
     "evidence": ["decision certificate", "payment execution event", "double-entry postings"]},
    {"id": "operator_credential_failure", "title": "Agent operator failed to protect credentials",
     "factual": "Token issuance records, DPoP key thumbprint, source of the request, agent security posture and incident history.",
     "contractual": "Operator obligations under the agent registration and participant terms.",
     "potential_legal": "Security-safeguard obligations (e.g. privacy and information-security laws) may be relevant.",
     "evidence": ["TOKEN_ISSUED events", "agent incident history", "DPoP binding"]},
    {"id": "merchant_changed_details", "title": "Merchant submitted different payment details",
     "factual": "Compare the approved operation hash with the executed operation; check beneficiary, amount and reference.",
     "contractual": "Merchant agreements and invoice terms.",
     "potential_legal": "Fraud, misrepresentation and payments law.",
     "evidence": ["human approval operation hash", "executed operation", "invoice/reference"]},
    {"id": "approval_compromised", "title": "Authentication or approval evidence was compromised",
     "factual": "KYM cannot prove who was at the keyboard. Demo approvals use a simulated session and server-held key; this is stated in every receipt.",
     "contractual": "Authentication provider and bank customer agreements.",
     "potential_legal": "Unauthorized-transaction and electronic-fund-transfer rules.",
     "evidence": ["consent receipt assurance level", "approval grant events", "authentication logs (external)"]},
    {"id": "risk_controls_failed", "title": "Transaction risk controls failed to identify a suspicious pattern",
     "factual": "Review the risk assessment signals and thresholds applied at the time; synthetic signals in this demo.",
     "contractual": "Bank internal policy and processor agreements.",
     "potential_legal": "Financial-crime control obligations; supervisory expectations.",
     "evidence": ["RISK_EVALUATED event", "risk thresholds and policy version"]},
]

LEVELS = [
    ("factual", "Factual responsibility", "Which party performed or controlled each step. Established from signed evidence."),
    ("contractual", "Contractual responsibility", "How contracts allocate risk between parties. Requires the contracts."),
    ("potential_legal", "Potential legal liability", "Possible exposure under applicable law. Requires legal analysis."),
    ("adjudicated", "Final adjudicated liability", "Decided by a court, tribunal or other competent body. NOT decided by this system."),
]


def matrix() -> dict:
    return {"roles": [{"id": r, "name": n, "description": d} for r, n, d in ROLES], "steps": [{"id": s, "question": q, "default_role": r} for s, q, r in STEPS],
            "levels": [{"id": i, "name": n, "description": d} for i, n, d in LEVELS], "faults": FAULTS,
            "disclaimer": "Attribution of who did what. It does not determine fault or legal liability."}


def attribution(*, principal_name: str, agent: dict, operator_name: str, approvers: list[str], executed: bool, ledger_ref: str, approved_by_customer: bool = True) -> list[dict]:
    rows = [
        ("requested", f"{agent['display_name']} ({agent['id']})", f"operated by {operator_name}", "Agent runtime (outside the bank's control)"),
        ("granted", principal_name, "mandate consent receipt", "Customer"),
        ("authenticated", "Meridian demo identity provider", "simulated bank session (not passkey)", "Bank-controlled"),
        ("agent_verified", "Meridian Know Your Agent service", "attestation checks recorded at AGENT_VERIFIED", "Bank-controlled"),
        ("mandate_evaluated", "Meridian policy decision point", "POLICY_EVALUATED event + replayable inputs", "Bank-controlled"),
        ("screened", "Meridian synthetic risk engine", "RISK_EVALUATED event", "Bank-controlled"),
        ("approved", ", ".join(approvers) if approvers else "no human approval required/obtained", "HUMAN_APPROVAL_* events", "Human approver, bank-controlled interface"),
        ("executed", "Meridian payment engine (simulated processor)" if executed else "not executed", "PAYMENT_EXECUTED event + postings", "Bank-controlled"),
        ("evidence_held", "Meridian evidence ledger (bank); consent receipt copy (customer); runtime logs (operator)", ledger_ref, "Shared"),
    ]
    q = {s: question for s, question, _ in STEPS}
    return [{"step": s, "question": q[s], "party": p, "evidence": e, "system_control": c, "level": "factual"} for s, p, e, c in rows]


CAN_ESTABLISH = [
    "Which registered agent, operator and mandate version were involved, and the mandate's digest.",
    "That a consent receipt bound to the mandate digest exists and its signature verifies under the recorded key.",
    "The exact operation requested, the policy version applied, the decision, reason codes and each check performed (replayable).",
    "Risk signals and thresholds used (synthetic in this demo), any human approvals and the operation hash they were bound to.",
    "Whether the payment engine executed, and the balanced double-entry postings.",
    "That the signed ledger events are intact, in order, and consistent with exported checkpoints.",
]
CANNOT_ESTABLISH = [
    "That the customer's consent was legally effective: demo consent uses a simulated session and server-held demo key.",
    "Who was physically present at the keyboard, or the absence of fraud, coercion or misrepresentation.",
    "Whether the agent's action matched the customer's real-world intent when it stayed within the mandate.",
    "Contractual allocation of loss between parties, or any legal liability. These are for contracts, regulators and courts.",
    "That wholesale replacement of the database and signing keys did not occur, beyond the external checkpoints provided.",
]
