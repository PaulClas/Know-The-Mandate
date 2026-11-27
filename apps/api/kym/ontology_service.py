"""Semantic layer: ontology loading, mandate graph construction, SHACL validation, JSON-LD, safe SPARQL.

The graph is used for (a) validating mandates at creation/amendment time, (b) explanation and
exploration and (c) analytical SPARQL queries. It is never consulted to authorize a transaction.
"""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import timedelta
from functools import lru_cache

from pyshacl import validate as shacl_validate
from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef
from rdflib.plugins.sparql import prepareQuery
from sqlalchemy import select

from . import clock, config, db, taxonomy
from .schemas import Mandate

KYM = Namespace(config.KYM_NS)
KID = Namespace("https://example.org/kym/id/")
PROV = Namespace("http://www.w3.org/ns/prov#")
ODRL = Namespace("http://www.w3.org/ns/odrl/2/")

ONT_DIR = config.PACKAGES / "ontology"
_graph_lock = threading.Lock()


@lru_cache
def ontology() -> Graph:
    g = Graph()
    g.parse(ONT_DIR / "kym-v1.ttl", format="turtle")
    return g


@lru_cache
def shapes() -> Graph:
    g = Graph()
    g.parse(ONT_DIR / "shapes.ttl", format="turtle")
    return g


@lru_cache
def jsonld_context() -> dict:
    return json.loads((ONT_DIR / "context.jsonld").read_text())


def bind(g: Graph) -> Graph:
    for p, ns in (("kym", KYM), ("kymid", KID), ("prov", PROV), ("odrl", ODRL)):
        g.bind(p, ns)
    return g


def _dt(ts: str) -> Literal:
    return Literal(ts, datatype=XSD.dateTime)


def _int(v: int) -> Literal:
    return Literal(int(v), datatype=XSD.integer)


def mandate_iri(mandate_id: str, version: int) -> URIRef:
    return KID[f"mandate/{mandate_id}/v{version}"]


def action_class(action_id: str) -> URIRef:
    return KYM[taxonomy.BY_ID[action_id].cls]


