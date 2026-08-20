from datetime import date, timedelta
from unittest.mock import patch

import pytest

from opta_sync import (
    _attr,
    _ensure_list,
    _parse_f1_json,
    _parse_f1_xml,
    sync_all_opta_teams,
    sync_team,
)
from deadline_calc import calc_all_deadlines

TEAM = {
    "id": "team-1",
    "name": "LA Galaxy",
    "season": "2026",
    "deadline_days": 3,
    "feed_source": "opta",
    "feed_team_id": "tHOME",
    "feed_competition_id": "130",
    "competition": "",
}

FAKE_CFG = {"username": "u", "password": "p", "base_url": "http://opta.example"}


# ── _ensure_list / _attr ─────────────────────────────────────────────────────

def test_ensure_list_wraps_single_value():
    assert _ensure_list({"a": 1}) == [{"a": 1}]


def test_ensure_list_passes_through_list():
    assert _ensure_list([1, 2]) == [1, 2]


def test_ensure_list_none_returns_empty():
    assert _ensure_list(None) == []


def test_attr_returns_attributes_dict():
    assert _attr({"@attributes": {"uID": "t1"}}) == {"uID": "t1"}


def test_attr_missing_returns_empty_dict():
    assert _attr({}) == {}


# ── _parse_f1_json ───────────────────────────────────────────────────────────

def test_parse_f1_json_soccerfeed_structure():
    data = {
        "SoccerFeed": {
            "SoccerDocument": {
                "@attributes": {"competition_name": "MLS"},
                "Team": [
                    {"@attributes": {"uID": "tHOME"}, "Name": {"@value": "LA Galaxy"}},
                    {"@attributes": {"uID": "tAWAY"}, "Name": {"@value": "Portland"}},
                ],
                "MatchData": [
                    {
                        "@attributes": {"uID": "g12345"},
                        "MatchInfo": {
                            "Date": {"@value": "2026-06-10 19:00:00"},
                            "DateLocal": {"@attributes": {"Offset": "-07:00"}},
                        },
                        "TeamData": [
                            {"@attributes": {"Side": "Home", "TeamRef": "tHOME"}},
                            {"@attributes": {"Side": "Away", "TeamRef": "tAWAY"}},
                        ],
                    }
                ],
            }
        }
    }
    matches, teams, competition_name = _parse_f1_json(data)
    assert competition_name == "MLS"
    assert teams == {"tHOME": "LA Galaxy", "tAWAY": "Portland"}
    assert len(matches) == 1
    m = matches[0]
    assert m["game_id"] == "12345"
    assert m["home_team_id"] == "tHOME"
    assert m["away_team_id"] == "tAWAY"
    assert m["utc_offset"] == "-07:00"


def test_parse_f1_json_games_structure():
    data = {"Games": {"Team": [], "MatchData": []}}
    matches, teams, competition_name = _parse_f1_json(data)
    assert matches == []
    assert teams == {}


def test_parse_f1_json_unexpected_structure_raises():
    with pytest.raises(KeyError):
        _parse_f1_json({"SomethingElse": {}})


# ── _parse_f1_xml ────────────────────────────────────────────────────────────

def test_parse_f1_xml_normal_structure():
    xml = """<Root>
        <Team uID="tHOME"><Name>LA Galaxy</Name></Team>
        <SoccerDocument competition_name="MLS">
            <Team uID="tAWAY"><Name>Portland</Name></Team>
            <MatchData uID="g999">
                <MatchInfo>
                    <Date>2026-06-10 19:00:00</Date>
                    <DateLocal Offset="-07:00" />
                </MatchInfo>
                <TeamData Side="Home" TeamRef="tHOME" />
                <TeamData Side="Away" TeamRef="tAWAY" />
            </MatchData>
        </SoccerDocument>
    </Root>"""
    matches, teams, competition_name = _parse_f1_xml(xml)
    assert competition_name == "MLS"
    # Regression: must use the (empty-looking) SoccerDocument, not the outer Root,
    # so the stray top-level Team ("tHOME") must NOT appear here.
    assert teams == {"tAWAY": "Portland"}
    assert len(matches) == 1
    assert matches[0]["game_id"] == "999"


