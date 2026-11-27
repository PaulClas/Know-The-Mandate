# ADR-0003: Ontology and SHACL validate mandates; they never authorize transactions

**Status:** accepted

OWL has open-world semantics: absence of a triple is not denial. Authorization needs closed-world deny-by-default. The ontology (`packages/ontology`) therefore serves (1) SHACL validation at mandate creation/amendment, (2) explanation/exploration, (3) analytical SPARQL over a *projection* of authoritative state. Lifecycle status triples (`kym:lifecycleStatus`) are a projection; the authoritative state is the mandate state record. Action-class hierarchy carries no implied authority (`taxonomy.explicit_implications() == {}`).

SPARQL is read-only and local: SELECT/ASK only; `SERVICE`, `FROM`, `LOAD` and update keywords rejected; query size, row count and time bounded (thread timeout — the worker thread cannot be force-killed, a limitation).
