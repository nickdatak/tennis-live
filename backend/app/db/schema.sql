-- GENERATED FILE -- DO NOT EDIT BY HAND. Rendered from models.py via dump_schema.py. Generated 2026-08-29.

CREATE TABLE IF NOT EXISTS backtest_runs (
	id BIGSERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	dataset TEXT NOT NULL, 
	dataset_start DATE NOT NULL, 
	dataset_end DATE NOT NULL, 
	n_matches INTEGER NOT NULL, 
	models_fingerprint TEXT NOT NULL, 
	model_source TEXT NOT NULL, 
	trained_through DATE, 
	stake FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS players (
	id BIGSERIAL NOT NULL, 
	slug TEXT NOT NULL, 
	name TEXT NOT NULL, 
	rank FLOAT, 
	elo_global FLOAT NOT NULL, 
	elo_hard FLOAT NOT NULL, 
	elo_clay FLOAT NOT NULL, 
	elo_grass FLOAT NOT NULL, 
	matches_global INTEGER NOT NULL, 
	matches_hard INTEGER NOT NULL, 
	matches_clay INTEGER NOT NULL, 
	matches_grass INTEGER NOT NULL, 
	last_match_date DATE, 
	as_of DATE, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_players_name ON players (name);
CREATE UNIQUE INDEX IF NOT EXISTS ix_players_slug ON players (slug);

CREATE TABLE IF NOT EXISTS backtest_matches (
	id BIGSERIAL NOT NULL, 
	run_id BIGINT NOT NULL, 
	row_index INTEGER NOT NULL, 
	match_date DATE NOT NULL, 
	player1 TEXT NOT NULL, 
	player2 TEXT NOT NULL, 
	surface TEXT, 
	series TEXT, 
	tournament TEXT, 
	player1_won BOOLEAN NOT NULL, 
	b365_p1_odds FLOAT, 
	b365_p2_odds FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES backtest_runs (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_backtest_matches_match_date ON backtest_matches (match_date);
CREATE INDEX IF NOT EXISTS ix_backtest_matches_run_id ON backtest_matches (run_id);
CREATE INDEX IF NOT EXISTS ix_backtest_matches_surface ON backtest_matches (surface);

CREATE TABLE IF NOT EXISTS backtest_model_results (
	id BIGSERIAL NOT NULL, 
	run_id BIGINT NOT NULL, 
	model TEXT NOT NULL, 
	is_benchmark BOOLEAN NOT NULL, 
	n_scored INTEGER NOT NULL, 
	brier FLOAT NOT NULL, 
	log_loss FLOAT NOT NULL, 
	accuracy FLOAT NOT NULL, 
	n_bets INTEGER NOT NULL, 
	n_bet_wins INTEGER NOT NULL, 
	staked FLOAT NOT NULL, 
	profit FLOAT NOT NULL, 
	roi FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES backtest_runs (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_backtest_model_results_run_id ON backtest_model_results (run_id);

CREATE TABLE IF NOT EXISTS match_results (
	id BIGSERIAL NOT NULL, 
	date DATE NOT NULL, 
	surface TEXT, 
	tier TEXT, 
	tournament_name TEXT, 
	winner_id BIGINT NOT NULL, 
	loser_id BIGINT NOT NULL, 
	score TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(winner_id) REFERENCES players (id), 
	FOREIGN KEY(loser_id) REFERENCES players (id)
);
CREATE INDEX IF NOT EXISTS ix_match_results_date ON match_results (date);
CREATE INDEX IF NOT EXISTS ix_match_results_loser_id ON match_results (loser_id);
CREATE INDEX IF NOT EXISTS ix_match_results_winner_id ON match_results (winner_id);

CREATE TABLE IF NOT EXISTS player_recent_matches (
	id BIGSERIAL NOT NULL, 
	player_id BIGINT NOT NULL, 
	match_date DATE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(player_id) REFERENCES players (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_player_recent_matches_player_id ON player_recent_matches (player_id);

CREATE TABLE IF NOT EXISTS backtest_predictions (
	id BIGSERIAL NOT NULL, 
	run_id BIGINT NOT NULL, 
	match_id BIGINT NOT NULL, 
	model TEXT NOT NULL, 
	prob_player1 FLOAT NOT NULL, 
	bet_side TEXT, 
	bet_odds FLOAT, 
	bet_profit FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES backtest_runs (id) ON DELETE CASCADE, 
	FOREIGN KEY(match_id) REFERENCES backtest_matches (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_backtest_predictions_match_id ON backtest_predictions (match_id);
CREATE INDEX IF NOT EXISTS ix_backtest_predictions_model ON backtest_predictions (model);
CREATE INDEX IF NOT EXISTS ix_backtest_predictions_run_id ON backtest_predictions (run_id);
