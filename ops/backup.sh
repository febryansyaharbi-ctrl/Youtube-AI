#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p backups
# Pause scheduler + finish/stop active jobs from UI before maintenance backup for consistency.
docker compose exec -T db pg_dump -U creatorpilot creatorpilot | gzip > "backups/db-$stamp.sql.gz"
docker compose exec -T api tar czf - -C /data media > "backups/media-$stamp.tgz"
chmod 600 backups/*
printf 'Backup created: %s\n' "$stamp"
