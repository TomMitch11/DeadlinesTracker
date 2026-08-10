-- Enable UUID generation
create extension if not exists "uuid-ossp";

-- Statuses (defined first — referenced by upload_statuses)
create table statuses (
    id uuid primary key default uuid_generate_v4(),
    name text not null unique,
    label text not null,
    colour text not null default '#e74c3c',
    display_order integer not null default 0,
    is_system boolean not null default false
);

insert into statuses (name, label, colour, display_order, is_system) values
    ('pending',  'Pending',  '#e74c3c', 1, true),
    ('uploaded', 'Uploaded', '#27ae60', 2, true);

-- Auto-update updated_at on row changes
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- Platforms
create table platforms (
    id uuid primary key default uuid_generate_v4(),
    name text not null unique,
    display_order integer not null default 0
);

-- Teams (one row per Eleven client / home team)
create table teams (
    id uuid primary key default uuid_generate_v4(),
    name text not null unique,
    deadline_days integer not null default 3,
    feed_source text not null default 'manual',
    feed_competition_id text,
    feed_team_id text,
    season text not null default '2025-26',
    competition text,
    default_venue text
);

-- Which platforms are active per team
create table team_platforms (
    team_id uuid not null references teams(id) on delete cascade,
    platform_id uuid not null references platforms(id) on delete cascade,
    primary key (team_id, platform_id)
);

-- Fixtures (home games only)
create table fixtures (
    id uuid primary key default uuid_generate_v4(),
    team_id uuid not null references teams(id) on delete cascade,
    away_team text not null,
    match_date date not null,
    match_time text,
    match_utc_offset text,
    approval_deadline date,
    wc_deadline date,
    sales_deadline date,
    notes text not null default '',
    season text not null,
    source text not null default 'manual',
    feed_event_id text unique,
    venue text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create trigger fixtures_set_updated_at
before update on fixtures
for each row execute procedure set_updated_at();

create index on fixtures(team_id);

-- Upload status per (fixture, platform) — only for active team platforms
create table upload_statuses (
    fixture_id uuid not null references fixtures(id) on delete cascade,
    platform_id uuid not null references platforms(id) on delete cascade,
    status_id uuid not null references statuses(id),
    updated_at timestamptz not null default now(),
    updated_by text not null default 'system',
    primary key (fixture_id, platform_id)
);

create trigger upload_statuses_set_updated_at
before update on upload_statuses
for each row execute procedure set_updated_at();

-- Delivery contact info per (team, platform)
create table delivery_contacts (
    team_id uuid not null references teams(id) on delete cascade,
    platform_id uuid not null references platforms(id) on delete cascade,
    contact_info text not null default '',
    primary key (team_id, platform_id),
    foreign key (team_id, platform_id) references team_platforms(team_id, platform_id) on delete cascade
);

-- Holiday dates for deadline calculation
create table holidays (
    date date primary key,
    description text not null default ''
);
