from datetime import date, timedelta
from unittest.mock import patch

import pytest

from api_football_sync import (
    _parse_fixture_date,
    _season_year,
    sync_all_api_football_teams,
    sync_team,
)
from deadline_calc import calc_all_deadlines

TEAM = {
    "id": "team-1",
    "name": "Houston Dash",
    "season": "2025-26",
    "deadline_days": 3,
    "feed_source": "api_football",
    "feed_team_id": "1234",
    "feed_competition_id": "253",
}

FAKE_CFG = {"api_key": "key"}


# ── _season_year ─────────────────────────────────────────────────────────────

def test_season_year_hyphenated():
    assert _season_year("2025-26") == "2025"


def test_season_year_single_year():
    assert _season_year("2026") == "2026"


# ── _parse_fixture_date ──────────────────────────────────────────────────────

def test_parse_fixture_date_converts_to_utc():
    match_date, match_time, utc_offset = _parse_fixture_date("2026-06-10T19:00:00+02:00")
    assert match_date == date(2026, 6, 10)
    assert match_time == "17:00"
    assert utc_offset == "+02:00"


def test_parse_fixture_date_negative_offset():
    match_date, match_time, utc_offset = _parse_fixture_date("2026-06-10T12:00:00-05:00")
    assert utc_offset == "-05:00"
    assert match_time == "17:00"


def test_parse_fixture_date_invalid_returns_nones():
    match_date, match_time, utc_offset = _parse_fixture_date("not-a-date")
    assert match_date is None
    assert match_time is None
    assert utc_offset is None


# ── sync_team ────────────────────────────────────────────────────────────────

def test_sync_team_raises_if_no_feed_team_id():
    with pytest.raises(ValueError, match="feed_team_id"):
        sync_team({**TEAM, "feed_team_id": ""}, [])


def test_sync_team_upserts_home_fixtures_only():
    future = f"{date.today() + timedelta(days=10)}T19:00:00+00:00"
    data = {
        "response": [
            {
                "fixture": {"id": 111, "date": future},
                "teams": {"home": {"id": 1234, "name": "Houston Dash"}, "away": {"id": 999, "name": "Kansas City"}},
            },
            {
                "fixture": {"id": 112, "date": future},
                "teams": {"home": {"id": 999, "name": "Kansas City"}, "away": {"id": 1234, "name": "Houston Dash"}},
            },
        ]
    }

    with patch("api_football_sync.get_api_football_config", return_value=FAKE_CFG), \
         patch("api_football_sync._get", return_value=data) as mock_get, \
         patch("db.upsert_fixture", return_value="fid-1") as mock_upsert, \
         patch("db.create_upload_statuses_for_fixture") as mock_statuses:
        stats = sync_team(TEAM, [])

    assert stats["upserted"] == 1
    assert stats["total_home"] == 1
    mock_upsert.assert_called_once()
    mock_statuses.assert_called_once_with("fid-1", "team-1")
    mock_get.assert_called_once_with(
        "/fixtures",
        {"league": "253", "season": "2025", "team": 1234, "timezone": "UTC"},
        FAKE_CFG,
    )
    fixture = mock_upsert.call_args[0][0]
    expected = calc_all_deadlines(date.today() + timedelta(days=10), TEAM["deadline_days"], [])
    assert fixture["sales_deadline"] == str(expected["sales_deadline"])
    assert fixture["partner_success_deadline"] == str(expected["partner_success_deadline"])


def test_sync_team_skips_past_fixture():
    past = f"{date.today() - timedelta(days=10)}T19:00:00+00:00"
    data = {"response": [{
        "fixture": {"id": 111, "date": past},
        "teams": {"home": {"id": 1234, "name": "Houston Dash"}, "away": {"id": 999, "name": "Kansas City"}},
    }]}

    with patch("api_football_sync.get_api_football_config", return_value=FAKE_CFG), \
         patch("api_football_sync._get", return_value=data), \
         patch("db.upsert_fixture") as mock_upsert:
        stats = sync_team(TEAM, [])

    assert stats["skipped_past"] == 1
    mock_upsert.assert_not_called()


def test_sync_team_skips_unparseable_date():
    data = {"response": [{
        "fixture": {"id": 111, "date": "garbage"},
        "teams": {"home": {"id": 1234, "name": "Houston Dash"}, "away": {"id": 999, "name": "Kansas City"}},
    }]}

    with patch("api_football_sync.get_api_football_config", return_value=FAKE_CFG), \
         patch("api_football_sync._get", return_value=data), \
         patch("db.upsert_fixture") as mock_upsert:
        stats = sync_team(TEAM, [])

    assert stats["skipped_other"] == 1
    mock_upsert.assert_not_called()


# ── sync_all_api_football_teams ──────────────────────────────────────────────

def test_sync_all_api_football_teams_isolates_per_team_errors():
    good_team = {**TEAM, "name": "Good Team"}
    bad_team = {**TEAM, "name": "Bad Team", "feed_team_id": ""}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[good_team, bad_team]), \
         patch("api_football_sync.sync_team") as mock_sync:
        def side_effect(team, holidays):
            if team["name"] == "Good Team":
                return {"upserted": 1}
            raise ValueError("No feed_team_id set")
        mock_sync.side_effect = side_effect

        results = sync_all_api_football_teams()

    assert results["Good Team"] == {"upserted": 1}
    assert "error" in results["Bad Team"]


def test_sync_all_api_football_teams_filters_by_feed_source():
    apif_team = {**TEAM, "feed_source": "api_football"}
    other_team = {**TEAM, "name": "Other", "feed_source": "ical"}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[apif_team, other_team]), \
         patch("api_football_sync.sync_team", return_value={"upserted": 0}) as mock_sync:
        sync_all_api_football_teams()

    assert mock_sync.call_count == 1
