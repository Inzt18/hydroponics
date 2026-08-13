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

drop policy if exists "Public read plant photos" on storage.objects;
create policy "Public read plant photos"
  on storage.objects
  for select
  to public
  using (bucket_id in ('plant-photos', 'cam-uploads'));

drop policy if exists "Service role write cam uploads" on storage.objects;
create policy "Service role write cam uploads"
  on storage.objects
  for insert
  to service_role
  with check (bucket_id in ('plant-photos', 'cam-uploads'));

drop policy if exists "Service role update cam uploads" on storage.objects;
create policy "Service role update cam uploads"
  on storage.objects
  for update
  to service_role
  using (bucket_id in ('plant-photos', 'cam-uploads'));
