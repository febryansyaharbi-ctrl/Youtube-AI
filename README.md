# CreatorPilot AI

Self-hosted Indonesian creator studio. React/TypeScript frontend, FastAPI, PostgreSQL, Redis/Celery, persistent database scheduler, Ollama and FFmpeg. Deploys separately from other VPS services.

## Implemented

- Private single-owner login, Argon2 password hashing, server-side sessions, CSRF checks, origin checks and rate limits.
- Editable app name; Indonesian UI; Indonesian and English script/video production.
- Projects, manual scripts, local AI script/strategy generation, original text/slide video production with optional owned image backgrounds, eSpeak NG narration, MP4, thumbnail and SRT output.
- Asset storage with source/license notes, upload size limits and media validation; faster-whisper tiny transcription and AI highlight extraction.
- PostgreSQL job records and schedules, Celery worker, stage/scene checkpoints, pause/cancel/retry, idempotency keys, job locks and heartbeat recovery.
- Resource estimates before work, one production worker, memory/CPU caps, health checks, rotating logs and audit events.
- Encrypted Google OAuth credentials/tokens, official YouTube captions access for videos the user can edit, channel statistics and 28-day analytics.
- Resumable upload sessions saved encrypted in PostgreSQL; ambiguous sessions do not silently create a replacement upload. Each reviewed project revision can have one upload record. Upload privacy and scheduling require explicit action in the app.
- Gamified manual learning milestones. XP is a learning checklist, not evidence of monetization eligibility.

## Deliberate limits

This is the first working release, not a guarantee of channel growth or monetization. Local text-model output needs fact checking. The default voice is basic synthetic eSpeak NG; no cloned voice or premium TTS is implied. Videos are composed text/slide videos, not generative cinematic video. Image/video generation adapters and cloud-paid providers are not enabled. One image can be used as a video background.

Google OAuth must be configured and consented by the account owner before YouTube operations can run. Google Cloud quotas and verification requirements apply. The UI displays an application-level daily upload budget, not an invented Google remaining quota. YouTube Studio's Earn tab is authoritative for monetization eligibility; API watch-time metrics are not substituted for eligible public watch hours. Automatic mode produces a draft video; publication requires a reviewed output and explicit upload/schedule request.

Pause/cancel is cooperative: render subprocesses stop quickly; model jobs stop at a streamed token boundary; network uploads stop between chunks. Already accepted YouTube uploads cannot be undone by cancelling a local job. An interrupted render keeps completed scene clips. An interrupted model request restarts that stage.

## Deploy

```sh
python3 ops/init-env.py
sudo docker compose build
sudo docker compose up -d
sudo docker compose exec ollama ollama pull qwen3:4b
```

Use Docker Compose v2. `.env` and `access.txt` are created mode 600 and never committed. Proxy HTTPS traffic to `127.0.0.1:8033`. PostgreSQL, Redis and Ollama have no host-published ports. The web app is single-owner; registration is intentionally disabled.

For initial deployment, use the app credentials in `access.txt`, then change the password in Settings. The database is authoritative after first boot; changing ADMIN_PASSWORD in `.env` does not change an existing account.

## YouTube configuration

1. Create a Google Cloud project, enable YouTube Data API v3 and YouTube Analytics API.
2. Configure OAuth consent, test users if applicable, and a Web Application OAuth client.
3. Set the exact authorized redirect URI shown in Settings.
4. Enter Client ID and Secret into the authenticated settings form (stored encrypted).
5. Connect Google and grant access. Synchronize analytics, then test a private video upload.

No Google password is requested. OAuth access/refresh tokens and upload URLs are never returned in job responses or public logs. Rotating ENCRYPTION_KEY without re-encrypting stored secrets breaks existing connections; back it up securely.

## Maintenance

```sh
sudo docker compose ps
sudo docker compose logs --tail=100 worker scheduler
sudo docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/health').read().decode())"
sudo bash ops/backup.sh
```

Backup includes PostgreSQL and media; an encrypted-token recovery key is included as a mode-600 local secrets snapshot. Retention is 7 days. Keep an additional off-server copy in secure storage. No remote backup destination is configured by default. Restore with the application stopped to avoid concurrent writes.

Schema is version 1 (`ops/schema-version.txt`); initial installation uses SQLAlchemy metadata creation. Future schema changes must add an explicit migration before upgrade; create_all does not migrate existing tables. Do not use destructive resets on production.

## Validation

Tests require a separate PostgreSQL database ending `_test` and Redis DB 15. They verify authentication, CSRF/origin rejection, ownership, idempotent submissions, edit locking, pause/resume, a real FFmpeg render, SRT output, media access and persistent schedules. Production data is never reset by the test script.

References: [Ollama Qwen3](https://ollama.com/library/qwen3:4b), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [YouTube upload](https://developers.google.com/youtube/v3/docs/videos/insert), [caption permissions](https://developers.google.com/youtube/v3/docs/captions/download), [YPP eligibility](https://support.google.com/youtube/answer/72851).
