from datetime import date, timedelta
from unittest.mock import patch

import pytest

from stats_perform_sync import sync_team, sync_all_stats_perform_teams, _parse_event_date
from deadline_calc import calc_fixture_deadlines, deadlines_to_str

TEAM = {
    "id": "team-1",
    "name": "Denver Broncos",
    "season": "2026",
    "deadline_days": 3,
    "feed_source": "statsperform",
    "feed_team_id": "332",
}

FAKE_CFG = {"sp_api_key": "key", "sp_api_secret": "secret"}


def _event(event_id, home_id, away_id, home_loc, home_nick, away_loc, away_nick, local_iso, utc_iso):
    return {
        "eventId": event_id,
        "startDate": [
            {"full": local_iso, "dateType": "Local"},
            {"full": utc_iso, "dateType": "UTC"},
        ],
        "teams": [
            {"teamId": home_id, "location": home_loc, "nickname": home_nick,
             "teamLocationType": {"teamLocationTypeId": 1, "name": "home"}},
            {"teamId": away_id, "location": away_loc, "nickname": away_nick,
             "teamLocationType": {"teamLocationTypeId": 2, "name": "away"}},
        ],
    }


def _raw(events):
    return {"apiResults": [{"league": {"season": {"eventType": [{"events": events}]}}}]}


# ── _parse_event_date ────────────────────────────────────────────────────────

def test_parse_event_date_extracts_date_time_and_offset():
    start_date = [
        {"full": "2026-08-21T19:00:00", "dateType": "Local"},
        {"full": "2026-08-22T01:00:00", "dateType": "UTC"},
    ]
    match_date, match_time, utc_offset = _parse_event_date(start_date)
    assert match_date == date(2026, 8, 22)
    assert match_time == "01:00"
    assert utc_offset == "-06:00"


def test_parse_event_date_missing_utc_returns_nones():
    match_date, match_time, utc_offset = _parse_event_date(
        [{"full": "2026-08-21T19:00:00", "dateType": "Local"}]
    )
    assert match_date is None
    assert match_time is None
    assert utc_offset is None


def test_parse_event_date_missing_local_still_returns_date_and_time():
    match_date, match_time, utc_offset = _parse_event_date(
        [{"full": "2026-08-22T01:00:00", "dateType": "UTC"}]
    )
    assert match_date == date(2026, 8, 22)
    assert match_time == "01:00"
    assert utc_offset is None


# ── sync_team ────────────────────────────────────────────────────────────────

def test_sync_team_raises_if_no_feed_team_id():
    with pytest.raises(ValueError, match="feed_team_id"):
        sync_team({**TEAM, "feed_team_id": ""}, [])


def test_sync_team_upserts_home_games_only():
    future = date.today() + timedelta(days=10)
    # Local kickoff is the evening before the UTC-dated calendar day (e.g. Denver MDT, UTC-6).
    future_local = f"{future - timedelta(days=1)}T19:00:00"
    future_utc = f"{future}T01:00:00"
    events = [
        _event(1, 332, 335, "Denver", "Broncos", "Green Bay", "Packers", future_local, future_utc),
        _event(2, 335, 332, "Green Bay", "Packers", "Denver", "Broncos", future_local, future_utc),
    ]
    raw = _raw(events)

    with patch("stats_perform_sync.get_sp_config", return_value=FAKE_CFG), \
         patch("stats_perform_sync._fetch_schedule", return_value=raw), \
         patch("db.upsert_fixture", return_value="fid-1") as mock_upsert, \
         patch("db.create_upload_statuses_for_fixture") as mock_statuses:
        stats = sync_team(TEAM, [])

    assert stats["upserted"] == 1
    assert stats["total_home"] == 1
    mock_upsert.assert_called_once()
    mock_statuses.assert_called_once_with("fid-1", "team-1")
    fixture = mock_upsert.call_args[0][0]
    assert fixture["away_team"] == "Green Bay Packers"
    assert fixture["source"] == "statsperform"
    assert fixture["feed_event_id"] == "sp_1"
    assert fixture["match_utc_offset"] == "-06:00"
    expected = deadlines_to_str(calc_fixture_deadlines(future, TEAM, {}, []))
    assert fixture["sales_deadline"] == expected["sales_deadline"]
    assert fixture["partner_success_deadline"] == expected["partner_success_deadline"]


def test_sync_team_skips_past_game():
    past = date.today() - timedelta(days=10)
    events = [_event(1, 332, 335, "Denver", "Broncos", "Green Bay", "Packers", f"{past}T19:00:00", f"{past}T01:00:00")]
    raw = _raw(events)

    with patch("stats_perform_sync.get_sp_config", return_value=FAKE_CFG), \
         patch("stats_perform_sync._fetch_schedule", return_value=raw), \
         patch("db.upsert_fixture") as mock_upsert:
        stats = sync_team(TEAM, [])

    assert stats["skipped_past"] == 1
    mock_upsert.assert_not_called()


def test_sync_team_skips_deadline_fields_for_overridden_fixture():
    future = date.today() + timedelta(days=10)
    events = [_event(77, 332, 335, "Denver", "Broncos", "Green Bay", "Packers", f"{future}T19:00:00", f"{future}T01:00:00")]
    raw = _raw(events)

    with patch("stats_perform_sync.get_sp_config", return_value=FAKE_CFG), \
         patch("stats_perform_sync._fetch_schedule", return_value=raw), \
         patch("db.upsert_fixture", return_value="fid-1") as mock_upsert, \
         patch("db.create_upload_statuses_for_fixture"):
        sync_team(TEAM, [], {}, {"sp_77"})

    fixture = mock_upsert.call_args[0][0]
    assert "approval_deadline" not in fixture
    assert "wc_deadline" not in fixture
    assert "sales_deadline" not in fixture
    assert "partner_success_deadline" not in fixture


def test_sync_team_handles_empty_response():
    with patch("stats_perform_sync.get_sp_config", return_value=FAKE_CFG), \
         patch("stats_perform_sync._fetch_schedule", return_value={}), \
         patch("db.upsert_fixture") as mock_upsert:
        stats = sync_team(TEAM, [])

    assert stats == {"upserted": 0, "skipped_past": 0, "skipped_other": 0, "total_home": 0, "total_matches": 0}
    mock_upsert.assert_not_called()


# ── sync_all_stats_perform_teams ─────────────────────────────────────────────

def test_sync_all_stats_perform_teams_isolates_per_team_errors():
    good_team = {**TEAM, "name": "Good Team"}
    bad_team = {**TEAM, "name": "Bad Team", "feed_team_id": ""}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[good_team, bad_team]), \
         patch("stats_perform_sync.sync_team") as mock_sync:
        def side_effect(team, holidays, weekday_rules=None, overridden_ids=None):
            if team["name"] == "Good Team":
                return {"upserted": 1}
            raise ValueError("No feed_team_id set")
        mock_sync.side_effect = side_effect

        results = sync_all_stats_perform_teams()

    assert results["Good Team"] == {"upserted": 1}
    assert "error" in results["Bad Team"]


def test_sync_all_stats_perform_teams_filters_by_feed_source():
    sp_team = {**TEAM, "feed_source": "statsperform"}
    other_team = {**TEAM, "name": "Other", "feed_source": "opta"}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[sp_team, other_team]), \
         patch("stats_perform_sync.sync_team", return_value={"upserted": 0}) as mock_sync:
        sync_all_stats_perform_teams()

    assert mock_sync.call_count == 1