def mandate_graph(m: Mandate, digest: str, *, operator_name: str | None = None) -> Graph:
    g = bind(Graph())
    mi = mandate_iri(m.mandate_id, m.version)
    g.add((mi, RDF.type, KYM.Mandate))
    g.add((mi, RDF.type, KYM.MandateVersion))
    g.add((mi, KYM.mandateVersion, _int(m.version)))
    g.add((mi, KYM.policyVersion, Literal(m.policy_version)))
    g.add((mi, KYM.ontologyVersion, Literal(m.ontology_version)))
    g.add((mi, KYM.cryptographicDigest, Literal(digest)))
    g.add((mi, KYM.currency, Literal(m.currency)))
    g.add((mi, KYM.validFrom, _dt(m.validity.not_before)))
    g.add((mi, KYM.validUntil, _dt(m.validity.expires_at)))
    g.add((mi, KYM.delegationAllowed, Literal(m.delegation.allowed)))
    g.add((mi, KYM.maximumDelegationDepth, _int(m.delegation.maximum_depth)))

    cust = KID[f"customer/{m.principal.id}"]
    g.add((cust, RDF.type, KYM.Customer))
    g.add((cust, RDF.type, KYM.Organization if m.principal.type == "business" else KYM.Human))
    g.add((cust, KYM.grantsMandate, mi))
    g.add((mi, KYM.hasPrincipal, cust))
    g.add((mi, PROV.wasAttributedTo, cust))

    agent = KID[f"agent/{m.mandatary.agent_id}"]
    op = KID[f"operator/{m.mandatary.operator_id}"]
    g.add((agent, RDF.type, KYM.AIAgent))
    g.add((op, RDF.type, KYM.AgentOperator))
    if operator_name:
        g.add((op, RDFS.label, Literal(operator_name)))
    g.add((op, KYM.operatesAgent, agent))
    g.add((agent, KYM.hasOperator, op))
    g.add((mi, KYM.hasMandatary, agent))
    g.add((agent, PROV.actedOnBehalfOf, cust))

    purpose = KID[f"purpose/{m.purpose}"]
    g.add((purpose, RDF.type, KYM.Purpose))
    g.add((purpose, RDFS.label, Literal(m.purpose)))
    g.add((mi, KYM.hasPurpose, purpose))
    g.add((mi, KYM.governedByPolicy, KID[f"policy/{m.policy_version}"]))

    for j in m.jurisdictions:
        ji = KID[f"jurisdiction/{j}"]
        g.add((ji, RDF.type, KYM.Jurisdiction))
        g.add((mi, KYM.subjectToJurisdiction, ji))

    for i, perm in enumerate(m.permissions):
        pn = KID[f"mandate/{m.mandate_id}/v{m.version}/permission/{i}"]
        g.add((pn, RDF.type, KYM.Permission))
        g.add((pn, RDF.type, ODRL.Permission))
        if perm.action in taxonomy.MONEY_MOVING:
            g.add((pn, RDF.type, KYM.MoneyMovingPermission))
        g.add((action_class(perm.action), RDF.type, KYM.FinancialAction))  # punning: ODRL treats actions as individuals
        g.add((pn, KYM.authorizesAction, action_class(perm.action)))
        g.add((pn, ODRL.action, action_class(perm.action)))
        g.add((mi, KYM.hasPermission, pn))
        g.add((mi, ODRL.permission, pn))
        for r in perm.resources:
            rn = KID[f"account/{r}"]
            g.add((rn, RDF.type, KYM.BankAccount))
            g.add((pn, KYM.appliesToResource, rn))
            g.add((pn, ODRL.target, rn))
        c = perm.constraints
        if any([c.maximum_amount_minor, c.allowed_beneficiaries, c.allowed_merchants, c.allowed_destination_accounts, c.allowed_merchant_categories, c.allowed_countries]):
            cn = KID[f"mandate/{m.mandate_id}/v{m.version}/constraint/{i}"]
            g.add((cn, RDF.type, KYM.Constraint))
            g.add((cn, RDF.type, ODRL.Constraint))
            g.add((pn, KYM.hasConstraint, cn))
            g.add((pn, ODRL.constraint, cn))
            if c.maximum_amount_minor:
                g.add((cn, KYM.maximumAmount, _int(c.maximum_amount_minor)))
                g.add((cn, ODRL.leftOperand, ODRL.payAmount))
                g.add((cn, ODRL.operator, ODRL.lteq))
                g.add((cn, ODRL.rightOperand, _int(c.maximum_amount_minor)))
                g.add((cn, KYM.currency, Literal(c.currency or m.currency)))
            for b in c.allowed_beneficiaries:
                bn = KID[f"beneficiary/{b}"]
                g.add((bn, RDF.type, KYM.Beneficiary))
                g.add((cn, KYM.allowedBeneficiary, bn))
            for mm in c.allowed_merchants:
                mn = KID[f"merchant/{mm}"]
                g.add((mn, RDF.type, KYM.Merchant))
                g.add((cn, KYM.allowedMerchant, mn))
            for da in c.allowed_destination_accounts:
                dn = KID[f"account/{da}"]
                g.add((dn, RDF.type, KYM.BankAccount))
                g.add((cn, KYM.allowedDestinationAccount, dn))
            for mc in c.allowed_merchant_categories:
                g.add((cn, KYM.allowedMerchantCategory, Literal(mc)))
            for co in c.allowed_countries:
                g.add((cn, KYM.allowedCountry, Literal(co)))

    for pa in m.prohibitions:
        pn = KID[f"mandate/{m.mandate_id}/v{m.version}/prohibition/{pa}"]
        g.add((pn, RDF.type, KYM.Prohibition))
        g.add((pn, RDF.type, ODRL.Prohibition))
        g.add((pn, ODRL.action, action_class(pa)))
        g.add((mi, ODRL.prohibition, pn))
        g.add((mi, KYM.prohibitsAction, action_class(pa)))

    a = m.aggregate_constraints
    if a.maximum_daily_amount_minor:
        g.add((mi, KYM.maximumDailyAmount, _int(a.maximum_daily_amount_minor)))
    if a.maximum_monthly_amount_minor:
        g.add((mi, KYM.maximumMonthlyAmount, _int(a.maximum_monthly_amount_minor)))
    if a.maximum_transaction_count_monthly:
        g.add((mi, KYM.maximumTransactionCount, _int(a.maximum_transaction_count_monthly)))

    ob = KID[f"mandate/{m.mandate_id}/v{m.version}/obligation/approval"]
    g.add((ob, RDF.type, KYM.Obligation))
    g.add((ob, RDF.type, ODRL.Duty))
    g.add((ob, KYM.requiredApprovals, _int(m.obligations.required_approvals)))
    if m.obligations.human_approval_above_minor is not None:
        g.add((ob, KYM.humanApprovalAbove, _int(m.obligations.human_approval_above_minor)))
    g.add((mi, KYM.imposesObligation, ob))
    g.add((mi, ODRL.obligation, ob))

    if m.version > 1:
        g.add((mi, KYM.supersedes, mandate_iri(m.mandate_id, m.version - 1)))
        g.add((mandate_iri(m.mandate_id, m.version - 1), RDF.type, KYM.MandateVersion))
    if m.lineage:
        parent = mandate_iri(m.lineage.parent_mandate_id, m.lineage.parent_mandate_version)
        g.add((mi, KYM.derivedFromMandate, parent))
        g.add((parent, KYM.delegatesTo, mi))
        g.add((parent, RDF.type, KYM.MandateVersion))
    return g


