# Deployment handoff

- Public application: https://studio.cekwifi.site/
- Dedicated Compose project: `creatorpilot`.
- Application on loopback port 8033, routed by the existing Caddy service behind Cloudflare Tunnel.
- Existing Cekwifi routes retained; its public homepage responded HTTP 200 after route installation.
- Admin username: `harnet`. Initial application password is generated independently from VPS credentials; it is never committed.
- Local operator computer receives `CreatorPilot-Login.txt` on its Desktop. Server copy is `access.txt`, mode 600, ignored by Git.
- Daily local backup timer: `creatorpilot-backup.timer`, approximately 03:30 Asia/Jakarta, seven-day retention. This is not an off-server disaster-recovery backup.
- Production health endpoint returns `status: ok`. Current TypeScript production build completed.
- Isolated integration suite passed: authentication and CSRF/origin checks, resource ownership, idempotent submission, edit locks, job pause/resume, a real FFmpeg MP4/SRT render, protected media access and stored future schedules.

## External setup still required

Google Cloud OAuth web client setup and account-owner consent are required before upload, official caption retrieval or analytics can be used. Configure these in the application's Settings page. Exact callback:

`https://studio.cekwifi.site/api/youtube/callback`

No live Google upload has been claimed or performed without that connection. The deployment does not enable paid AI providers or generative image/video models. Default video production uses composed text/image scenes and basic eSpeak NG narration.
