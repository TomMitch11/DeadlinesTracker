from datetime import date, datetime, timedelta, timezone as tz
from unittest.mock import MagicMock, patch

import pytest
from icalendar import Calendar, Event

import ical_sync
from ical_sync import (
    _fetch_events,
    _league_home_uids,
    _parse_away_team,
    _parse_dt,
    sync_all_ical_teams,
    sync_team,
)

TEAM = {
    "id": "team-1",
    "name": "LA Galaxy",
    "season": "2026",
    "deadline_days": 3,
    "feed_source": "ical",
    "feed_team_id": "la-galaxy",
    "feed_competition_id": "",
    "competition": "MLS",
    "default_venue": "Dignity Health Sports Park",
}


def _ics(events: list[dict]) -> bytes:
    """Build minimal ICS bytes from a list of {summary, dtstart, uid} dicts."""
    cal = Calendar()
    for e in events:
        ev = Event()
        ev.add("summary", e["summary"])
        if "dtstart" in e:
            ev.add("dtstart", e["dtstart"])
        if "uid" in e:
            ev.add("uid", e["uid"])
        cal.add_component(ev)
    return cal.to_ical()


def _fake_response(content: bytes):
    resp = MagicMock()
    resp.content = content
    resp.raise_for_status.return_value = None
    return resp


# ── _parse_dt ────────────────────────────────────────────────────────────────

def test_parse_dt_converts_tz_aware_to_utc():
    dt = datetime(2026, 6, 10, 21, 0, tzinfo=tz(timedelta(hours=-4)))
    match_date, match_time = _parse_dt(dt)
    assert match_date == date(2026, 6, 11)
    assert match_time == "01:00"


def test_parse_dt_date_only_has_no_time():
    match_date, match_time = _parse_dt(date(2026, 6, 10))
    assert match_date == date(2026, 6, 10)
    assert match_time is None


# ── _parse_away_team ─────────────────────────────────────────────────────────

def test_parse_away_team_dash_separator():
    assert _parse_away_team("LA Galaxy - Portland Timbers") == "Portland Timbers"


def test_parse_away_team_v_separator():
    assert _parse_away_team("Arsenal v Chelsea") == "Chelsea"


def test_parse_away_team_no_separator_returns_empty():
    assert _parse_away_team("Some weird summary") == ""


# ── _league_home_uids ────────────────────────────────────────────────────────

def test_league_home_uids_returns_empty_on_connection_error():
    with patch("ical_sync._fetch_events", side_effect=ConnectionError("timeout")):
        result = _league_home_uids("some-league", "LA Galaxy")
    assert result == set()


def test_league_home_uids_propagates_non_network_errors():
    with patch("ical_sync._fetch_events", side_effect=ValueError("bad calendar")):
        with pytest.raises(ValueError):
            _league_home_uids("some-league", "LA Galaxy")


def test_league_home_uids_filters_by_home_prefix():
    future = datetime.now(tz.utc) + timedelta(days=10)
    events = [
        {"summary": "LA Galaxy - Portland", "dtstart": future, "uid": "home-uid"},
        {"summary": "Seattle - LA Galaxy", "dtstart": future, "uid": "away-uid"},
    ]
    with patch("ical_sync._fetch_events", return_value=[
        e for e in Calendar.from_ical(_ics(events)).walk() if e.name == "VEVENT"
    ]):
        result = _league_home_uids("mls", "LA Galaxy")
    assert result == {"home-uid"}


# ── sync_team ────────────────────────────────────────────────────────────────

def test_sync_team_raises_if_no_feed_team_id():
    with pytest.raises(ValueError, match="feed_team_id"):
        sync_team({**TEAM, "feed_team_id": ""}, [])


def test_sync_team_adds_new_fixture():
    future = datetime.now(tz.utc) + timedelta(days=10)
    content = _ics([{"summary": "LA Galaxy - Portland", "dtstart": future, "uid": "evt-1"}])
    with patch("ical_sync.requests.get", return_value=_fake_response(content)), \
         patch("db.get_fixture_by_feed_event_id", return_value=None), \
         patch("db.upsert_fixture", return_value="fid-1") as mock_upsert, \
         patch("db.create_upload_statuses_for_fixture") as mock_statuses:
        stats, new_fixtures, rescheduled = sync_team(TEAM, [])

    assert stats["upserted"] == 1
    assert len(new_fixtures) == 1
    assert new_fixtures[0]["away_team"] == "Portland"
    assert rescheduled == []
    mock_upsert.assert_called_once()
    mock_statuses.assert_called_once_with("fid-1", "team-1")


def test_sync_team_skips_past_match():
    past = datetime.now(tz.utc) - timedelta(days=10)
    content = _ics([{"summary": "LA Galaxy - Portland", "dtstart": past, "uid": "evt-1"}])
    with patch("ical_sync.requests.get", return_value=_fake_response(content)), \
         patch("db.upsert_fixture") as mock_upsert:
        stats, new_fixtures, rescheduled = sync_team(TEAM, [])

    assert stats["skipped_past"] == 1
    assert stats["upserted"] == 0
    mock_upsert.assert_not_called()


