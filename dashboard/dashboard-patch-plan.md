# Dashboard patch plan — "▶ Listen to the call"
### Prepared, NOT applied. Live dashboard changes only on Henry's go.

Repo: `hwangnyc/albertson-fire-dashboard`, file: `index.html`
Supabase project: `sddzkerxgkdnafequvmv` (the dashboard's own project —
not the old Pi logger's project)

## Prerequisite
Run `dashboard-setup.sql` in that project's SQL Editor (creates the
`dispatch-audio` bucket + `radio_clips` table, read-only for anon).

## Change 1 — fetch clips with the calls
In the same refresh that loads incidents
(`api("/incidents?select=*&order=created_at.desc&limit=25")`), also load:
```js
api("/radio_clips?select=*&order=started_at.desc&limit=50")
```
Store in a `clips` array next to `incidents`. If the table doesn't
exist yet, the fetch fails silently and the dashboard behaves exactly
as today (same graceful-degradation pattern as pi_heartbeats).

## Change 2 — time-match (no manual linking)
A clip belongs to a call when its start time is:
- no more than 60 seconds **before** the call's `dispatched_at`, and
- no more than 4 minutes **after** it.

Radio dispatch and the CAD timestamp are the same event, so this
window is generous but safe: Albertson rarely has two calls inside
4 minutes, and if it does, the closer dispatch wins (assign each clip
to the nearest dispatched_at).

## Change 3 — the player, in the call detail pane
In `renderInfo()`, after the incident-number line, for each matched
clip add:
```html
<div class="info-audio">
  <div>🎧 Dispatch audio — 8:41:07 PM</div>
  <audio controls preload="none" src="<public_url>"></audio>
</div>
```
Native `<audio controls>` = click to play, pause, scrub. No autoplay
(the TV shouldn't blare audio on its own; a person clicks).

## Change 4 — split-screen hint (optional, same patch)
On split-screen active-call cards, add a small `🎧` next to the call
type when a clip has matched, so people know audio exists before
they tap the call.

## What does NOT change
- CAD ingest, incidents table, heartbeat, passphrase gate: untouched.
- No keys added to the page — it already reads with the anon key,
  and the bucket/table are anon-read by the SQL above.
- Uploads never go through the web page; only Henry's Mac writes.

## Rollback
Revert the one `index.html` commit. The bucket/table can stay
(unused) or be dropped with two SQL lines.