def add_parent_facts(g: Graph, parent: Mandate, parent_digest: str) -> None:
    """Include the parent's temporal bounds so child-vs-parent SHACL constraints can be evaluated."""
    pi = mandate_iri(parent.mandate_id, parent.version)
    g.add((pi, KYM.validFrom, _dt(parent.validity.not_before)))
    g.add((pi, KYM.validUntil, _dt(parent.validity.expires_at)))


def validate_graph(data: Graph) -> dict:
    conforms, report_graph, text = shacl_validate(
        data, shacl_graph=shapes(), ont_graph=ontology(), inference="none", abort_on_first=False, advanced=True
    )
    SH = Namespace("http://www.w3.org/ns/shacl#")
    results = []
    for r in report_graph.subjects(RDF.type, SH.ValidationResult):
        results.append(
            {
                "focus_node": str(report_graph.value(r, SH.focusNode) or ""),
                "path": str(report_graph.value(r, SH.resultPath) or ""),
                "message": str(report_graph.value(r, SH.resultMessage) or ""),
                "severity": str(report_graph.value(r, SH.resultSeverity) or "").rsplit("#", 1)[-1],
                "source_shape": str(report_graph.value(r, SH.sourceShape) or "")[-60:],
            }
        )
    results.sort(key=lambda x: (x["focus_node"], x["message"]))
    return {"conforms": bool(conforms), "results": results, "report_text": text}


def to_jsonld(g: Graph) -> dict:
    out = g.serialize(format="json-ld", context=jsonld_context(), auto_compact=True)
    return json.loads(out)


def to_turtle(g: Graph) -> str:
    return g.serialize(format="turtle")


# --------------------------------------------------------------------------- registry graph / SPARQL


