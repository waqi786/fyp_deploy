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
