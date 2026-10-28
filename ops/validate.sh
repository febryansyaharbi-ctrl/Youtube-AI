#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T db psql -U creatorpilot -tAc "SELECT 1 FROM pg_database WHERE datname='creatorpilot_test'" | grep -q 1 || docker compose exec -T db createdb -U creatorpilot creatorpilot_test
docker compose exec -T api python -c 'import os; os.environ["DATABASE_URL"]=os.environ["DATABASE_URL"].rsplit("/",1)[0]+"/creatorpilot_test"; os.environ["REDIS_URL"]="redis://redis:6379/15"; import pytest; raise SystemExit(pytest.main(["tests","-q"]))'
