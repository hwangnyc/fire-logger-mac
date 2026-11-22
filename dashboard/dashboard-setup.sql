-- Fire Logger -> Dashboard setup
-- Run ONCE in the DASHBOARD Supabase project (sddzkerxgkdnafequvmv),
-- SQL Editor. Creates everything new; touches no existing tables.
-- *** DO NOT RUN until Henry says go — this is a live-system change. ***

-- 1. Storage bucket for the audio clips (public so the dashboard can play them)
insert into storage.buckets (id, name, public)
values ('dispatch-audio', 'dispatch-audio', true)
on conflict (id) do nothing;

-- Anyone can READ/play files in the bucket (the dashboard uses the anon key)
drop policy if exists "dispatch audio public read" on storage.objects;
create policy "dispatch audio public read"
  on storage.objects for select
  using (bucket_id = 'dispatch-audio');

-- NOTE: no anon INSERT policy on purpose. Uploads come only from Henry's
-- Mac using a key stored on that Mac, never from the public web page.

-- 2. Clip index table
create table if not exists public.radio_clips (
  id bigint generated always as identity primary key,
  started_at timestamptz not null,          -- when the recording started (Mac clock, ET)
  storage_path text not null,               -- file name inside the bucket
  public_url text not null,                 -- playable URL for the dashboard
  incident_number text,                     -- filled in later if we add hard matching;
                                            -- v1 matches by time in the dashboard itself
  transcript_raw text,                      -- Whisper's transcript, exactly as heard
  transcript_clean text,                    -- local-model cleanup, CAD-anchored; set ONLY
                                            -- when the digit check passed (every number
                                            -- traces to the raw transcript or the CAD
                                            -- record). The raw is always kept alongside.
  created_at timestamptz not null default now()
);

alter table public.radio_clips enable row level security;

-- Dashboard (anon) can read the clip list
drop policy if exists "radio clips anon read" on public.radio_clips;
create policy "radio clips anon read"
  on public.radio_clips for select
  to anon
  using (true);

-- No anon insert/update/delete policies: only the Mac's key can write.

-- 3. (Optional, later) let the dashboard update live when a clip lands:
-- alter publication supabase_realtime add table public.radio_clips;
-- Left out of v1 — the dashboard's normal refresh picks clips up within a minute.
