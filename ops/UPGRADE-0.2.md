# CreatorPilot 0.2 — guided channel and clipping upgrade

This is an additive upgrade of the existing VPS application. It reuses authentication, PostgreSQL, Redis, Celery, scheduler, file storage and official YouTube OAuth. No destructive schema migration or paid provider is added.

## Workflows

1. Open **Mentor & perjalanan**, select one of 16 channel niches and a specific audience, then save the profile. Ten concrete steps cover channel creation, branding, settings, research, planning, production, review, publishing and improvement. Checkmarks are user-reported progress, not automatic verification of Google settings.
2. The stored profile supplies new projects, AI scripts, mentor strategy, highlight analysis and visual prompts. Existing calendar versions keep a snapshot of their original profile. Changing the profile does not rewrite existing videos.
3. **Kalender 90 hari** creates 30 persisted entries on days 3, 6, ..., 90, alternating AI/Clip/Prompt. Day 1 is the selected start date. Each entry contains time in Asia/Jakarta, title, hook, concept, description, CTA and hashtags. This is a deterministic niche-based editorial matrix, not live keyword/virality research. Entries are editable; project creation is idempotent. Regeneration archives the old matrix. It does not schedule public uploads automatically.
4. **Prompt visual** builds and stores copyable prompts for Runway, Pika, Sora, Midjourney and Leonardo AI from subject, lighting, camera, style and ratio plus the saved niche/audience. This makes no provider API call and does not claim those services are free.
5. **Content Clipper** accepts a YouTube URL, validates its host and ID, embeds the source and retrieves license metadata via the owner's configured official OAuth when available. It cannot inspect all Content ID claims or certify fair use. Alternatives are clearly marked search/review suggestions, not certified safe videos.
6. Upload an original/authorized source MP4 in Media, transcribe it, then request niche-aware highlight suggestions or enter ranges manually. Rendering accepts 1–10 clips, 1–180 seconds each, with ownership, matching-transcript, duration and duplicate checks. All heavy work uses the persistent queue and checkpoints.
7. Preview raw source/ranges and rendered clips. Styled subtitles are burned into MP4 and downloadable as SRT. Styles include Clean, Bold Hook, Karaoke and Neon; fonts are actually installed open fonts. Per-word timing is estimated from transcript segments, not precise forced alignment. The same styles work for AI slide videos.
8. Media has no expiry or automatic cleanup. Explicit **Hapus Video** removes an output from active storage; other clips remain. Existing backup snapshots may retain older copies according to the backup policy. No off-server disaster-recovery copy is configured.

## Honest boundaries

- YouTube links are for source review/metadata/embedded playback; the application does not download YouTube audiovisual content. Clip rendering uses an uploaded original/authorized file. Official policy: https://developers.google.com/youtube/terms/developer-policies
- Creative Commons metadata and a user's rights declaration are not a no-claim guarantee. Official guidance: https://support.google.com/youtube/answer/2797466 and https://support.google.com/youtube/answer/2797468
- Channel creation and Google consent require the owner's own interaction with Google. Guides: https://support.google.com/youtube/answer/1646861 and https://support.google.com/youtube/answer/3027950
- Local AI video remains FFmpeg scenes plus basic eSpeak narration. No cinematic text-to-video model or cloud billing has been activated.
- No actual YouTube account upload/analytics end-to-end test is possible until OAuth is configured and consented.

## Validation and rollout

Use the isolated `creatorpilot_test` database and Redis DB 15. New integration coverage checks profile/calendar persistence, all 30 slots, calendar project idempotency, URL restrictions, prompt context, subtitle presets, matching source transcription, rights/range validation, real two-clip FFmpeg renders, protected downloads and explicit deletion; the original workflow/security suite is retained. Production media and database are never used as test fixtures.

Keep the previous Docker images tagged `creatorpilot-backend:before-0.2` and `creatorpilot-web:before-0.2`. Run the existing backup before rollout. Deploy only API/worker/scheduler/web; leave PostgreSQL, Redis, Ollama, Caddy, cloudflared and Cekwifi intact. If health fails, restore the prior image tags and recreate those four services. Additive Setting rows do not prevent old-code rollback.
