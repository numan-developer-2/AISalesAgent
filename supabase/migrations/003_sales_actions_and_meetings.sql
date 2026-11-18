create table if not exists public.sales_actions (
    id uuid primary key default gen_random_uuid(),
    action_reference text unique not null,
    conversation_id uuid not null references public.sales_conversations(id) on delete cascade,
    lead_id uuid references public.sales_leads(id),
    action_type text not null,
    status text not null,
    requires_confirmation boolean not null default false,
    confirmation_status text not null default 'not_required',
    confirmed_at timestamptz,
    idempotency_key text unique not null,
    payload jsonb not null default '{}'::jsonb,
    result jsonb not null default '{}'::jsonb,
    error_code text,
    error_message text,
    expires_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    constraint sales_actions_type_check check (action_type in ('check_meeting_availability', 'book_meeting', 'request_proposal', 'human_handover')),
    constraint sales_actions_status_check check (status in ('requested', 'awaiting_confirmation', 'ready', 'executing', 'completed', 'failed', 'cancelled', 'expired')),
    constraint sales_actions_confirmation_check check (confirmation_status in ('not_required', 'required', 'confirmed', 'rejected', 'expired'))
);

create table if not exists public.sales_meetings (
    id uuid primary key default gen_random_uuid(),
    meeting_reference text unique not null,
    action_id uuid unique not null references public.sales_actions(id) on delete cascade,
    conversation_id uuid not null references public.sales_conversations(id) on delete cascade,
    lead_id uuid references public.sales_leads(id),
    requested_date date,
    requested_daypart text,
    start_at timestamptz,
    end_at timestamptz,
    timezone text not null default 'Asia/Karachi',
    duration_minutes integer not null default 30,
    buffer_minutes integer not null default 15,
    calendar_provider text,
    external_event_id text,
    external_event_url text,
    status text not null default 'requested',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint sales_meetings_status_check check (status in ('requested', 'slot_offered', 'awaiting_confirmation', 'confirmed', 'booked', 'failed', 'cancelled')),
    constraint sales_meetings_duration_check check (duration_minutes > 0 and buffer_minutes >= 0)
);

create table if not exists public.sales_action_audit (
    id uuid primary key default gen_random_uuid(),
    action_id uuid not null references public.sales_actions(id) on delete cascade,
    event_type text not null,
    previous_status text,
    new_status text,
    safe_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists sales_actions_conversation_idx on public.sales_actions (conversation_id, created_at);
create index if not exists sales_actions_lead_idx on public.sales_actions (lead_id);
create index if not exists sales_actions_type_status_idx on public.sales_actions (action_type, status);
create index if not exists sales_actions_idempotency_idx on public.sales_actions (idempotency_key);
create index if not exists sales_meetings_conversation_idx on public.sales_meetings (conversation_id, created_at);
create index if not exists sales_meetings_action_idx on public.sales_meetings (action_id);
create index if not exists sales_action_audit_action_idx on public.sales_action_audit (action_id, created_at);

drop trigger if exists set_sales_actions_updated_at on public.sales_actions;
create trigger set_sales_actions_updated_at
before update on public.sales_actions
for each row execute function public.set_sales_updated_at();

drop trigger if exists set_sales_meetings_updated_at on public.sales_meetings;
create trigger set_sales_meetings_updated_at
before update on public.sales_meetings
for each row execute function public.set_sales_updated_at();

alter table public.sales_actions enable row level security;
alter table public.sales_meetings enable row level security;
alter table public.sales_action_audit enable row level security;

comment on table public.sales_actions is 'Authoritative server-side action log for sales tool requests. No anonymous public write policies.';
comment on table public.sales_meetings is 'Server-side meeting booking records and provider references. Calendar integrations are connected through backend adapters only.';
comment on table public.sales_action_audit is 'Sanitized action audit trail. Must never store credentials, auth headers, hidden prompts, raw RAG context, or provider secrets.';