def test_sync_team_skips_summary_with_no_away_team():
    future = datetime.now(tz.utc) + timedelta(days=10)
    content = _ics([{"summary": "Season opener", "dtstart": future, "uid": "evt-1"}])
    with patch("ical_sync.requests.get", return_value=_fake_response(content)), \
         patch("db.upsert_fixture") as mock_upsert:
        stats, new_fixtures, rescheduled = sync_team(TEAM, [])

    assert stats["skipped_other"] == 1
    mock_upsert.assert_not_called()


def test_sync_team_handles_event_with_no_uid():
    future = datetime.now(tz.utc) + timedelta(days=10)
    content = _ics([{"summary": "LA Galaxy - Portland", "dtstart": future}])
    with patch("ical_sync.requests.get", return_value=_fake_response(content)), \
         patch("db.get_fixture_by_feed_event_id") as mock_lookup, \
         patch("db.upsert_fixture", return_value="fid-1") as mock_upsert, \
         patch("db.create_upload_statuses_for_fixture") as mock_statuses:
        stats, new_fixtures, rescheduled = sync_team(TEAM, [])

    assert stats["upserted"] == 1
    mock_lookup.assert_not_called()
    mock_statuses.assert_called_once_with("fid-1", "team-1")


def test_sync_team_detects_reschedule():
    future = datetime.now(tz.utc) + timedelta(days=10)
    content = _ics([{"summary": "LA Galaxy - Portland", "dtstart": future, "uid": "evt-1"}])
    existing = {"id": "fid-1", "match_date": "2020-01-01", "match_time": None, "away_team": "Portland", "venue": ""}
    with patch("ical_sync.requests.get", return_value=_fake_response(content)), \
         patch("db.get_fixture_by_feed_event_id", return_value=existing), \
         patch("db.upsert_fixture", return_value="fid-1"), \
         patch("db.create_upload_statuses_for_fixture") as mock_statuses:
        stats, new_fixtures, rescheduled = sync_team(TEAM, [])

    assert new_fixtures == []
    assert len(rescheduled) == 1
    assert rescheduled[0]["old_date"] == "2020-01-01"
    mock_statuses.assert_not_called()


def test_sync_team_flags_cup_warning_when_not_in_league_feed():
    future = datetime.now(tz.utc) + timedelta(days=10)
    team_content = _ics([{"summary": "LA Galaxy - Portland", "dtstart": future, "uid": "team-only-uid"}])
    league_content = _ics([{"summary": "LA Galaxy - Seattle", "dtstart": future, "uid": "league-uid"}])
    team_with_league = {**TEAM, "feed_competition_id": "mls"}

    with patch(
        "ical_sync.requests.get",
        side_effect=[_fake_response(team_content), _fake_response(league_content)],
    ), \
         patch("db.get_fixture_by_feed_event_id", return_value=None), \
         patch("db.upsert_fixture", return_value="fid-1"), \
         patch("db.create_upload_statuses_for_fixture"):
        stats, new_fixtures, rescheduled = sync_team(team_with_league, [])

    assert new_fixtures[0]["cup_warning"] is not None


# ── sync_all_ical_teams ──────────────────────────────────────────────────────

def test_sync_all_ical_teams_isolates_per_team_errors():
    good_team = {**TEAM, "name": "Good Team"}
    bad_team = {**TEAM, "name": "Bad Team", "feed_team_id": ""}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[good_team, bad_team]), \
         patch("ical_sync.sync_team") as mock_sync:
        def side_effect(team, holidays):
            if team["name"] == "Good Team":
                return {"upserted": 1}, [{"away_team": "X"}], []
            raise ValueError("No feed_team_id set")
        mock_sync.side_effect = side_effect

        with patch("notifications.send_sync_summary") as mock_notify:
            results = sync_all_ical_teams()

    assert results["Good Team"] == {"upserted": 1}
    assert "error" in results["Bad Team"]
    mock_notify.assert_called_once_with([{"away_team": "X"}], [])


def test_sync_all_ical_teams_filters_by_feed_source():
    ical_team = {**TEAM, "feed_source": "ical"}
    other_team = {**TEAM, "name": "Other", "feed_source": "opta"}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[ical_team, other_team]), \
         patch("ical_sync.sync_team", return_value=({"upserted": 0}, [], [])) as mock_sync:
        sync_all_ical_teams()

    assert mock_sync.call_count == 1


def test_sync_all_ical_teams_skips_notification_when_nothing_changed():
    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[TEAM]), \
         patch("ical_sync.sync_team", return_value=({"upserted": 0}, [], [])), \
         patch("notifications.send_sync_summary") as mock_notify:
        sync_all_ical_teams()

    mock_notify.assert_not_called()
