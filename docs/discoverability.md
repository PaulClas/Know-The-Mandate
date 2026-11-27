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
* Apache-2.0 [LICENSE](../LICENSE) is in place. Still to do by hand: a social-preview image and a tagged release (`v0.1.0`) so citations have a stable target.
* If published on a custom domain, set `NEXT_PUBLIC_SITE_URL` before building the web app so the sitemap and structured data use absolute URLs.

## Limits and honesty
SEO/AEO results cannot be guaranteed or measured from this repository. Nothing here uses hidden text, keyword stuffing or claims of authority KYM does not have. The local web app is a demo; its metadata matters only if deployed publicly (which the project advises against for the demo configuration).

## Applying the GitHub metadata

The description, topics and private vulnerability reporting live in repository settings, not in the code, so they must be set once by the owner. The source of truth is [.github/repo-metadata.json](../.github/repo-metadata.json).

**By hand (about two minutes, no token needed)**

1. Open the repository page, click the gear icon next to **About**, paste the `description`, add each entry of `topics`, and save.
2. Go to **Settings → Code security** (or **Advanced Security**) and enable **Private vulnerability reporting**. [SECURITY.md](../SECURITY.md) and the issue templates point reporters at it.

**By script**

1. Create a fine-grained token at <https://github.com/settings/personal-access-tokens/new>: repository access limited to `PaulClas/Know-Your-Mandate`, permission **Administration: Read and write**. Set a short expiry.
2. `GITHUB_TOKEN=<token> python3 scripts/set_github_metadata.py` (add `--dry-run` first to preview).
3. Delete the token.

## Custom domain

None is registered. Options, registry status and the steps to follow if one is bought are in [domain-options.md](domain-options.md).