def test_parse_f1_xml_uses_empty_soccerdocument_not_root():
    """SoccerDocument with zero children is falsy in ElementTree but must still be used."""
    xml = """<Root>
        <Team uID="tRoot"><Name>ShouldNotAppear</Name></Team>
        <SoccerDocument competition_name="Empty Comp"></SoccerDocument>
    </Root>"""
    matches, teams, competition_name = _parse_f1_xml(xml)
    assert competition_name == "Empty Comp"
    assert teams == {}
    assert matches == []


# ── sync_team ────────────────────────────────────────────────────────────────

def test_sync_team_raises_if_no_feed_team_id():
    with pytest.raises(ValueError, match="feed_team_id"):
        sync_team({**TEAM, "feed_team_id": ""}, [])


def test_sync_team_upserts_home_matches_only():
    future = str(date.today() + timedelta(days=10))
    matches = [
        {"game_id": "1", "date": f"{future} 19:00:00", "home_team_id": "tHOME", "away_team_id": "tAWAY", "utc_offset": "-07:00"},
        {"game_id": "2", "date": f"{future} 19:00:00", "home_team_id": "tAWAY", "away_team_id": "tHOME", "utc_offset": "-07:00"},
    ]
    teams = {"tHOME": "LA Galaxy", "tAWAY": "Portland"}

    with patch("opta_sync.get_opta_config", return_value=FAKE_CFG), \
         patch("opta_sync._fetch_and_parse", return_value=(matches, teams, "MLS")), \
         patch("db.upsert_fixture", return_value="fid-1") as mock_upsert, \
         patch("db.create_upload_statuses_for_fixture") as mock_statuses:
        stats = sync_team(TEAM, [])

    assert stats["upserted"] == 1
    assert stats["total_home"] == 1
    mock_upsert.assert_called_once()
    mock_statuses.assert_called_once_with("fid-1", "team-1")
    fixture = mock_upsert.call_args[0][0]
    expected = calc_all_deadlines(date.today() + timedelta(days=10), TEAM["deadline_days"], [])
    assert fixture["sales_deadline"] == str(expected["sales_deadline"])
    assert fixture["partner_success_deadline"] == str(expected["partner_success_deadline"])


def test_sync_team_skips_past_match():
    past = str(date.today() - timedelta(days=10))
    matches = [{"game_id": "1", "date": f"{past} 19:00:00", "home_team_id": "tHOME", "away_team_id": "tAWAY", "utc_offset": ""}]

    with patch("opta_sync.get_opta_config", return_value=FAKE_CFG), \
         patch("opta_sync._fetch_and_parse", return_value=(matches, {}, "")), \
         patch("db.upsert_fixture") as mock_upsert:
        stats = sync_team(TEAM, [])

    assert stats["skipped_past"] == 1
    mock_upsert.assert_not_called()


def test_sync_team_prev_season_connection_error_is_ignored():
    future = str(date.today() + timedelta(days=10))
    curr_matches = [{"game_id": "1", "date": f"{future} 19:00:00", "home_team_id": "tHOME", "away_team_id": "tAWAY", "utc_offset": ""}]

    def fetch_side_effect(comp_id, season_id, cfg):
        if season_id == "2025":
            raise ConnectionError("prev season unavailable")
        return curr_matches, {}, "MLS"

    with patch("opta_sync.get_opta_config", return_value=FAKE_CFG), \
         patch("opta_sync._fetch_and_parse", side_effect=fetch_side_effect), \
         patch("db.upsert_fixture", return_value="fid-1"), \
         patch("db.create_upload_statuses_for_fixture"):
        stats = sync_team(TEAM, [])

    assert stats["upserted"] == 1


