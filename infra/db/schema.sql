create extension if not exists "uuid-ossp";

create table if not exists users (
  id uuid primary key default uuid_generate_v4(),
  email text unique not null,
  created_at timestamptz not null default now()
);

create table if not exists workspaces (
  id uuid primary key default uuid_generate_v4(),
  name text not null,
  owner_id uuid references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists workspace_members (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id) on delete cascade,
  user_id uuid references users(id) on delete cascade,
  role text not null check (role in ('owner', 'editor', 'viewer')),
  joined_at timestamptz not null default now()
);

create table if not exists search_history (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  query text not null,
  searched_at timestamptz not null default now()
);

create table if not exists saved_searches (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  name text not null,
  query text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists research_papers (
  id uuid primary key default uuid_generate_v4(),
  paperid text not null unique,
  title text not null,
  abstract text,
  authors jsonb not null default '[]'::jsonb,
  url text,
  pdf_url text,
  year int,
  venue text,
  citationcount int not null default 0,
  referencecount int not null default 0,
  isopenaccess boolean not null default false,
  source text not null,
  all_sources jsonb not null default '[]'::jsonb,
  topic text,
  content text,
  inserted_at timestamptz not null default now()
);

create table if not exists projects (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id) on delete cascade,
  name text not null,
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists authors (
  id uuid primary key default uuid_generate_v4(),
  paper_id uuid references research_papers(id) on delete cascade,
  display_name text not null,
  affiliation text,
  orcid text,
  created_at timestamptz not null default now()
);

create table if not exists concepts (
  id uuid primary key default uuid_generate_v4(),
  name text not null unique,
  description text,
  created_at timestamptz not null default now()
);

create table if not exists paper_concepts (
  id uuid primary key default uuid_generate_v4(),
  paper_id uuid references research_papers(id) on delete cascade,
  concept_id uuid references concepts(id) on delete cascade,
  confidence_score numeric(5,2) not null default 0
);

create table if not exists embeddings (
  id uuid primary key default uuid_generate_v4(),
  paper_id uuid references research_papers(id) on delete cascade,
  chunk_id text not null unique,
  chunk_text text not null,
  vector_model text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists summaries (
  id uuid primary key default uuid_generate_v4(),
  paper_id uuid references research_papers(id),
  tier text not null,
  content jsonb not null,
  confidence_score numeric(5,2) not null default 0,
  source_span jsonb not null default '[]'::jsonb,
  model_used text not null,
  generated_at timestamptz not null default now()
);

create table if not exists messages (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id),
  role text not null,
  content text not null,
  citations jsonb not null default '[]'::jsonb,
  confidence_score numeric(5,2) not null default 0,
  source_span jsonb not null default '[]'::jsonb,
  model_used text not null default 'manual',
  generated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists citations (
  id uuid primary key default uuid_generate_v4(),
  source_paper_id uuid references research_papers(id) on delete cascade,
  target_paper_id uuid references research_papers(id) on delete cascade,
  sentiment text not null default 'mention',
  context text,
  confidence_score numeric(5,2) not null default 0,
  source_span jsonb not null default '[]'::jsonb,
  model_used text not null default 'citation-agent',
  generated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists literature_reviews (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id),
  title text not null,
  sections jsonb not null default '[]'::jsonb,
  confidence_score numeric(5,2) not null default 0,
  source_span jsonb not null default '[]'::jsonb,
  model_used text not null,
  generated_at timestamptz not null default now()
);

create table if not exists comparisons (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id),
  focus text not null,
  narrative_summary text,
  confidence_score numeric(5,2) not null default 0,
  source_span jsonb not null default '[]'::jsonb,
  model_used text not null default 'comparison-engine',
  generated_at timestamptz not null default now()
);

create table if not exists comparison_pdf_files (
  id uuid primary key,
  comparison_id uuid not null,
  owner_user_id text not null,
  original_name text not null,
  sha256 char(64) not null,
  size_bytes bigint not null,
  page_count integer not null,
  extracted_text text not null,
  extraction_method text not null,
  pdf_bytes bytea not null,
  created_at timestamptz not null default now(),
  unique (comparison_id, owner_user_id, sha256)
);

create index if not exists comparison_pdf_owner_idx
  on comparison_pdf_files(owner_user_id, comparison_id, created_at);

create table if not exists comparison_rows (
  id uuid primary key default uuid_generate_v4(),
  comparison_id uuid references comparisons(id) on delete cascade,
  paper_id uuid references research_papers(id),
  strengths jsonb not null default '[]'::jsonb,
  weaknesses jsonb not null default '[]'::jsonb,
  extracted_columns jsonb not null default '{}'::jsonb,
  similarity_score numeric(6,3) not null default 0,
  confidence_score numeric(5,2) not null default 0,
  source_span jsonb not null default '[]'::jsonb,
  model_used text not null default 'comparison-engine',
  generated_at timestamptz not null default now()
);

create table if not exists gap_reports (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id),
  title text not null,
  findings jsonb not null default '[]'::jsonb,
  confidence_score numeric(5,2) not null default 0,
  source_span jsonb not null default '[]'::jsonb,
  model_used text not null default 'gap-agent',
  generated_at timestamptz not null default now()
);

