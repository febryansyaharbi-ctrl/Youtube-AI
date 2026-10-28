#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p backups
# Outputs are immutable; DB references are committed only after media files exist.
docker compose exec -T db pg_dump -U creatorpilot creatorpilot | gzip > "backups/db-$stamp.sql.gz"
docker compose exec -T api tar czf - -C /data media > "backups/media-$stamp.tgz"
cp .env "backups/secrets-$stamp.env"
chmod 600 backups/*
find backups -maxdepth 1 -type f -mtime +7 -delete
printf 'Backup created: %s\n' "$stamp"
