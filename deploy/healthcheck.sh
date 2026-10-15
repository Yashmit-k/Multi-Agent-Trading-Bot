#!/usr/bin/env bash
# Uptime/health alert. Run from cron every 5 minutes during market hours:
#   */5 3-10 * * 1-5  ~/Multi-Agent-Trading-Bot/deploy/healthcheck.sh >> ~/backups/health.log 2>&1
# Alerts (optional) go to ALERT_WEBHOOK_URL as JSON {"text": ...} (Slack/Discord-compatible).
# Only components whose status is "down" alert, plus an unreachable site; "warn" is logged.
set -uo pipefail
URL="${HEALTH_URL:-https://13-238-176-73.sslip.io/api/v1/system/health}"
WEBHOOK="${ALERT_WEBHOOK_URL:-}"
[ -f "$HOME/.trading-bot-alert" ] && . "$HOME/.trading-bot-alert"
body="$(curl -fsS --max-time 20 "$URL")"
if [ $? -ne 0 ] || [ -z "$body" ]; then
  message="StockX: health endpoint unreachable ($URL)"
else
  message="$(printf '%s' "$body" | python3 -c '
import json, sys
data = json.load(sys.stdin)
if data.get("live_enabled"):
    print("StockX: live_enabled is TRUE"); sys.exit()
bad = [c["component"] + ": " + c["detail"] for c in data.get("checks", []) if c.get("status") == "down"]
warn = [c["component"] for c in data.get("checks", []) if c.get("status") == "warn"]
if bad: print("StockX down: " + "; ".join(bad))
elif warn: print("WARN " + ", ".join(warn), file=sys.stderr)
')"
fi
if [ -n "$message" ]; then
  echo "$(date "+%Y-%m-%dT%H:%M:%S%z") $message"
  [ -n "$WEBHOOK" ] && curl -fsS --max-time 10 -H 'Content-Type: application/json' -d "$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1], "content": sys.argv[1]}))' "$message")" "$WEBHOOK" >/dev/null
else
  echo "$(date "+%Y-%m-%dT%H:%M:%S%z") ok"
fi
exit 0
