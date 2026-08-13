-- Solar ESP32 Smart Fertigation — Supabase schema
-- Run this in the Supabase SQL Editor (Dashboard → SQL → New query).

create extension if not exists pgcrypto;

create table if not exists public.captures (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  device text not null default 'esp32-cam',
  filename text not null unique,
  storage_path text not null,
  bytes integer,
  image_url text,
  is_healthy boolean,
  should_dose boolean,
  severity_pct integer,
  dose_ms integer,
  top_issue text,
  nutrient_deficient text,
  pumped boolean,
  decision jsonb,
  plant_id_access_token text
);

create index if not exists captures_created_at_idx
  on public.captures (created_at desc);

alter table public.captures enable row level security;

drop policy if exists "Public read captures" on public.captures;
create policy "Public read captures"
  on public.captures
  for select
  to anon, authenticated
  using (true);

insert into storage.buckets (id, name, public)
values ('plant-photos', 'plant-photos', true)
on conflict (id) do update set public = true;

insert into storage.buckets (id, name, public)
values ('cam-uploads', 'cam-uploads', true)
on conflict (id) do update set public = true;

-- Storage uploads run INSERT … RETURNING *, so SELECT is required
-- or the insert is rolled back with 403 RLS. Scope SELECT to these
-- two buckets only — do not allow listing every bucket.
drop policy if exists "Service role write cam uploads" on storage.objects;
drop policy if exists "Service role update cam uploads" on storage.objects;
drop policy if exists "Upload plant photos" on storage.objects;
drop policy if exists "Update plant photos" on storage.objects;
drop policy if exists "allow select plant and cam" on storage.objects;

create policy "Upload plant photos"
  on storage.objects
  for insert
  to anon, authenticated, service_role
  with check (bucket_id in ('plant-photos', 'cam-uploads'));

create policy "Update plant photos"
  on storage.objects
  for update
  to anon, authenticated, service_role
  using (bucket_id in ('plant-photos', 'cam-uploads'))
  with check (bucket_id in ('plant-photos', 'cam-uploads'));

create policy "allow select plant and cam"
  on storage.objects
  for select
  to anon, authenticated, service_role, public
  using (bucket_id in ('plant-photos', 'cam-uploads'));