def test_sync_team_auto_populates_competition_name():
    future = str(date.today() + timedelta(days=10))
    matches = [{"game_id": "1", "date": f"{future} 19:00:00", "home_team_id": "tHOME", "away_team_id": "tAWAY", "utc_offset": ""}]

    with patch("opta_sync.get_opta_config", return_value=FAKE_CFG), \
         patch("opta_sync._fetch_and_parse", return_value=(matches, {}, "MLS")), \
         patch("db.upsert_fixture", return_value="fid-1"), \
         patch("db.create_upload_statuses_for_fixture"), \
         patch("db.update_team_competition") as mock_update_comp:
        sync_team(TEAM, [])

    mock_update_comp.assert_called_once_with("team-1", "MLS")


def test_sync_team_skips_unparseable_date():
    matches = [{"game_id": "1", "date": "not-a-date", "home_team_id": "tHOME", "away_team_id": "tAWAY", "utc_offset": ""}]

    with patch("opta_sync.get_opta_config", return_value=FAKE_CFG), \
         patch("opta_sync._fetch_and_parse", return_value=(matches, {}, "")), \
         patch("db.upsert_fixture") as mock_upsert:
        stats = sync_team(TEAM, [])

    assert stats["skipped_other"] == 1
    mock_upsert.assert_not_called()


# ── sync_all_opta_teams ──────────────────────────────────────────────────────

def test_sync_all_opta_teams_isolates_per_team_errors():
    good_team = {**TEAM, "name": "Good Team"}
    bad_team = {**TEAM, "name": "Bad Team", "feed_team_id": ""}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[good_team, bad_team]), \
         patch("opta_sync.sync_team") as mock_sync:
        def side_effect(team, holidays, weekday_rules=None, overridden_ids=None):
            if team["name"] == "Good Team":
                return {"upserted": 1}
            raise ValueError("No feed_team_id set")
        mock_sync.side_effect = side_effect

        results = sync_all_opta_teams()

    assert results["Good Team"] == {"upserted": 1}
    assert "error" in results["Bad Team"]


def test_sync_all_opta_teams_filters_by_feed_source():
    opta_team = {**TEAM, "feed_source": "opta"}
    other_team = {**TEAM, "name": "Other", "feed_source": "ical"}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[opta_team, other_team]), \
         patch("opta_sync.sync_team", return_value={"upserted": 0}) as mock_sync:
        sync_all_opta_teams()

    assert mock_sync.call_count == 1


def test_sync_team_skips_deadline_fields_for_overridden_fixture():
    future = str(date.today() + timedelta(days=10))
    matches = [{"game_id": "77", "date": f"{future} 19:00:00", "home_team_id": "tHOME", "away_team_id": "tAWAY", "utc_offset": ""}]

    with patch("opta_sync.get_opta_config", return_value=FAKE_CFG), \
         patch("opta_sync._fetch_and_parse", return_value=(matches, {}, "")), \
         patch("db.upsert_fixture", return_value="fid-1") as mock_upsert, \
         patch("db.create_upload_statuses_for_fixture"):
        sync_team(TEAM, [], {}, {"77"})

    fixture = mock_upsert.call_args[0][0]
    assert "approval_deadline" not in fixture
    assert "wc_deadline" not in fixture
    assert "sales_deadline" not in fixture
    assert "partner_success_deadline" not in fixture


def test_sync_all_opta_teams_passes_weekday_map_and_overridden_ids():
    team = {**TEAM}
    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={"team-1": {5: 2}}), \
         patch("db.get_overridden_feed_event_ids", return_value={"evt-x"}), \
         patch("db.get_teams", return_value=[team]), \
         patch("opta_sync.sync_team", return_value={"upserted": 0}) as mock_sync:
        sync_all_opta_teams()

    mock_sync.assert_called_once_with(team, [], {5: 2}, {"evt-x"})