create table if not exists annotations (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id),
  paper_id uuid references research_papers(id),
  quote text not null,
  note text,
  highlight_span jsonb not null default '[]'::jsonb,
  color text default 'yellow',
  created_at timestamptz not null default now()
);

create table if not exists notes (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  paper_id uuid references research_papers(id) on delete set null,
  title text not null,
  content text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists private_notes (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  title text not null,
  encrypted_content text not null,
  encryption_hint text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists folders (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists tags (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists folder_items (
  id uuid primary key default uuid_generate_v4(),
  folder_id uuid references folders(id) on delete cascade,
  resource_type text not null,
  resource_id text not null,
  created_at timestamptz not null default now()
);

create table if not exists tag_assignments (
  id uuid primary key default uuid_generate_v4(),
  tag_id uuid references tags(id) on delete cascade,
  resource_type text not null,
  resource_id text not null,
  created_at timestamptz not null default now()
);

create table if not exists notifications (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  title text not null,
  body text not null,
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists refresh_tokens (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  token_hash text not null,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists abuse_events (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id) on delete set null,
  user_id uuid references users(id) on delete set null,
  event_type text not null,
  severity text not null default 'medium',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists backup_runs (
  id uuid primary key default uuid_generate_v4(),
  scope text not null,
  status text not null,
  storage_uri text not null,
  verified_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists push_subscriptions (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  endpoint text not null,
  public_key text,
  auth_secret text,
  created_at timestamptz not null default now()
);

create table if not exists offline_actions (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  action_type text not null,
  payload jsonb not null default '{}'::jsonb,
  synced_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists plagiarism_check_results (
  id uuid primary key default uuid_generate_v4(),
  literature_review_id uuid references literature_reviews(id) on delete cascade,
  score numeric(5,2) not null default 0,
  flagged_spans jsonb not null default '[]'::jsonb,
  confidence_score numeric(5,2) not null default 0,
  source_span jsonb not null default '[]'::jsonb,
  model_used text not null default 'plagiarism-checker',
  generated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists evaluation_runs (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id) on delete cascade,
  first_result_latency_ms numeric(10,2),
  full_search_latency_ms numeric(10,2),
  dedup_reduction numeric(6,3),
  summary_quality_mean numeric(5,2),
  rag_accuracy numeric(6,3),
  bridge_accuracy numeric(6,3),
  draft_success_rate numeric(6,3),
  concurrent_users_supported int,
  overall_passed boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists export_jobs (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id),
  export_type text not null,
  status text not null default 'pending',
  payload jsonb not null default '{}'::jsonb,
  output_uri text,
  created_at timestamptz not null default now()
);

create table if not exists audit_logs (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id),
  actor_user_id uuid references users(id),
  action text not null,
  target_type text not null,
  target_id text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists collaborators (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id) on delete cascade,
  user_id uuid references users(id) on delete cascade,
  invited_email text,
  role text not null check (role in ('owner', 'editor', 'viewer')),
  status text not null default 'active' check (status in ('pending', 'active', 'revoked')),
  invited_at timestamptz not null default now(),
  accepted_at timestamptz
);

create table if not exists share_links (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id) on delete cascade,
  resource_type text not null,
  resource_id text not null,
  permission text not null default 'view',
  token text not null unique,
  expires_at timestamptz,
  created_by uuid references users(id) on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists api_keys (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  name text not null,
  key_prefix text not null,
  key_hash text not null,
  scopes jsonb not null default '[]'::jsonb,
  last_used_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists webhook_subscriptions (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id) on delete cascade,
  target_url text not null,
  event_types jsonb not null default '[]'::jsonb,
  secret_hash text,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists prompt_templates (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid references users(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  name text not null,
  body text not null,
  tags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists import_jobs (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id) on delete cascade,
  format text not null,
  item_count int not null default 0,
  status text not null default 'pending',
  created_at timestamptz not null default now()
);

create table if not exists plugin_registrations (
  id uuid primary key default uuid_generate_v4(),
  name text not null unique,
  plugin_type text not null,
  capabilities jsonb not null default '[]'::jsonb,
  status text not null default 'active',
  created_at timestamptz not null default now()
);

create table if not exists review_subscriptions (
  id uuid primary key default uuid_generate_v4(),
  workspace_id uuid references workspaces(id) on delete cascade,
  query text not null,
  last_digest_at timestamptz,
  active boolean not null default true,
  created_at timestamptz not null default now()
);
