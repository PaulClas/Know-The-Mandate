"""Protocol adapters. Transport and communication protocols are NOT authorization: every adapter normalizes into the same
policy enforcement point (gateway.handle), so MCP, A2A and agentic-commerce messages are governed exactly like HTTP calls.
"""
from __future__ import annotations

import json

from . import compliance, gateway

REGISTRY = [
    {"id": "http", "name": "Bank HTTP API (/bank)", "status": "implemented", "notes": "Reference path through the PEP."},
    {"id": "mcp", "name": "Model Context Protocol (restricted bank tools)", "status": "sandbox_adapter",
     "notes": "JSON-RPC tools/list and tools/call shapes routed into the PEP. Not a conformant MCP server (no initialize/transport negotiation). Tool discovery is NOT permission to execute."},
    {"id": "ap2", "name": "Google AP2 (Agent Payments Protocol)", "status": "conceptual_mapping", "notes": "Mapping of mandate artifacts to KYM concepts only. No AP2 message parsing, signing or interoperability."},
    {"id": "a2a", "name": "Agent2Agent (A2A)", "status": "extension_interface", "notes": "Interface only: an A2A message would be normalized to an operation and sent through the PEP. Not implemented."},
    {"id": "acp", "name": "Agentic Commerce Protocol", "status": "extension_interface", "notes": "Interface only."},
    {"id": "visa", "name": "Visa agentic commerce infrastructure", "status": "extension_interface", "notes": "Interface only. No Visa API used."},
    {"id": "mastercard", "name": "Mastercard Agent Pay", "status": "extension_interface", "notes": "Interface only. No Mastercard API used."},
    {"id": "x402", "name": "x402", "status": "extension_interface", "notes": "Interface only."},
]

TOOLS = [
    {"name": "get_accounts", "description": "List accounts the mandate permits you to read.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_balance", "description": "Read one account balance (requires balances.read in the mandate).", "inputSchema": {"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]}},
    {"name": "get_transactions", "description": "Read transactions of one account (requires transactions.read).", "inputSchema": {"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]}},
    {"name": "propose_payment", "description": "Prepare (not execute) a payment. Preparing does not authorize execution.", "inputSchema": {"type": "object", "properties": {"account_id": {"type": "string"}, "beneficiary_id": {"type": "string"}, "amount_minor": {"type": "integer"}, "currency": {"type": "string"}, "purpose": {"type": "string"}}, "required": ["account_id", "beneficiary_id", "amount_minor", "currency"]}},
    {"name": "initiate_payment", "description": "Submit a payment for policy enforcement. May be denied, require human approval or be referred to risk review.", "inputSchema": {"type": "object", "properties": {"account_id": {"type": "string"}, "beneficiary_id": {"type": "string"}, "amount_minor": {"type": "integer"}, "currency": {"type": "string"}, "purpose": {"type": "string"}, "idempotency_key": {"type": "string"}, "approval_id": {"type": "string"}}, "required": ["account_id", "beneficiary_id", "amount_minor", "currency", "idempotency_key"]}},
]


def mcp_handle(payload: dict, caller: gateway.Caller) -> dict:
    rid = payload.get("id")
    method = payload.get("method")
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS, "_note": "Discovery only. Calling a tool still requires a valid mandate-bound token and passes the policy enforcement point."}}
    if method != "tools/call":
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not supported by this sandbox adapter"}}
    p = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    name, a = p.get("name"), p.get("arguments") if isinstance(p.get("arguments"), dict) else {}
    if name == "get_accounts":
        st, body = gateway.list_accounts(caller)
    elif name in ("get_balance", "get_transactions"):
        st, body = gateway.read_data(caller, "balances.read" if name == "get_balance" else "transactions.read", a.get("account_id", ""))
    elif name == "propose_payment":
        st, body = gateway.handle(caller, {**a, "kind": "PREPARE"})
    elif name == "initiate_payment":
        st, body = gateway.handle(caller, {**{k: v for k, v in a.items() if k != "idempotency_key"}, "kind": "PAYMENT"}, idempotency_key=a.get("idempotency_key"))
    else:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
    body = {k: v for k, v in body.items() if k != "_data"}
    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": json.dumps(body)}], "isError": st >= 400, "_http_status": st}}


def ap2_map(artifact_type: str, payload: dict | None = None) -> dict:
    m = compliance.ap2_mapping()
    hit = [a for a in m["artifacts"] if artifact_type.lower() in a["ap2_artifact"].lower()]
    return {"status": "conceptual_mapping", "ap2_version_observed": m["ap2_version_observed"], "date_verified": m["date_verified"], "matches": hit,
            "kym_separation": ["customer intent (mandate)", "checkout details (hashed into the operation hash)", "payment authorization (approval + decision certificate)",
                               "bank-side authorization constraints (PDP, risk, policy)", "execution evidence (ledger)"],
            "warning": "No AP2 message was parsed or produced. This is a mapping, not interoperability."}
