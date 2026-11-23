# Dashboard audio — as built
### Status: LIVE. Applied Nov 22, 2026 (originally a plan; this file now records what shipped.)

Repo: `hwangnyc/albertson-fire-dashboard`, file: `index.html`
Supabase project: `sddzkerxgkdnafequvmv` (the dashboard's own project —
not the old Pi logger's project)

## Prerequisite — done
`dashboard-setup.sql` was run in that project's SQL Editor on
Nov 22, 2026: public `dispatch-audio` bucket + `radio_clips` table,
anon read-only. Uploads come only from the Mac, using a secret key
stored only on that Mac — there is deliberately no anon insert policy.

## What shipped

1. **Fetch clips with the calls.** The refresh that loads incidents
   also loads `radio_clips?select=*&order=started_at.desc&limit=50`.
   If the table is missing, the fetch fails silently and the dashboard
   behaves exactly as before (same pattern as pi_heartbeats).

2. **Time-match (no manual linking).** A clip belongs to the call
   whose dispatch time is nearest, when the clip starts within
   −60 s/+4 min of `dispatched_at`. Clips matching nothing are
   simply not shown.

3. **The player — an inline pill in the call detail.** One pill per
   matched clip, labeled by airing ("Airing 1 · 8:48 PM"), holding:
   a round play/pause button, a stop button beside it (pause +
   rewind), a click-to-seek progress bar, and a `0:00 / 0:21` time
   readout. Only one clip plays at a time — starting one pauses the
   other. No autoplay: a person presses play.
   (This is the third iteration, all on Nov 22, 2026: native
   `<audio controls>` blocks → a popup player with synced transcript
   highlighting → this pill, which is the design that stayed.)

4. **Split-screen hint.** Split-screen call cards show a 🎧 when a
   clip has matched the call.

5. **Transcripts — stored, deliberately not displayed.**
   `radio_clips` carries `transcript_raw` / `transcript_clean`, and
   backfilled rows hold their raw text, but the UI shows none of it:
   raw Whisper output on dispatch audio isn't good enough yet.
   Display returns when the CAD-anchored cleanup stage proves out.
   The audio is the record.

Commits on the dashboard repo: `9c52c99` (first player),
`3b753b7` (popup, superseded), `e413ba6` (the pill + detail-pane
spacing fixes — current).

## Verified
- Nov 22, 2026, 12:08 PM ET test transmission: recorder log
  `☁️ Uploaded: …/dispatch-audio/2026-11-22_12-08-14.mp3`, the
  `radio_clips` row landed with the exact timestamp, and the public
  MP3 URL returned `200 audio/mpeg`.
- Real call #499 (Nov 21, 2026) backfilled the same evening: both
  airings at +12 s/+39 s from dispatch — inside the match window —
  and the live page renders both pills with correct durations.

## What did NOT change
- CAD ingest, incidents table, heartbeat, passphrase gate: untouched.
- No keys added to the page — it reads with the anon key, and the
  bucket/table are anon-read by the SQL above.

## Rollback
Revert the `index.html` commits. The bucket/table can stay (unused)
or be dropped with two SQL lines.
