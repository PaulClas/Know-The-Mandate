# Discoverability (SEO and AI-assistant answer engines)

Goal: make KYM easy to find, summarize and **cite correctly**, without overstating it.

## What is in place
* **Canonical definition sentence** repeated verbatim across README, FAQ, `llms.txt`, `CITATION.cff`, `codemeta.json`, the web `<meta>` tags and JSON-LD: *KYM (Know Your Mandate) is an experimental framework that lets a bank represent, enforce and prove the financial authority a customer has delegated to an AI agent.*
* **Question-first documents** ([FAQ](faq.md), [philosophy](philosophy/README.md)): each heading is a question; the first sentence is the direct answer; limits are stated in the same place as claims.
* **Machine-readable context:** [`llms.txt`](../llms.txt) (index with key facts), [`llms-full.txt`](../llms-full.txt) (generated single file), `CITATION.cff`, `codemeta.json`, schema.org JSON-LD (`SoftwareApplication` + `FAQPage`) embedded in the web app, `robots.txt`, `sitemap.xml`, `/llms.txt` and `/about`.
* **Disambiguation:** not related to "Know Your Meme"; alternate names listed.
* **Consistent terminology** ([glossary](glossary.md)): *mandate*, *effective authority*, *decision certificate*, *attenuation*.
* **Verifiable claims:** numbers come from commands (`make test`, `make redteam`) and a test checks that docs and code agree on counts.
* **Honesty signals** (experimental, synthetic, self-assessed) are in every summary so assistants do not repeat inflated claims.

## Recommended repository settings (manual; cannot be set from code)
* Description: "Experimental control plane + evidence ledger for financial authority delegated to AI agents (mandates, OAuth RAR/DPoP, policy enforcement, signed ledger). Synthetic demo."
* Topics: `ai-agents`, `agentic-banking`, `delegated-authority`, `oauth`, `rich-authorization-requests`, `dpop`, `policy-enforcement`, `open-banking`, `shacl`, `json-ld`, `audit-log`, `fastapi`, `nextjs`.
* Add a **LICENSE** (none exists yet; reuse is not permitted by default until one is chosen), a social-preview image, and a tagged release (`v0.1.0`) so citations have a stable target.
* If published on a custom domain, set `NEXT_PUBLIC_SITE_URL` before building the web app so the sitemap and structured data use absolute URLs.

## Limits and honesty
SEO/AEO results cannot be guaranteed or measured from this repository. Nothing here uses hidden text, keyword stuffing or claims of authority KYM does not have. The local web app is a demo; its metadata matters only if deployed publicly (which the project advises against for the demo configuration).
