# Domain name options (parked, no purchase decided)

**Status: no custom domain is registered or planned yet.** For now the canonical home of KYM is the GitHub repository, <https://github.com/PaulClas/Know-Your-Mandate>. This page records the research so the decision can be made later without redoing it.

## Why not `knowyourmandate.com`

A registry lookup on 2026-11-27 showed `knowyourmandate.com` is already registered (by a third party; the maintainer reports it is used by an anonymous Substack publication). KYM does not compete with it, imitate it or claim it. When a site exists it should say plainly that it is **not** that publication and **not** "Know Your Meme".

## Candidates and registry status (checked 2026-11-27)

Checked with RDAP registry lookups. "Not found" means the registry returned no record; it is **not** a guarantee the name can be bought (premium pricing, reserved names and registrar-side holds are not visible). Re-check at a registrar before relying on any of this.

| Domain | Registry result | Notes |
|---|---|---|
| `knowyourmandate.com` | Registered | Not available |
| `agentmandate.com`, `agentmandates.com`, `mandateledger.com` | Registered | Not available |
| `knowyourmandate.org` | Not found | **Preferred if a domain is ever bought**: exact name, and `.org` suits an open, Apache-2.0, disclosure-first project |
| `knowyourmandate.dev`, `knowyourmandate.ai` | Not found | Reasonable defensive redirects |
| `kymandate.com`, `kymandate.org` | Not found | Short, but easy to mistype and reads less clearly |
| `kymframework.com`, `kymframework.org` | Not found | Implies a framework others use, which is premature |
| `mandatekit.org` | Not found | Generic; weaker tie to the project name |

## If a domain is bought later

1. Register the canonical domain (preferred: `knowyourmandate.org`) with registrar lock and auto-renew, and consider the defensive redirects above.
2. Make the site state "Not Know Your Meme; not the Substack of the same name" prominently.
3. Set it as the repository website, then update `CITATION.cff` (`url`), `codemeta.json` (`url`), `llms.txt`, and `.github/repo-metadata.json` (`homepage`), and add `sameAs` links between the site and the repository in JSON-LD.
4. Follow [discoverability.md](discoverability.md) for crawler, `llms.txt` and structured-data setup, and the claims rules in [media-guide.md](media-guide.md).
5. Run a trademark search first if the name will be used commercially. This page is not legal advice.

## Costs and trade-offs

A domain adds an annual fee, DNS and email-security work (SPF, DKIM, DMARC if mail is used), and a long-term commitment to keep links stable. It makes the project look more established than a single maintainer's experimental proof of concept actually is; the [claims policy](media-guide.md) applies to any site.
