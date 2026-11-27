"""Isolated SPARQL executor: runs in a child process so a runaway query can be killed (threads cannot be).

Reads {"nt": <graph as N-Triples>, "query": str, "limit": int, "cpu": int} on stdin; writes a JSON result on stdout.
Applies RLIMIT_CPU (and RLIMIT_AS where the OS enforces it). The child has no database or network access by design.
"""
from __future__ import annotations

import json
import sys


def main() -> None:
    req = json.load(sys.stdin)
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (req["cpu"], req["cpu"]))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
        except (ValueError, OSError):
            pass
    except ImportError:
        pass
    from rdflib import XSD, Graph, Namespace
    from rdflib.namespace import RDFS

    ns = {"kym": Namespace("https://example.org/kym/v1#"), "kymid": Namespace("https://example.org/kym/id/"), "prov": Namespace("http://www.w3.org/ns/prov#"),
          "odrl": Namespace("http://www.w3.org/ns/odrl/2/"), "xsd": XSD, "rdfs": RDFS}
    g = Graph()
    g.parse(data=req["nt"], format="nt")
    res = g.query(req["query"], initNs=ns)
    if res.type == "ASK":
        out = {"type": "ASK", "boolean": bool(res.askAnswer), "vars": [], "rows": []}
    else:
        vars_ = [str(v) for v in res.vars]
        rows = []
        for r in res:
            rows.append({v: (None if r[v] is None else str(r[v])) for v in vars_})
            if len(rows) >= req["limit"]:
                break
        out = {"type": "SELECT", "vars": vars_, "rows": rows, "truncated": len(rows) >= req["limit"]}
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
