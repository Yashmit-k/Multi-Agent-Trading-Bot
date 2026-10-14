#!/usr/bin/env bash
# Smoke-test a deployment through its public URL. Read-only except one POST
# that must be refused by the public proxy.
set -euo pipefail
BASE="${1:?usage: deploy/smoke.sh https://your-domain}"
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "1. frontend health"
curl -fsS "$BASE/api/health" | grep -q '"ok"' || fail "frontend /api/health"

echo "2. system status through the proxy, live trading must be off"
status=$(curl -fsS "$BASE/api/v1/system/status")
echo "$status" | grep -q '"live_enabled":false' || fail "live_enabled is not false: $status"

echo "3. trace endpoint"
curl -fsS "$BASE/api/v1/trace?limit=5" | grep -q '"events"' || fail "trace endpoint"

echo "4. latest agent signals"
curl -fsS "$BASE/api/v1/signals/latest" | grep -q 'agent_name' || echo "   warning: no agent signals stored yet"

echo "5. public proxy refuses paper start"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/v1/paper/start" -H 'Content-Type: application/json' -d '{}')
[ "$code" = "403" ] || fail "POST /api/v1/paper/start returned $code, expected 403"

echo "6. pages render"
for page in dashboard agents trace signals orders positions; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/$page")
  [ "$code" = "200" ] || fail "/$page returned $code"
done
echo "OK: $BASE"
