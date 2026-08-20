from datetime import date
from _import_gospel_deadlines import match_gospel_rows


def test_match_gospel_rows_matches_by_resolved_team_name_and_date():
    gospel_rows = [
        (date(2026, 8, 22), "London Stadium", "Arsenal", date(2026, 8, 14)),
    ]
    app_fixtures = [
        {"id": "fix-1", "team_id": "t1", "match_date": "2026-08-22"},
    ]
    teams_by_id = {"t1": "West Ham"}
    result = match_gospel_rows(gospel_rows, app_fixtures, teams_by_id)
    assert result == [("fix-1", date(2026, 8, 14))]


def test_match_gospel_rows_skips_when_no_fixture_matches_date():
    gospel_rows = [
        (date(2026, 8, 22), "Aston Villa", "Arsenal", date(2026, 8, 19)),
    ]
    app_fixtures = [
        {"id": "fix-1", "team_id": "t1", "match_date": "2026-08-29"},
    ]
    teams_by_id = {"t1": "Aston Villa"}
    result = match_gospel_rows(gospel_rows, app_fixtures, teams_by_id)
    assert result == []


def test_match_gospel_rows_skips_when_team_not_in_app():
    gospel_rows = [
        (date(2026, 8, 22), "Some Untracked Team", "Arsenal", date(2026, 8, 19)),
    ]
    app_fixtures = [
        {"id": "fix-1", "team_id": "t1", "match_date": "2026-08-22"},
    ]
    teams_by_id = {"t1": "Aston Villa"}
    result = match_gospel_rows(gospel_rows, app_fixtures, teams_by_id)
    assert result == []


def test_match_gospel_rows_skips_row_with_no_approval_deadline():
    gospel_rows = [
        (date(2026, 8, 22), "Aston Villa", "Arsenal", None),
    ]
    app_fixtures = [
        {"id": "fix-1", "team_id": "t1", "match_date": "2026-08-22"},
    ]
    teams_by_id = {"t1": "Aston Villa"}
    result = match_gospel_rows(gospel_rows, app_fixtures, teams_by_id)
    assert result == []
