#!/usr/bin/env bash
# Compile a mandate and inspect it over plain HTTP against a running demo API (`make api`, port 8000).
# Needs only curl and python3. Demo sessions exist only when KYM_ENV=demo (the default).
set -euo pipefail
API="${KYM_API:-http://127.0.0.1:8000}"
EXPIRES="$(python3 -c 'from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc)+timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"))')"
CNL="$(sed "s/{{EXPIRES_AT}}/${EXPIRES}/" "$(dirname "$0")/mandates/02-bill-payer.cnl")"
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

echo "1. health"; curl -fsS "$API/health"; echo
echo "2. demo customer session (no password: demo only)"
TOKEN="$(curl -fsS -X POST "$API/api/session" -H 'content-type: application/json' -d '{"user_id":"customer_001"}' | json 'd["token"]')"
echo "3. compile KYM-CNL into a canonical mandate (deterministic; nothing is stored)"
PAYLOAD="$(CNL="$CNL" python3 -c 'import json,os; print(json.dumps({"principal_id":"customer_001","cnl":os.environ["CNL"]}))')"
curl -fsS -X POST "$API/api/mandates/compile" -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' -d "$PAYLOAD" \
  | json '"ok=%s  permissions=%s  digest=%s\n%s" % (d["ok"], len(d["mandate"]["permissions"]), d["canonical_digest"][:24], d["normalized_cnl"])'
echo "4. verify the evidence ledger (hash chain, signatures, checkpoints)"
curl -fsS -X POST "$API/api/ledger/verify" -H "authorization: Bearer $TOKEN" | json '"ok=%s events_checked=%s problems=%s" % (d["ok"], d["events_checked"], d["problems"])'
