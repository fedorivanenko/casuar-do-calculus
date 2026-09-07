-- Apply once with psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f schema.sql
begin;
create schema casuar_do;
revoke all on schema casuar_do from public;
create table casuar_do.models (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  version integer not null check (version > 0),
  definition jsonb not null check (jsonb_typeof(definition) = 'object'),
  created_at timestamptz not null default now(),
  unique (name, version)
);
create table casuar_do.observations (
  id uuid primary key default gen_random_uuid(),
  person_id text not null,
  variable text not null,
  value double precision not null,
  unit text not null,
  observed_at timestamptz not null,
  uncertainty_sd double precision check (uncertainty_sd >= 0),
  source jsonb not null default '{}'::jsonb
);
create index on casuar_do.observations (person_id, variable, observed_at desc);
create table casuar_do.runs (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references casuar_do.models(id),
  person_id text,
  model_snapshot jsonb not null,
  result jsonb not null,
  created_at timestamptz not null default now()
);
create index on casuar_do.runs (model_id);
alter table casuar_do.models enable row level security;
alter table casuar_do.observations enable row level security;
alter table casuar_do.runs enable row level security;
-- Private backend-only schema; no public API grants or permissive policies.
commit;
