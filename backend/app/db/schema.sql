-- Supabase schema (run once in the Supabase SQL editor).
-- Kept in sync with backend/app/db/models.py; the seed script can also
-- create these tables automatically via SQLAlchemy.

create table if not exists players (
  id               bigint generated always as identity primary key,
  slug             text unique not null,
  name             text unique not null,          -- research format, e.g. 'Alcaraz C.'
  rank             double precision,
  elo_global       double precision not null default 1500,
  elo_hard         double precision not null default 1500,
  elo_clay         double precision not null default 1500,
  elo_grass        double precision not null default 1500,
  matches_global   integer not null default 0,
  matches_hard     integer not null default 0,
  matches_clay     integer not null default 0,
  matches_grass    integer not null default 0,
  last_match_date  date,
  as_of            date,
  updated_at       timestamptz not null default now()
);

-- One row per match: duplicate dates are intentional (two matches in one
-- day both count toward the 7-day workload feature).
create table if not exists player_recent_matches (
  id          bigint generated always as identity primary key,
  player_id   bigint not null references players(id) on delete cascade,
  match_date  date not null
);
create index if not exists idx_recent_matches_player on player_recent_matches(player_id);

-- Completed main-draw matches (H2H display + refresh dedup). Retired and
-- walkover matches are intentionally never stored.
create table if not exists match_results (
  id               bigint generated always as identity primary key,
  api_match_id     text unique,
  source           text not null default 'api',   -- 'api' | 'research'
  date             date not null,
  surface          text,
  tier             text,
  tournament_name  text,
  winner_id        bigint not null references players(id),
  loser_id         bigint not null references players(id),
  score            text
);
create index if not exists idx_match_results_date on match_results(date);
create index if not exists idx_match_results_winner on match_results(winner_id);
create index if not exists idx_match_results_loser on match_results(loser_id);

-- One row per refresh run; latest successful row is the watermark.
create table if not exists refresh_log (
  id               bigint generated always as identity primary key,
  ran_at           timestamptz not null default now(),
  window_start     date not null,
  window_end       date not null,
  status           text not null,
  matches_applied  integer not null default 0,
  retired_skipped  integer not null default 0,
  new_players      integer not null default 0,
  rank_updates     integer not null default 0,
  requests_used    integer not null default 0,
  detail           text
);

-- Tennis API player id mapping lives on players.
alter table players add column if not exists api_player_id bigint unique;

-- Placeholder for future bet tracking.
create table if not exists bets (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now()
);
