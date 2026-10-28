# Deployment handoff

- Public application: https://studio.cekwifi.site/
- Dedicated Compose project: `creatorpilot`, at `/home/harnet/creatorpilot`.
- Application listens on loopback port 8033, routed by Caddy behind Cloudflare Tunnel.
- Existing Cekwifi routes retained and its public homepage verified HTTP 200.
- Admin username: `harnet`. The generated app password is separate from VPS credentials and is never committed.
- Login details were delivered to `CreatorPilot-Login.txt` on the operator computer's Desktop. Server copy: `access.txt`, mode 600, ignored by Git.
- Daily local backup timer: `creatorpilot-backup.timer`, approximately 03:30 Asia/Jakarta, seven-day retention. An off-server backup destination is not configured.
- Public API health is OK and the TypeScript production build completed.
- Isolated integration tests passed: authentication, CSRF/origin protection, ownership, idempotency, edit locks, pause/resume, real MP4/SRT rendering, protected media and persisted schedules.

## External setup still required

Google Cloud OAuth web client configuration and account-owner consent are required for YouTube upload, caption retrieval and analytics. Configure them in Settings. Exact callback:

`https://studio.cekwifi.site/api/youtube/callback`

No live Google upload has been performed. Paid AI providers and generative image/video models are not enabled. Production currently composes text/image scenes with basic eSpeak NG narration.

## Final production verification

- AI-to-video sample completed at 100%: 50.423 seconds, H.264 720x1280 with AAC audio, SRT and thumbnail present.
- Qwen3 4B performed real script generation; CPU throughput measured around 1.2 tokens/second on this VPS.
- Qwen3 1.7B was installed, verified with a live JSON generation request, and selected in the database as the faster default. 4B remains available in Settings; only one model loads at a time.
- Worker and scheduler restarted successfully after the sample completed. Public API health remained OK and the Cekwifi homepage still returned HTTP 200.
- YouTube publication/analytics remains unverified pending the owner's Google OAuth configuration and consent.
