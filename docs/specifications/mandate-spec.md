# KYM mandate specification (experimental v1.0.0)

Namespace: `https://example.org/kym/v1#` — **experimental placeholder, not a standard**. JSON Schema: [`packages/mandate-schema/mandate.schema.json`](../../packages/mandate-schema/mandate.schema.json) (generated from `apps/api/kym/schemas.py`; a test fails if it drifts). TypeScript mirror: `apps/web/lib/types.ts`.

## Document

Fields follow the project brief. Additions: top-level `currency` (single currency per mandate), `permissions[].constraints.allowed_merchants|allowed_destination_accounts`, `lineage` (child mandates), `obligations.required_approvals`. Rules enforced by the model: integer minor units (no floats), UTC timestamps `YYYY-MM-DDTHH:MM:SSZ`, IANA `budget_timezone`, permit/prohibit conflict rejected, delegation depth 0 when delegation disallowed, unknown fields rejected.

Digest: `sha256:` of the RFC 8785 canonical JSON of the content (`canon.digest`). Lifecycle status, counters and revocation are **not** part of the signed content.

## Action taxonomy (no implicit inheritance)

`ReadFinancialData` (accounts.read, balances.read, transactions.read, accounts.owner.read, data.transmit_external) · `AnalyzeFinancialData` (analysis.*) · `PrepareFinancialOperation` (payments.prepare, transfers.prepare, investments.prepare) · `ExecuteFinancialOperation` (payments.initiate, payments.pay_invoice, purchases.goods, transfers.execute (internal), transfers.external, investments.trade) · `ManageFinancialAuthority` (mandates.request, mandates.delegate, mandates.revoke). Preparing ≠ executing; balance ≠ transactions; internal ≠ external transfer.

## Decisions and reason codes

Decisions: `ALLOW`, `DENY`, `REQUIRE_HUMAN_APPROVAL`, `REFER_TO_RISK_REVIEW`. Base reason codes: AGENT_NOT_VERIFIED, AGENT_SUSPENDED, INVALID_TOKEN, INVALID_ACTOR_BINDING, TOKEN_SCOPE_INSUFFICIENT, MANDATE_NOT_FOUND, MANDATE_EXPIRED, MANDATE_REVOKED, MANDATE_VERSION_MISMATCH, RESOURCE_NOT_AUTHORIZED, ACTION_NOT_AUTHORIZED, PURPOSE_NOT_AUTHORIZED, BENEFICIARY_NOT_AUTHORIZED, CURRENCY_NOT_AUTHORIZED, TRANSACTION_LIMIT_EXCEEDED, DAILY_LIMIT_EXCEEDED, MONTHLY_LIMIT_EXCEEDED, DELEGATION_NOT_ALLOWED, DELEGATION_EXCEEDS_PARENT, HUMAN_APPROVAL_REQUIRED, RISK_THRESHOLD_EXCEEDED.

KYM extensions (documented additions): CUSTOMER_NOT_VERIFIED, ACCOUNT_RESTRICTED, MANDATE_NOT_YET_VALID, MANDATE_SUSPENDED, MERCHANT_NOT_AUTHORIZED, DELEGATION_CYCLE, APPROVAL_INVALID, POLICY_INPUT_UNVERIFIABLE, RISK_REVIEW_REQUIRED.

## Credentials (proposed extensions)

Access token: ES256 JWT with `iss`, `sub` (customer), `aud` (`https://bank.example/api`), `client_id`, `act.sub` (agent; nested for exchanged tokens), `scope`, `jti`, `iat`, `exp` (5 min), `cnf.jkt`, `authorization_details` (RFC 9396, type `kym_financial_mandate`) and the proposed claims `https://example.org/kym/mandate_id|mandate_version|mandate_hash`. These claims and the RAR type are **KYM proposals, not IETF-standardized**.

Illustrative scopes (bank-defined): accounts.read, balances.read, transactions.read, payments.prepare, payments.initiate, transfers.initiate. Scopes cannot express account, beneficiary, amount, cumulative limit, purpose, schedule, delegation depth, approvals or revocation state — those live in the RAR and the server-side mandate (`taxonomy.SCOPE_GAPS`).

## Budgets

Calendar day/month windows are computed in the mandate's `budget_timezone` (wall-clock midnight, DST-safe) and converted to UTC instants. Usage = executed + reserved money-moving transactions whose `mandate_chain` contains the mandate (so a child consumes its own and every ancestor's budget).

## Open-banking API note

`GET /bank/accounts[/{id}[/balances|/transactions]]` resemble FDX-style account/balance/transaction resources (field names are KYM-sandbox, not FDX schemas; FDX conformance is not claimed). `POST /bank/payments`, `/bank/payments/proposals`, `/bank/transfers` and the decision/approval model are KYM sandbox extensions. Data-access and payment-initiation authority are separate: a token for balances.read cannot move money.
