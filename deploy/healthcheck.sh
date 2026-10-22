#!/usr/bin/env bash
# Uptime/health alert, run from cron every 5 minutes in market hours (EC2 clock is UTC):
#   */5 3-10 * * 1-5  ~/Multi-Agent-Trading-Bot/deploy/healthcheck.sh >> ~/backups/health.log 2>&1
# Alerts on any "down" component, an unreachable site, or live_enabled=true. Sends to Telegram
# (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) and/or ALERT_WEBHOOK_URL, read from the repo's .env.
# The same problem is re-sent at most every 30 minutes, and a "recovered" message follows once it clears.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
read_env() { grep -E "^$1=" "$REPO/.env" 2>/dev/null | tail -1 | cut -d= -f2- ; }
URL="${HEALTH_URL:-https://$(read_env DOMAIN)/api/v1/system/health}"
STATE="${HEALTH_STATE:-$HOME/backups/health.state}"
TG_TOKEN="${TELEGRAM_BOT_TOKEN:-$(read_env TELEGRAM_BOT_TOKEN)}"
TG_CHAT="${TELEGRAM_CHAT_ID:-$(read_env TELEGRAM_CHAT_ID)}"
WEBHOOK="${ALERT_WEBHOOK_URL:-$(read_env ALERT_WEBHOOK_URL)}"
stamp() { date "+%Y-%m-%dT%H:%M:%S%z"; }

send() {
  local text="$1"
  if [ -n "$TG_TOKEN" ] && [ -n "$TG_CHAT" ]; then
    curl -fsS --max-time 10 -H 'Content-Type: application/json' \
      -d "$(python3 -c 'import json,sys; print(json.dumps({"chat_id": sys.argv[1], "text": sys.argv[2]}))' "$TG_CHAT" "$text")" \
      "https://api.telegram.org/bot$TG_TOKEN/sendMessage" >/dev/null || echo "$(stamp) telegram send failed"
  fi
  if [ -n "$WEBHOOK" ]; then
    curl -fsS --max-time 10 -H 'Content-Type: application/json' \
      -d "$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1], "content": sys.argv[1]}))' "$text")" "$WEBHOOK" >/dev/null || echo "$(stamp) webhook send failed"
  fi
}

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
if bad:
    print("StockX down: " + "; ".join(bad))
')"
fi

# Disk: alert at DISK_ALERT_PCT (default 85%) used on the root filesystem.
DISK_ALERT_PCT="${DISK_ALERT_PCT:-85}"
disk_used=$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')
if [ -n "$disk_used" ] && [ "$disk_used" -ge "$DISK_ALERT_PCT" ]; then
  message="${message:+$message; }StockX: server disk ${disk_used}% full (alert at ${DISK_ALERT_PCT}%)"
fi

now=$(date +%s)
last_message=""; last_sent=0
[ -f "$STATE" ] && { last_message="$(sed -n 1p "$STATE")"; last_sent="$(sed -n 2p "$STATE")"; }
if [ -n "$message" ]; then
  echo "$(stamp) $message"
  if [ "$message" != "$last_message" ] || [ $((now - ${last_sent:-0})) -ge 1800 ]; then
    send "$message"
    printf '%s\n%s\n' "$message" "$now" > "$STATE"
  fi
else
  echo "$(stamp) ok"
  if [ -n "$last_message" ]; then
    send "StockX recovered: all components healthy again."
    rm -f "$STATE"
  fi
fi
exit 0