def registry_graph(s) -> Graph:
    """Projection of registry, mandate, delegation and transaction state for analytical queries."""
    g = bind(Graph())
    g += ontology()
    for c in s.execute(select(db.Customer)).scalars():
        ci = KID[f"customer/{c.id}"]
        g.add((ci, RDF.type, KYM.Customer))
        g.add((ci, RDFS.label, Literal(c.name)))
        g.add((ci, RDF.type, KYM.Organization if c.type == "business" else KYM.Human))
        g.add((ci, KYM.subjectToJurisdiction, KID[f"jurisdiction/{c.jurisdiction}"]))
    for r in s.execute(select(db.Representative)).scalars():
        g.add((KID[f"customer/{r.person_id}"], RDF.type, KYM.AuthorizedRepresentative))
        g.add((KID[f"customer/{r.person_id}"], KYM.represents, KID[f"customer/{r.business_id}"]))
        g.add((KID[f"customer/{r.business_id}"], KYM.hasSignatory, KID[f"customer/{r.person_id}"]))
    for a in s.execute(select(db.Account).where(db.Account.owner_id.is_not(None))).scalars():
        ai = KID[f"account/{a.id}"]
        g.add((ai, RDF.type, KYM.BankAccount))
        g.add((ai, RDFS.label, Literal(a.name)))
        g.add((KID[f"customer/{a.owner_id}"], KYM.ownsAccount, ai))
        g.add((KID[f"customer/{a.owner_id}"], KYM.controlsResource, ai))
    for p in s.execute(select(db.Payee)).scalars():
        pi = KID[f"{p.kind}/{p.id}"]
        g.add((pi, RDF.type, KYM.Beneficiary if p.kind == "beneficiary" else KYM.Merchant))
        g.add((pi, RDFS.label, Literal(p.name)))
    for ag in s.execute(select(db.Agent)).scalars():
        ai = KID[f"agent/{ag.id}"]
        g.add((ai, RDF.type, KYM.AIAgent))
        g.add((ai, RDFS.label, Literal(ag.display_name)))
        g.add((ai, KYM.operationalStatus, Literal(ag.status)))
        oid = ag.declared.get("operator_id")
        if oid:
            g.add((KID[f"operator/{oid}"], RDF.type, KYM.AgentOperator))
            g.add((KID[f"operator/{oid}"], RDFS.label, Literal(ag.declared.get("operating_organization", oid))))
            g.add((KID[f"operator/{oid}"], KYM.operatesAgent, ai))
    states = {(st.mandate_id, st.version): st for st in s.execute(select(db.MandateState)).scalars()}
    for row in s.execute(select(db.MandateRow)).scalars():
        m = Mandate.model_validate(row.content)
        g += mandate_graph(m, row.digest)
        mi = mandate_iri(m.mandate_id, m.version)
        st = states.get((m.mandate_id, m.version))
        if st:
            g.add((mi, KYM.lifecycleStatus, Literal(st.status)))
            if st.status == "REVOKED":
                rv = KID[f"revocation/{m.mandate_id}/v{m.version}"]
                g.add((rv, RDF.type, KYM.Revocation))
                g.add((mi, KYM.revokedBy, rv))
                g.add((rv, PROV.wasAssociatedWith, KID[f"customer/{m.principal.id}"]))
    for c in s.execute(select(db.Consent)).scalars():
        ci = KID[f"consent/{c.id}"]
        g.add((ci, RDF.type, KYM.Consent))
        g.add((mandate_iri(c.mandate_id, c.version), PROV.wasGeneratedBy, ci))
        g.add((ci, PROV.wasAssociatedWith, KID[f"customer/{c.customer_id}"]))
    for tx in s.execute(select(db.Transaction).where(db.Transaction.kind.in_(["PAYMENT", "TRANSFER"]))).scalars():
        ti = KID[f"tx/{tx.id}"]
        g.add((ti, RDF.type, KYM.Transaction))
        g.add((ti, KYM.amountMinor, _int(tx.amount_minor)))
        g.add((ti, KYM.hasAgent, KID[f"agent/{tx.agent_id}"]))
        g.add((ti, KYM.lifecycleStatus, Literal(tx.status)))
        if tx.mandate_id and tx.status in ("EXECUTED", "RESERVED", "AUTHORIZED"):
            g.add((ti, KYM.authorizedUnderMandate, mandate_iri(tx.mandate_id, tx.mandate_version or 1)))
        if tx.payee_id:
            g.add((ti, KYM.executedBy, KID[f"agent/{tx.agent_id}"]))
        if tx.decision_id:
            di = KID[f"decision/{tx.decision_id}"]
            g.add((di, RDF.type, KYM.PolicyDecision))
            g.add((ti, KYM.hasDecision, di))
    for ap in s.execute(select(db.Approval)).scalars():
        ai = KID[f"approval/{ap.id}"]
        g.add((ai, RDF.type, KYM.Approval))
        g.add((KID[f"tx/{ap.tx_id}"], KYM.hasApproval, ai))
        g.add((KID[f"tx/{ap.tx_id}"], KYM.requiresApproval, ai))
        for gr in ap.grants:
            if gr.get("decision") == "APPROVE":
                g.add((ai, KYM.approvedBy, KID[f"customer/{gr['approver_id']}"]))
    for d in s.execute(select(db.DelegationRow)).scalars():
        g.add((mandate_iri(d.parent_id, d.parent_version), KYM.delegatesTo, mandate_iri(d.child_id, d.child_version)))
        g.add((mandate_iri(d.child_id, d.child_version), KYM.derivedFromMandate, mandate_iri(d.parent_id, d.parent_version)))
    return g


_FORBIDDEN = re.compile(r"(?<![?$\w:])(SERVICE|FROM|LOAD|INSERT|DELETE|CLEAR|DROP|CREATE|COPY|MOVE|ADD|WITH)(?!\w)", re.I)
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sparql")


class SparqlError(ValueError):
    pass


def _walk(node, seen=None):
    seen = seen if seen is not None else set()
    if id(node) in seen:
        return
    seen.add(id(node))
    yield node
    if hasattr(node, "values") and callable(node.values):
        for v in list(node.values()):
            yield from _walk(v, seen)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _walk(v, seen)


