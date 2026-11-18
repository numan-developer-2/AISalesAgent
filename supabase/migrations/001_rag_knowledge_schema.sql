create extension if not exists vector
with schema extensions;

create table if not exists public.knowledge_chunks (
    id bigint generated always as identity primary key,
    chunk_id text not null unique,
    content text not null,
    title text,
    source_url text,
    content_type text,
    content_hash text unique,
    metadata jsonb not null default '{}'::jsonb,
    embedding extensions.vector(768),
    created_at timestamp with time zone not null default now(),
    updated_at timestamp with time zone not null default now()
);

comment on table public.knowledge_chunks is
    'RAG knowledge chunks for Gemini gemini-embedding-2 embeddings with output dimensionality 768.';

comment on column public.knowledge_chunks.embedding is
    'Embedding vector from Gemini gemini-embedding-2, output dimensionality 768. Nullable until ingestion completes.';

create index if not exists knowledge_chunks_content_type_idx
    on public.knowledge_chunks (content_type);

create index if not exists knowledge_chunks_source_url_idx
    on public.knowledge_chunks (source_url);

create index if not exists knowledge_chunks_embedding_hnsw_idx
    on public.knowledge_chunks
    using hnsw (embedding extensions.vector_cosine_ops);

create or replace function public.set_knowledge_chunks_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists set_knowledge_chunks_updated_at on public.knowledge_chunks;

create trigger set_knowledge_chunks_updated_at
before update on public.knowledge_chunks
for each row
execute function public.set_knowledge_chunks_updated_at();

alter table public.knowledge_chunks enable row level security;

create or replace function public.match_knowledge_chunks(
    query_embedding extensions.vector(768),
    match_threshold double precision,
    match_count integer,
    filter_content_type text default null
)
returns table (
    id bigint,
    chunk_id text,
    content text,
    title text,
    source_url text,
    content_type text,
    metadata jsonb,
    similarity double precision
)
language sql
stable
as $$
    select
        kc.id,
        kc.chunk_id,
        kc.content,
        kc.title,
        kc.source_url,
        kc.content_type,
        kc.metadata,
        1 - (kc.embedding <=> query_embedding) as similarity
    from public.knowledge_chunks as kc
    where
        kc.embedding is not null
        and (filter_content_type is null or kc.content_type = filter_content_type)
        and (1 - (kc.embedding <=> query_embedding)) >= match_threshold
    order by kc.embedding <=> query_embedding
    limit least(greatest(coalesce(match_count, 10), 1), 50);
$$;

comment on function public.match_knowledge_chunks(
    extensions.vector(768),
    double precision,
    integer,
    text
) is
    'Cosine similarity retrieval over knowledge_chunks embeddings generated with Gemini gemini-embedding-2 at output dimensionality 768. RLS access strategy is finalized when the backend Supabase client is implemented.';
