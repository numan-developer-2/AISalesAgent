create extension if not exists pgcrypto
with schema extensions;

create or replace function public.set_sales_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create table if not exists public.sales_leads (
    id uuid primary key default gen_random_uuid(),
    lead_reference text unique not null,
    full_name text,
    company_name text,
    email text,
    phone text,
    website_url text,
    industry text,
    required_services jsonb not null default '[]'::jsonb,
    business_goal text,
    budget_range text,
    timeline text,
    authority_status text,
    lead_score integer not null default 0,
    lead_classification text not null default 'Cold',
    score_reasons jsonb not null default '[]'::jsonb,
    meeting_requested boolean not null default false,
    proposal_requested boolean not null default false,
    human_handover_requested boolean not null default false,
    assigned_sales_rep text,
    crm_status text not null default 'New',
    source_page text,
    language text,
    consent_status text not null default 'not_requested',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint sales_leads_score_range check (lead_score >= 0 and lead_score <= 100),
    constraint sales_leads_classification_check check (lead_classification in ('Hot', 'Warm', 'Cold')),
    constraint sales_leads_consent_check check (consent_status in ('not_requested', 'granted', 'declined'))
);

create table if not exists public.sales_conversations (
    id uuid primary key default gen_random_uuid(),
    conversation_key text unique not null,
    lead_id uuid references public.sales_leads(id),
    status text not null default 'active',
    language text,
    source_page text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_message_at timestamptz,
    constraint sales_conversations_status_check check (status in ('active', 'closed', 'handover_requested'))
);

create table if not exists public.sales_messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references public.sales_conversations(id) on delete cascade,
    role text not null,
    content text not null,
    intent text,
    grounding_status text,
    grounding_sources jsonb not null default '[]'::jsonb,
    recommended_services jsonb not null default '[]'::jsonb,
    requires_action boolean not null default false,
    action_intent text,
    source_metadata jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    constraint sales_messages_role_check check (role in ('user', 'assistant'))
);

create index if not exists sales_conversations_conversation_key_idx on public.sales_conversations (conversation_key);
create index if not exists sales_conversations_lead_id_idx on public.sales_conversations (lead_id);
create index if not exists sales_messages_conversation_created_idx on public.sales_messages (conversation_id, created_at);
create index if not exists sales_leads_classification_idx on public.sales_leads (lead_classification);
create index if not exists sales_leads_crm_status_idx on public.sales_leads (crm_status);
create index if not exists sales_leads_created_at_idx on public.sales_leads (created_at);
create index if not exists sales_leads_email_idx on public.sales_leads (lower(email)) where email is not null;
create index if not exists sales_leads_phone_idx on public.sales_leads (phone) where phone is not null;

drop trigger if exists set_sales_leads_updated_at on public.sales_leads;
create trigger set_sales_leads_updated_at
before update on public.sales_leads
for each row execute function public.set_sales_updated_at();

drop trigger if exists set_sales_conversations_updated_at on public.sales_conversations;
create trigger set_sales_conversations_updated_at
before update on public.sales_conversations
for each row execute function public.set_sales_updated_at();

alter table public.sales_leads enable row level security;
alter table public.sales_conversations enable row level security;
alter table public.sales_messages enable row level security;

comment on table public.sales_leads is 'Server-side sales lead profiles for progressive AI Sales Agent qualification. No anonymous public write policies.';
comment on table public.sales_conversations is 'Persistent sales conversations linked optionally to sales leads. Frontend must use a backend API, not direct table access.';
comment on table public.sales_messages is 'Safe persisted user/assistant messages and metadata. Hidden prompts, raw RAG context, credentials, and embeddings must never be stored.';
