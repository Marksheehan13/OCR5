create table if not exists public.organization_identities (
  email text primary key,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  display_name text,
  company_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.organization_identities enable row level security;
revoke all on public.organization_identities from anon, authenticated;
grant all on public.organization_identities to service_role;

create index if not exists organization_identities_org_idx
  on public.organization_identities(organization_id);
