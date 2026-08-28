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

-- Completed main-draw matches from the research snapshot (H2H display).
-- Retired and walkover matches are intentionally never stored.
create table if not exists match_results (
  id               bigint generated always as identity primary key,
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

-- Backtest results. Written only by backend/scripts/run_backtest.py (local);
-- the dashboard reads these tables and never computes a backtest itself.
create table if not exists backtest_runs (
  id                 bigint generated always as identity primary key,
  created_at         timestamptz not null default now(),
  dataset            text not null,
  dataset_start      date not null,
  dataset_end        date not null,
  n_matches          integer not null,
  models_fingerprint text not null,
  model_source       text not null,
  trained_through    date,
  stake              double precision not null default 1
);

create table if not exists backtest_model_results (
  id           bigint generated always as identity primary key,
  run_id       bigint not null references backtest_runs(id) on delete cascade,
  model        text not null,
  is_benchmark boolean not null default false,
  n_scored     integer not null,
  brier        double precision not null,
  log_loss     double precision not null,
  accuracy     double precision not null,
  n_bets       integer not null default 0,
  n_bet_wins   integer not null default 0,
  staked       double precision not null default 0,
  profit       double precision not null default 0,
  roi          double precision
);
create index if not exists idx_backtest_results_run on backtest_model_results(run_id);

create table if not exists backtest_matches (
  id            bigint generated always as identity primary key,
  run_id        bigint not null references backtest_runs(id) on delete cascade,
  row_index     integer not null,
  match_date    date not null,
  player1       text not null,
  player2       text not null,
  surface       text,
  series        text,
  tournament    text,
  player1_won   boolean not null,
  b365_p1_odds  double precision,
  b365_p2_odds  double precision
);
create index if not exists idx_backtest_matches_run on backtest_matches(run_id);
create index if not exists idx_backtest_matches_date on backtest_matches(match_date);
create index if not exists idx_backtest_matches_surface on backtest_matches(surface);

create table if not exists backtest_predictions (
  id            bigint generated always as identity primary key,
  run_id        bigint not null references backtest_runs(id) on delete cascade,
  match_id      bigint not null references backtest_matches(id) on delete cascade,
  model         text not null,
  prob_player1  double precision not null,
  bet_side      text,
  bet_odds      double precision,
  bet_profit    double precision
);
create index if not exists idx_backtest_predictions_run on backtest_predictions(run_id);
create index if not exists idx_backtest_predictions_match on backtest_predictions(match_id);
create index if not exists idx_backtest_predictions_model on backtest_predictions(model);
