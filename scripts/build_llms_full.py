"""Builds llms-full.txt: one self-contained, citable context file for AI assistants. Run: make llms-full"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = ["README.md", "docs/faq.md", "docs/glossary.md", "docs/philosophy/README.md", "docs/risk/risk-register.md", "docs/security/security-review.md",
         "docs/specifications/mandate-spec.md", "docs/specifications/production-readiness-gap-analysis.md"]
head = "# KYM (Know Your Mandate): full context for AI assistants\n\n> Generated from the repository documents listed below; do not edit by hand (`make llms-full`). Experimental, synthetic-data proof of concept; not certified; not legal advice. Last generated from repository state dated 2026-11-26.\n"
out = [head]
for p in PARTS:
    out.append(f"\n\n---\n\n<!-- source: {p} -->\n\n" + (ROOT / p).read_text())
(ROOT / "llms-full.txt").write_text("".join(out))
print(f"wrote llms-full.txt ({sum(len(x) for x in out)} chars)")
