"""Unit tests: name matching and research-identical Elo application."""
from __future__ import annotations

import datetime

from app.config import GLOBAL_BASE_K, SURFACE_BASE_K, TIER_MULTIPLIERS
from app.services.name_matching import candidate_research_names
from app.services.refresh import _apply_elo_updates, _expected_score


class TestCandidateNames:
    def test_simple_name(self):
        assert candidate_research_names("Jannik Sinner") == ["Sinner J."]

    def test_double_surname_prefers_full_then_parts(self):
        candidates = candidate_research_names("Pedro Martinez Portero")
        assert candidates[0] == "Martinez Portero P."
        assert "Martinez P." in candidates
        assert "Portero P." in candidates

    def test_triple_surname(self):
        candidates = candidate_research_names("Alejandro Davidovich Fokina")
        assert candidates[0] == "Davidovich Fokina A."

    def test_hyphenated_given_name_multi_initials(self):
        # DB stores "Struff J.L."
        candidates = candidate_research_names("Jan-Lennard Struff")
        assert "Struff J.L." in candidates
        assert "Struff J." in candidates
        assert "Struff L." in candidates

    def test_second_given_name_initial(self):
        # DB stores "Vallejo D." for Adolfo Daniel Vallejo
        candidates = candidate_research_names("Adolfo Daniel Vallejo")
        assert "Vallejo A.D." in candidates
        assert "Vallejo D." in candidates

    def test_single_token_gives_nothing(self):
        assert candidate_research_names("Sinner") == []


class TestNormalize:
    def test_strips_punctuation_and_case(self):
        from app.services.name_matching import normalize

        assert normalize("Tirante T. A.") == normalize("Tirante T.A.")
        assert normalize("Auger-Aliassime F.") == normalize("Auger Aliassime F.")


class FakePlayer:
    """Duck-typed stand-in for the ORM Player inside _apply_elo_updates."""

    _next_id = 1

    def __init__(self, elo_global=1500.0, elo_hard=1500.0, elo_clay=1500.0, elo_grass=1500.0):
        self.id = FakePlayer._next_id
        FakePlayer._next_id += 1
        self.elo_global = elo_global
        self.elo_hard = elo_hard
        self.elo_clay = elo_clay
        self.elo_grass = elo_grass


def make_match(winner, loser, date, tier="ATP 250", surface="Hard"):
    return {
        "winner_db_id": winner.id,
        "loser_db_id": loser.id,
        "date": date,
        "tier": tier,
        "surface": surface,
    }


class TestEloApplication:
    def test_equal_players_gain_exact_half_k(self):
        a, b = FakePlayer(), FakePlayer()
        day = datetime.date(2026, 8, 20)
        _apply_elo_updates([make_match(a, b, day)], {a.id: a, b.id: b})
        expected = GLOBAL_BASE_K * TIER_MULTIPLIERS["ATP 250"] * 0.5
        assert abs(a.elo_global - (1500.0 + expected)) < 1e-9
        assert abs(b.elo_global - (1500.0 - expected)) < 1e-9
        # Surface Elo uses the surface K (Hard=32) with the same multiplier.
        surface_expected = SURFACE_BASE_K["Hard"] * TIER_MULTIPLIERS["ATP 250"] * 0.5
        assert abs(a.elo_hard - (1500.0 + surface_expected)) < 1e-9

    def test_zero_sum(self):
        a, b, c = FakePlayer(1600.0), FakePlayer(1550.0), FakePlayer(1450.0)
        players = {p.id: p for p in (a, b, c)}
        day1, day2 = datetime.date(2026, 8, 20), datetime.date(2026, 8, 21)
        matches = [
            make_match(a, b, day1, tier="ATP Masters 1000", surface="Clay"),
            make_match(a, c, day2, tier="Grand Slam", surface="Clay"),
        ]
        before = sum(p.elo_global for p in players.values())
        _apply_elo_updates(matches, players)
        after = sum(p.elo_global for p in players.values())
        assert abs(before - after) < 1e-9

    def test_same_day_batching_uses_start_of_day_ratings(self):
        # a beats b, then a beats c on the SAME day: a's second match must be
        # rated from a's start-of-day Elo, not the post-first-match Elo.
        a, b, c = FakePlayer(1500.0), FakePlayer(1500.0), FakePlayer(1500.0)
        players = {p.id: p for p in (a, b, c)}
        day = datetime.date(2026, 8, 20)
        _apply_elo_updates(
            [make_match(a, b, day), make_match(a, c, day)],
            players,
        )
        # Both wins rated at p=0.5 from the 1500 start-of-day state.
        per_win = GLOBAL_BASE_K * TIER_MULTIPLIERS["ATP 250"] * 0.5
        assert abs(a.elo_global - (1500.0 + 2 * per_win)) < 1e-9

    def test_sequential_days_compound(self):
        a, b = FakePlayer(), FakePlayer()
        players = {a.id: a, b.id: b}
        day1, day2 = datetime.date(2026, 8, 20), datetime.date(2026, 8, 21)
        _apply_elo_updates(
            [make_match(a, b, day1), make_match(a, b, day2)],
            players,
        )
        # Day 2 must be rated from day-1-updated ratings: p > 0.5, so the
        # second gain is strictly smaller than the first.
        first_gain = GLOBAL_BASE_K * TIER_MULTIPLIERS["ATP 250"] * 0.5
        second_probability = _expected_score(1500.0 + first_gain, 1500.0 - first_gain)
        second_gain = GLOBAL_BASE_K * TIER_MULTIPLIERS["ATP 250"] * (1.0 - second_probability)
        assert second_gain < first_gain
        assert abs(a.elo_global - (1500.0 + first_gain + second_gain)) < 1e-9

    def test_unknown_surface_updates_global_only(self):
        a, b = FakePlayer(), FakePlayer()
        players = {a.id: a, b.id: b}
        day = datetime.date(2026, 8, 20)
        _apply_elo_updates([make_match(a, b, day, surface=None)], players)
        assert a.elo_global > 1500.0
        assert a.elo_hard == 1500.0 and a.elo_clay == 1500.0 and a.elo_grass == 1500.0
