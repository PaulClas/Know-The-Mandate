# Regulatory mapping

This folder-level note explains how KYM (Know Your Mandate) maps legal and regulatory sources to demo capabilities. The control records live in:

- [`policies/canada/controls.json`](../../policies/canada/controls.json) (jurisdiction `CA`)
- [`policies/quebec/controls.json`](../../policies/quebec/controls.json) (jurisdiction `CA-QC`)
- [`policies/united-states/controls.json`](../../policies/united-states/controls.json) (jurisdiction `US`)
- [`policies/jurisdiction-profiles.json`](../../policies/jurisdiction-profiles.json) (short profile per jurisdiction)

## Important caveats

- **Not legal advice.** The mappings are the KYM authors' research notes for a technical demonstration.
- **Not compliant or certified.** KYM is a proof-of-concept for a fictional bank ("Meridian Bank") with synthetic data. It is **not** compliant with, conformant to, or certified against any law, regulation, guideline or standard. `implementation_status` is deliberately never `implemented`; the highest value used is `simulated`.
- **Status changes.** Several sources are mid-change (the Canadian Consumer-Driven Banking Act is mostly not yet in force; the CFPB's 1033 rule has stayed compliance dates and is being reconsidered). Re-check before relying on any record.
- **No assumption that an AI agent is a legal person or mandatary/agent at law.** Mandate and agency material is a design analogy.
- **No single US law** governs AI-agent mandates; agency, contract and funds-transfer authorization are largely state law.

## Approach

1. Identify the primary source (statute, regulation, guideline) and fetch it from an official site. Record the provision, version/currency and the verification date.
2. Record the **current status** factually (in force, not yet in force, stayed, proposed, draft, unverified) and what is unverified.
3. Map to a KYM capability (`related_kym_capability`) and state conservatively how far the demo goes (`implementation_status`) and its `limitations`.
4. List the **evidence** a real deployment would need (`evidence_required`).
5. If a source could not be fetched or verified, set `date_verified` to `null` and say "unverified" in `current_status`. Never infer provisions that were not read.

### Record fields
`id`, `jurisdiction`, `source`, `source_type`, `source_url`, `provision`, `source_version`, `date_verified` (YYYY-MM-DD or `null`), `current_status`, `applicability`, `related_kym_capability`, `implementation_status`, `limitations`, `evidence_required`.

### `source_type` taxonomy

| Value | Meaning |
|---|---|
| `enacted_law` | A statute or duly made regulation/rule text. It may be only partly in force, stayed or under reconsideration - see `current_status` |
| `operative_requirement` | A requirement applied to regulated parties through a regulator's mandate or program (e.g. supervisory regime) rather than a single statutory provision |
| `proposed_regulation` | Published proposal, draft, ANPR or consultation; not final |
| `supervisory_guidance` | Regulator guidance or guidelines; expectations rather than law |
| `industry_standard` | Standards-body or industry specification (no records currently use this value) |
| `kym_proposal` | KYM's own design note or analogy; not a legal requirement |

### `implementation_status` values
`mapped` = documented correspondence only; `simulated` = the demo imitates the behaviour with synthetic data; `not_implemented` = nothing in the demo (used for a placeholder); `implemented` is intentionally not used for legal compliance.

## Notable findings

- **Canada - data access vs payment initiation.** The Consumer-Driven Banking Act (S.C. 2026, c. 3, s. 224, assented 2026-03-26) is a framework for consumer-directed *data sharing* supervised by the Bank of Canada. Per the Justice Laws consolidation current to 2026-11-12, only a limited set of provisions is in force; the rest awaits an order in council (s. 181). No payment-initiation functionality was found in the Act text; the Department of Finance's Budget 2025 document says write access (such as payments) is to be considered in a second phase. KYM therefore keeps data-access scopes and payment authority separate as its own design choice.
- **Quebec - mandate vocabulary.** Civil Code of Québec arts. 2130, 2135, 2138-2142, 2157-2160, 2175-2181 were read in the LégisQuébec consolidation current to 2026-10-15. Art. 2181 (revocation notified only to the mandatary does not affect a third person unaware of it) motivates bank-side, per-request revocation checks. Law 25's s. 12.1 (automated decisions) was verified. AMF guidance could not be retrieved and is marked unverified.
- **United States - CFPB 1033.** Compliance dates were stayed on 2025-10-29 in *Forcht Bank, N.A., et al. v. CFPB*, No. 5:24-cv-304-DCR (E.D. Ky.) per the CFPB's page (last modified 2026-01-06); an ANPR on reconsideration issued 2025-08-22; the CFPB's August 2026 regulatory agenda lists a planned reconsideration rulemaking. Developments after January 2026 were not independently verified.

## Summary: Canada (`CA`)

| Control ID | Source | Source type | Status | Date verified |
|---|---|---|---|---|
| CA-CDBA-01 | Consumer-Driven Banking Act (S.C. 2026, c. 3, s. 224) | enacted_law | Enacted 2026-03-26; most provisions not yet in force (s. 181) | 2026-11-26 |
| CA-CDBA-02 | CDBA - express consent, duration, renewal, withdrawal (ss. 85-90) | enacted_law | Enacted; not yet in force | 2026-11-26 |
| CA-CDBA-03 | CDBA - scope: data sharing vs payment initiation; Budget 2025 framework | enacted_law | Act covers data sharing; payment initiation not established (Finance: possible later phase) | 2026-11-26 |
| CA-CDBA-04 | Bank of Canada supervision; proposed CDBA regulations (Canada Gazette Part I) | proposed_regulation | Proposed regulations / draft guidelines; consultation closes 2026-12-08 | 2026-11-26 |
| CA-CDBA-05 | CDBA - security safeguards and breach reporting | enacted_law | Enacted; not yet in force; safeguards defined in proposed regulations | 2026-11-26 |
| CA-PIPEDA-01 | PIPEDA - consent (s. 6.1; Sch. 1 cl. 4.3, 4.4) | enacted_law | In force | 2026-11-26 |
| CA-PIPEDA-02 | PIPEDA - breach reporting (s. 10.1; cl. 4.7) | enacted_law | In force | 2026-11-26 |
| CA-PCMLTFA-01 | PCMLTFA - compliance program (s. 9.6) | enacted_law | In force | 2026-11-26 |
| CA-FINTRAC-01 | FINTRAC guidance (compliance program; identity verification) | supervisory_guidance | Guidance pages retrieved | 2026-11-26 |
| CA-RPAA-01 | Retail Payment Activities Act (payment functions) | enacted_law | In force; Bank of Canada supervises PSPs | 2026-11-26 |
| CA-RPAA-02 | Bank of Canada retail payments supervision | operative_requirement | Supervisory page retrieved | 2026-11-26 |
| CA-OSFI-B13 | OSFI B-13 Technology and Cyber Risk Management | supervisory_guidance | Published guideline (2022-07-31) | 2026-11-26 |
| CA-OSFI-B10 | OSFI B-10 Third-Party Risk Management | supervisory_guidance | Published guideline (2023-04-30) | 2026-11-26 |
| CA-OSFI-E21 | OSFI E-21 Operational Risk Management and Resilience | supervisory_guidance | Published guideline (2024-08-22) | 2026-11-26 |

## Summary: Quebec (`CA-QC`)

| Control ID | Source | Source type | Status | Date verified |
|---|---|---|---|---|
| QC-CCQ-01 | Civil Code of Québec arts. 2130, 2135 (mandate; scope) | enacted_law | In force | 2026-11-26 |
| QC-CCQ-02 | CCQ arts. 2138-2139 (mandatary's duties) | enacted_law | In force | 2026-11-26 |
| QC-CCQ-03 | CCQ arts. 2140-2142 (substitution and delegation) | enacted_law | In force | 2026-11-26 |
| QC-CCQ-04 | CCQ arts. 2157, 2158, 2160 (third-party effects) | enacted_law | In force | 2026-11-26 |
| QC-CCQ-05 | CCQ arts. 2175-2181 (revocation, renunciation) | enacted_law | In force | 2026-11-26 |
| QC-P39-01 | Private sector Act s. 12.1 (automated decisions) | enacted_law | In force | 2026-11-26 |
| QC-P39-02 | Private sector Act ss. 13-14 (consent) | enacted_law | In force | 2026-11-26 |
| QC-P39-03 | Private sector Act ss. 4-5 (collection limits) | enacted_law | In force | 2026-11-26 |
| QC-P39-04 | Private sector Act s. 3.5 (confidentiality incidents), s. 10 | enacted_law | In force (s. 3.5 text verified) | 2026-11-26 |
| QC-CAI-01 | CAI guidance for private enterprises | supervisory_guidance | Guidance pages exist; content not reviewed in detail | 2026-11-26 |
| QC-AMF-01 | AMF guidelines (not identified) | supervisory_guidance | **Unverified** (site not retrievable) | null |
| QC-CFL-01 | Charter of the French language s. 55 | enacted_law | In force; relevance to KYM consent not determined | 2026-11-26 |

## Summary: United States (`US`)

| Control ID | Source | Source type | Status | Date verified |
|---|---|---|---|---|
| US-DFA1033-01 | Dodd-Frank s. 1033 (12 U.S.C. 5533) | enacted_law | Statute in force | 2026-11-26 |
| US-CFPB1033-02 | CFPB rule, 12 CFR part 1033 - status | enacted_law | Codified; compliance dates **stayed** (E.D. Ky., 2025-10-29); under reconsideration; later developments unverified | 2026-11-26 |
| US-CFPB1033-03 | 12 CFR 1033.401, 1033.421 (authorized third parties) | enacted_law | Codified; stayed/under reconsideration | 2026-11-26 |
| US-CFPB1033-04 | 12 CFR 1033.211, 1033.331 (covered data; authentication) | enacted_law | Codified; stayed/under reconsideration | 2026-11-26 |
| US-CFPB1033-05 | CFPB ANPR, Personal Financial Data Rights Reconsideration (90 FR 40986) | proposed_regulation | ANPR only (2025-08-22) | 2026-11-26 |
| US-REGE-01 | EFTA / Regulation E (12 CFR 1005) | enacted_law | In force; application to AI-agent transfers unsettled | 2026-11-26 |
| US-GLBA-01 | GLBA safeguards: Interagency Guidelines (12 CFR 30 App. B); 15 U.S.C. 6801 | enacted_law | In force | 2026-11-26 |
| US-GLBA-02 | Regulation P (12 CFR 1016) | enacted_law | In force | 2026-11-26 |
| US-TPRM-01 | Interagency Guidance on Third-Party Relationships (88 FR 37920) | supervisory_guidance | Final non-binding guidance (2023-06-09) | 2026-11-26 |
| US-BSA-01 | BSA regulations for banks (31 CFR 1020.210, 1020.220) | enacted_law | In force as retrieved | 2026-11-26 |
| US-UCC4A-01 | UCC Article 4A (4A-201, 4A-202) | enacted_law | Uniform text verified; state enactments not checked | 2026-11-26 |
| US-ESIGN-01 | E-SIGN, 15 U.S.C. 7001(h) (electronic agents) | enacted_law | In force | 2026-11-26 |
| US-AGENCY-01 | State agency/contract law (design note) | kym_proposal | **Unverified** | null |

## Facts that could not be verified

- AMF (Québec) guideline titles and provisions (site returned HTTP 403/404 to automated retrieval).
- The text of the Canada Gazette Part I notices (proposed CDBA regulations of 2026-06-27; 2026-11-21 designation notice); only the Bank of Canada's description of them was read.
- Court docket status for *Forcht Bank v. CFPB* and any CFPB proposal after January 2026.
- Effective dates and transition arrangements of OSFI B-13, B-10 and E-21.
- State-level UCC 4A enactments, UETA variants and state agency law; the ALI Restatement (Third) of Agency text.
- OSFI guidance on model risk management, FinCEN suspicious activity reporting rules and any pending AML/CFT program rule changes were not reviewed.
