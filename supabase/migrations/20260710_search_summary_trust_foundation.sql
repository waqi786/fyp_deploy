create table if not exists public.resora_search_workspace_snapshots (
    id text primary key,
    saved_searches jsonb not null default '[]'::jsonb,
    history jsonb not null default '[]'::jsonb,
    trending_papers jsonb not null default '[]'::jsonb,
    trending_topics jsonb not null default '[]'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.saved_searches (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    name text not null,
    query text not null,
    sources jsonb not null default '[]'::jsonb,
    filters jsonb not null default '{}'::jsonb,
    alert_enabled boolean not null default true,
    alert_cadence text not null default 'daily',
    last_triggered_at timestamptz,
    new_match_count integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.search_history (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    session_id text not null,
    query text not null,
    normalized_query text not null,
    sources jsonb not null default '[]'::jsonb,
    result_count integer not null default 0,
    resumable_url text not null,
    searched_at timestamptz not null default now()
);

create table if not exists public.paper_summaries (
    id uuid primary key default gen_random_uuid(),
    paper_id text not null,
    user_id uuid references auth.users(id) on delete set null,
    tier text not null,
    summary jsonb not null,
    confidence_score numeric(5, 4) not null default 0,
    source_span jsonb not null default '[]'::jsonb,
    model_used text not null,
    generated_at timestamptz not null default now()
);

create table if not exists public.paper_trust_reports (
    id uuid primary key default gen_random_uuid(),
    paper_id text not null,
    user_id uuid references auth.users(id) on delete set null,
    trust_score numeric(4, 2) not null,
    novelty_score numeric(4, 2) not null,
    red_flags jsonb not null default '[]'::jsonb,
    evidence_meter jsonb not null default '{}'::jsonb,
    methodology_checklist jsonb not null default '[]'::jsonb,
    source_span jsonb not null default '[]'::jsonb,
    model_used text not null default 'resora-trust-heuristic',
    generated_at timestamptz not null default now()
);

alter table public.saved_searches enable row level security;
alter table public.search_history enable row level security;
alter table public.paper_summaries enable row level security;
alter table public.paper_trust_reports enable row level security;

drop policy if exists "saved_searches_owner_all" on public.saved_searches;
create policy "saved_searches_owner_all"
on public.saved_searches
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "search_history_owner_all" on public.search_history;
create policy "search_history_owner_all"
on public.search_history
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "paper_summaries_owner_or_public_read" on public.paper_summaries;
create policy "paper_summaries_owner_or_public_read"
on public.paper_summaries
for select
using (user_id is null or auth.uid() = user_id);

drop policy if exists "paper_summaries_owner_write" on public.paper_summaries;
create policy "paper_summaries_owner_write"
on public.paper_summaries
for insert
with check (user_id is null or auth.uid() = user_id);

drop policy if exists "paper_trust_reports_owner_or_public_read" on public.paper_trust_reports;
create policy "paper_trust_reports_owner_or_public_read"
on public.paper_trust_reports
for select
using (user_id is null or auth.uid() = user_id);

drop policy if exists "paper_trust_reports_owner_write" on public.paper_trust_reports;
create policy "paper_trust_reports_owner_write"
on public.paper_trust_reports
for insert
with check (user_id is null or auth.uid() = user_id);

create index if not exists saved_searches_user_updated_idx on public.saved_searches (user_id, updated_at desc);
create index if not exists search_history_user_time_idx on public.search_history (user_id, searched_at desc);
create index if not exists paper_summaries_paper_tier_idx on public.paper_summaries (paper_id, tier);
create index if not exists paper_trust_reports_paper_time_idx on public.paper_trust_reports (paper_id, generated_at desc);
