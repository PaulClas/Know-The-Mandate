import pytest
from helpers import make_mandate
from rdflib import RDF, Graph, Literal, Namespace

from kym import canon
from kym import ontology_service as o
from kym.schemas import Mandate

KYM = Namespace("https://example.org/kym/v1#")


def graph_for(m):
    mm = Mandate.model_validate(m)
    return o.mandate_graph(mm, canon.digest(mm.model_dump()))


def test_valid_mandate_graph_conforms_to_shacl():
    r = o.validate_graph(graph_for(make_mandate()))
    assert r["conforms"], r["results"]


def test_money_moving_permission_without_max_amount_violates_shacl():
    m = make_mandate()
    m["permissions"][1]["constraints"].pop("maximum_amount_minor")
    r = o.validate_graph(graph_for(m))
    assert not r["conforms"] and any("maximum per-transaction amount" in x["message"] for x in r["results"])


def test_invalid_graph_is_rejected():
    g = Graph()
    mi = o.mandate_iri("bad", 1)
    g.add((mi, RDF.type, KYM.Mandate))
    g.add((mi, KYM.validFrom, Literal("not-a-date")))
    r = o.validate_graph(g)
    assert not r["conforms"]
    msgs = " ".join(x["message"] for x in r["results"])
    assert "principal" in msgs and "mandatary" in msgs and "purpose" in msgs


def test_child_expiring_after_parent_violates_shacl():
    parent = make_mandate()
    child = make_mandate(mandate_id="mdt_c", lineage={"parent_mandate_id": "mdt_t1", "parent_mandate_version": 1, "depth": 1})
    cm = Mandate.model_validate(child)
    g = o.mandate_graph(cm, canon.digest(cm.model_dump()))
    parent_late = make_mandate()
    parent_late["validity"]["expires_at"] = "2000-01-02T00:00:00Z"
    parent_late["validity"]["not_before"] = "2000-01-01T00:00:00Z"
    o.add_parent_facts(g, Mandate.model_validate(parent_late), "x")
    r = o.validate_graph(g)
    assert not r["conforms"] and any("expire after its parent" in x["message"] for x in r["results"])
    assert parent


def test_jsonld_roundtrip_preserves_triples():
    g = graph_for(make_mandate())
    doc = o.to_jsonld(g)
    g2 = Graph().parse(data=__import__("json").dumps(doc), format="json-ld")
    assert len(g2) == len(g)


@pytest.mark.parametrize("q", [
    "SELECT * WHERE { SERVICE <http://evil.example/sparql> { ?s ?p ?o } }", "SELECT * FROM <http://evil.example/data> WHERE { ?s ?p ?o }",
    "DELETE WHERE { ?s ?p ?o }", "INSERT DATA { <a:b> <a:c> <a:d> }", "LOAD <http://evil.example/x>", "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", "x" * 5000,
])
def test_sparql_guard_rejects_unsafe_queries(q):
    with pytest.raises(o.SparqlError):
        o.safe_sparql(graph_for(make_mandate()), q)


def test_sparql_select_works_and_limits_rows():
    g = graph_for(make_mandate())
    res = o.safe_sparql(g, "SELECT ?s ?p ?o WHERE { ?s ?p ?o }", limit=5)
    assert len(res["rows"]) == 5 and res["truncated"]


def test_action_taxonomy_has_no_implicit_inheritance():
    from kym import taxonomy

    assert taxonomy.explicit_implications() == {}
    assert taxonomy.BY_ID["payments.prepare"].group != taxonomy.BY_ID["payments.initiate"].group