def safe_sparql(g: Graph, query: str, *, limit: int = 200, timeout: float = 5.0) -> dict:
    """Read-only SPARQL: SELECT/ASK only, no SERVICE/FROM (no remote federation or loading), bounded size, rows and time."""
    if len(query) > 4000:
        raise SparqlError("query too long (max 4000 characters)")
    stripped = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'|<[^>\s]*>|#[^\n]*', " ", query)
    m = _FORBIDDEN.search(stripped)
    if m:
        raise SparqlError(f"keyword {m.group(1).upper()} is not allowed in read-only local queries")
    try:
        prepared = prepareQuery(query, initNs={"kym": KYM, "kymid": KID, "prov": PROV, "odrl": ODRL, "xsd": XSD, "rdfs": RDFS})
    except Exception as e:  # noqa: BLE001
        raise SparqlError(f"invalid SPARQL: {e}") from e
    if prepared.algebra.name not in ("SelectQuery", "AskQuery"):
        raise SparqlError("only SELECT and ASK queries are allowed")
    for n in _walk(prepared.algebra):
        if getattr(n, "name", "") in ("Service", "ServiceGraphPattern"):
            raise SparqlError("SERVICE (federation) is not allowed")

    def run():
        res = g.query(prepared)
        if res.type == "ASK":
            return {"type": "ASK", "boolean": bool(res.askAnswer), "vars": [], "rows": []}
        vars_ = [str(v) for v in res.vars]
        rows = []
        for r in res:
            rows.append({v: (None if r[v] is None else str(r[v])) for v in vars_})
            if len(rows) >= limit:
                break
        return {"type": "SELECT", "vars": vars_, "rows": rows, "truncated": len(rows) >= limit}

    fut = _pool.submit(run)
    try:
        return fut.result(timeout=timeout)
    except FutureTimeout as e:
        fut.cancel()
        raise SparqlError(f"query exceeded the {timeout}s execution limit") from e


def sparql_examples(account_id: str = "account_001", tx_id: str = "TX") -> list[dict]:
    now = clock.now()
    plus7 = now + timedelta(days=7)
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    return [
        {
            "id": "agents-can-initiate-payments",
            "title": "Which agents can initiate payments from a specific account?",
            "query": f"""SELECT DISTINCT ?agent ?mandate ?status WHERE {{
  ?mandate kym:hasMandatary ?agent ;
           kym:hasPermission ?p ;
           kym:lifecycleStatus ?status .
  ?p kym:authorizesAction kym:InitiatePayment ;
     kym:appliesToResource <https://example.org/kym/id/account/{account_id}> .
  FILTER(?status = "ACTIVE")
}}""",
        },
        {
            "id": "mandates-expiring-soon",
            "title": "Which mandates expire within seven days?",
            "query": f"""SELECT ?mandate ?until WHERE {{
  ?mandate kym:validUntil ?until ; kym:lifecycleStatus "ACTIVE" .
  FILTER(?until > "{iso(now)}"^^xsd:dateTime && ?until <= "{iso(plus7)}"^^xsd:dateTime)
}}""",
        },
        {
            "id": "mandates-for-beneficiary",
            "title": "Which mandates authorize a particular beneficiary?",
            "query": """SELECT DISTINCT ?mandate ?status WHERE {
  ?mandate kym:hasPermission/kym:hasConstraint/kym:allowedBeneficiary <https://example.org/kym/id/beneficiary/beneficiary_hydro_quebec> ;
           kym:lifecycleStatus ?status .
}""",
        },
        {
            "id": "mandate-for-transaction",
            "title": "Which mandate authorized a disputed transaction?",
            "query": f"""SELECT ?tx ?mandate ?digest WHERE {{
  ?tx a kym:Transaction ; kym:authorizedUnderMandate ?mandate .
  ?mandate kym:cryptographicDigest ?digest .
  FILTER(STRENDS(STR(?tx), "{tx_id}"))
}}""",
        },
        {
            "id": "downstream-of-revoked",
            "title": "Which downstream mandates depend on a revoked parent mandate?",
            "query": """SELECT ?parent ?child ?childStatus WHERE {
  ?parent kym:lifecycleStatus "REVOKED" ; kym:delegatesTo+ ?child .
  OPTIONAL { ?child kym:lifecycleStatus ?childStatus }
}""",
        },
        {
            "id": "who-approved",
            "title": "Which party approved a given financial action?",
            "query": """SELECT ?tx ?approval ?approver ?name WHERE {
  ?tx kym:hasApproval ?approval .
  ?approval kym:approvedBy ?approver .
  OPTIONAL { ?approver rdfs:label ?name }
}""",
        },
    ]
