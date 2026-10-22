#!/usr/bin/env bash
# Nightly Postgres backup: custom-format pg_dump into ~/backups, keeping the newest $KEEP.
# Cron (EC2): 30 16 * * 1-5  ~/Multi-Agent-Trading-Bot/deploy/backup.sh >> ~/backups/backup.log 2>&1   (22:00 IST)
set -euo pipefail
DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP="${KEEP:-7}"
CONTAINER="${PG_CONTAINER:-multi-agent-trading-bot-postgres-1}"
mkdir -p "$DIR"
stamp="$(TZ=Asia/Kolkata date +%Y%m%dT%H%M%SIST)"
out="$DIR/core-$stamp.dump"
docker exec "$CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$out.partial"
mv "$out.partial" "$out"
ls -1t "$DIR"/core-*.dump | tail -n +"$((KEEP + 1))" | xargs -r rm -f
echo "$(date "+%Y-%m-%dT%H:%M:%S%z") backup ok: $out ($(du -h "$out" | cut -f1))"
