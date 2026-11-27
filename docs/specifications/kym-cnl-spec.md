# KYM-CNL 1.0.0 — controlled mandate language (experimental)

Inspired by the *principles* of ASD-STE100 Simplified Technical English (controlled vocabulary, short declarative statements, one instruction per statement). **No claim of ASD-STE100 compliance** is made. Grammar: [`packages/controlled-language/kym-cnl.lark`](../../packages/controlled-language/kym-cnl.lark) (Lark LALR).

```
PURPOSE household_bill_management.
PERMIT agent.finance-assistant TO READ_BALANCE ON account.chequing-001.
PERMIT agent.finance-assistant TO PAY_INVOICE FROM account.chequing-001 TO beneficiary.hydro-quebec
  WITH MAX_AMOUNT 250 CAD PER TRANSACTION.
LIMIT TOTAL_PAYMENTS TO 500 CAD PER CALENDAR_MONTH.
REQUIRE HUMAN_APPROVAL FOR PAYMENTS ABOVE 100 CAD.        # REQUIRE 2 HUMAN_APPROVALS ... for two signatories
PROHIBIT EXTERNAL_TRANSFER.   PROHIBIT DELEGATION.        # or: ALLOW DELEGATION TO DEPTH 1.
EXPIRE AT 2027-01-01T00:00:00Z.
```

Synonyms (`ALLOW`=`PERMIT`, `FORBID`=`PROHIBIT`), clause order, and money spellings (`250 CAD`, `CAD 250.00`) normalize to identical output and digest (tested). Read verbs use `ON`; money-moving verbs use `FROM … TO … WITH MAX_AMOUNT … PER TRANSACTION` (all mandatory). References (`agent.x`, `account.x`, `beneficiary.x`, `merchant.x`, `category.mcc`, `country.xx`) must resolve in the registry — **nothing is invented**. Missing purpose, expiry, amount, counterparty or resource is a compile error. Defaults (start time, jurisdiction, timezone) are reported in `defaults_applied`.

Ambiguity detection (`cnl.detect_ambiguities`) flags vague free text ("usual bills", "some savings", "whenever it makes sense", "too much") with the question the customer must answer; `propose_cnl` builds CNL **only** from explicitly resolved values. An optional LLM may propose CNL text but cannot issue or approve a mandate: output must pass the deterministic compiler, validation and explicit customer approval.

Compiler outputs (`POST /api/mandates/compile`): original intent, normalized CNL, ambiguities, AST, mandate JSON, JSON-LD (+Turtle), SHACL report, OAuth scopes + RAR, runtime policy, EN/FR consent summary, canonical digest, effective permissions.
