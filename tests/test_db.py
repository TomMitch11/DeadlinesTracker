from datetime import date, timedelta

import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_sb():
    """Returns (client_mock, chain_mock). chain_mock.execute.return_value.data controls results."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.upsert.return_value = chain
    chain.delete.return_value = chain
    chain.eq.return_value = chain
    chain.neq.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.gt.return_value = chain
    chain.order.return_value = chain
    chain.limit.return_value = chain
    chain.single.return_value = chain
    chain.execute.return_value = MagicMock(data=[])
    client = MagicMock()
    client.table.return_value = chain
    return client, chain

import db

def test_get_teams_returns_data(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[{"id": "abc", "name": "LA Galaxy"}])
    result = db.get_teams(client=client)
    assert result == [{"id": "abc", "name": "LA Galaxy"}]
    client.table.assert_called_with("teams")

def test_get_team_platforms_extracts_ids(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[{"platform_id": "p1"}, {"platform_id": "p2"}])
    result = db.get_team_platforms("team-123", client=client)
    assert result == ["p1", "p2"]

def test_get_upcoming_fixtures_no_team_filter(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[{"id": "f1", "match_date": "2026-06-01"}])
    result = db.get_upcoming_fixtures(days=7, client=client)
    assert len(result) == 1
    assert result[0]["id"] == "f1"

def test_get_upcoming_fixtures_with_team_filter(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.get_upcoming_fixtures(days=14, team_ids=["team-abc"], client=client)
    chain.in_.assert_called_with("team_id", ["team-abc"])

def test_get_upcoming_fixtures_selects_deadline_override_and_partner_success_deadline(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.get_upcoming_fixtures(client=client)
    select_call = chain.select.call_args_list[0]
    selected = select_call.args[0]
    assert "deadline_override" in selected
    assert "partner_success_deadline" in selected

def test_get_upcoming_fixtures_windows_by_approval_deadline_not_match_date(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.get_upcoming_fixtures(days=7, client=client)
    cutoff = str(date.today() + timedelta(days=7))
    chain.lte.assert_called_with("approval_deadline", cutoff)

def test_get_upcoming_fixtures_wc_deadline_overrides_days_window(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.get_upcoming_fixtures(days=7, wc_deadline="2026-09-22", client=client)
    chain.eq.assert_called_with("wc_deadline", "2026-09-22")
    chain.lte.assert_not_called()

def test_get_upcoming_wc_deadlines_returns_sorted_distinct(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"wc_deadline": "2026-09-22"},
        {"wc_deadline": "2026-09-15"},
        {"wc_deadline": "2026-09-22"},
        {"wc_deadline": None},
    ])
    result = db.get_upcoming_wc_deadlines(client=client)
    assert result == ["2026-09-15", "2026-09-22"]

def test_get_statuses_returns_list(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"id": "s1", "name": "pending", "label": "Pending", "colour": "#e74c3c"},
        {"id": "s2", "name": "uploaded", "label": "Uploaded", "colour": "#27ae60"},
    ])
    result = db.get_statuses(client=client)
    assert len(result) == 2
    assert result[0]["name"] == "pending"

def test_get_holidays_returns_sorted(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[{"date": "2026-12-25", "description": "Christmas"}])
    result = db.get_holidays(client=client)
    assert result[0]["date"] == "2026-12-25"

def test_upsert_fixture_feed_uses_on_conflict(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[{"id": "new-id"}])
    fixture = {"feed_event_id": "evt123", "match_date": "2026-06-01", "team_id": "t1", "away_team": "Portland"}
    result = db.upsert_fixture(fixture, client=client)
    assert result == "new-id"
    chain.upsert.assert_called_once()

def test_upsert_fixture_manual_uses_insert(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[{"id": "manual-id"}])
    fixture = {"match_date": "2026-06-01", "team_id": "t1", "away_team": "Portland"}
    result = db.upsert_fixture(fixture, client=client)
    assert result == "manual-id"
    chain.insert.assert_called_once()

def test_update_upload_status_calls_update(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.update_upload_status("fix-1", "plat-1", "stat-1", "Alice", client=client)
    chain.update.assert_called_once()

def test_set_team_platforms_deletes_then_inserts(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.set_team_platforms("team-1", ["p1", "p2"], client=client)
    chain.delete.assert_called_once()
    chain.insert.assert_called_once()

def test_delete_platform_raises_if_in_use(mock_sb):
    import pytest
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[{"fixture_id": "f1"}])
    with pytest.raises(ValueError, match="in use"):
        db.delete_platform("plat-1", client=client)

def test_delete_status_raises_if_system(mock_sb):
    import pytest
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data={"is_system": True})
    with pytest.raises(ValueError, match="system"):
        db.delete_status("stat-1", client=client)

def test_update_fixture_manual_includes_partner_success_deadline(mock_sb):
    client, chain = mock_sb
    db.update_fixture_manual(
        "fixture-1", "Chelsea", "2026-06-05",
        "2026-06-02", "2026-06-01", "2026-05-29", "2026-06-01",
        client=client,
    )
    payload = chain.update.call_args[0][0]
    assert payload["sales_deadline"] == "2026-05-29"
    assert payload["partner_success_deadline"] == "2026-06-01"

def test_recalculate_future_deadlines_writes_all_four_fields(mock_sb):
    client, chain = mock_sb
    chain.execute.side_effect = [
        MagicMock(data=[]),  # get_holidays
        MagicMock(data=[{"id": "t1", "name": "Chelsea", "deadline_days": 3, "deadline_active": True, "season": "2026"}]),  # get_teams
        MagicMock(data=[]),  # get_deadline_weekdays_by_team
        MagicMock(data=[{"id": "f1", "team_id": "t1", "match_date": "2026-06-05", "deadline_override": False}]),  # future fixtures
        MagicMock(data=[]),  # the .update().execute() call
    ]
    db.recalculate_future_deadlines(client=client)
    update_payload = chain.update.call_args[0][0]
    assert update_payload["sales_deadline"] == "2026-05-29"
    assert update_payload["partner_success_deadline"] == "2026-06-01"

def test_get_sales_fixtures_selects_only_safe_columns(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.get_sales_fixtures(days=14, client=client)
    select_call = chain.select.call_args_list[0]
    selected = select_call.args[0]
    assert "approval_deadline" not in selected
    assert "wc_deadline" not in selected
    assert "sales_deadline" in selected

def test_get_sales_fixtures_returns_data(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"id": "f1", "away_team": "Wolves", "match_date": "2026-06-05",
         "sales_deadline": "2026-06-01", "teams": {"name": "Chelsea"}},
    ])
    result = db.get_sales_fixtures(client=client)
    assert result[0]["away_team"] == "Wolves"

def test_get_partner_success_fixtures_selects_only_safe_columns(mock_sb, monkeypatch):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    monkeypatch.setattr(db, "get_platforms", lambda client=None: [])
    monkeypatch.setattr(db, "get_team_platforms", lambda team_id, client=None: [])
    db.get_partner_success_fixtures(days=14, client=client)
    select_call = chain.select.call_args_list[0]
    selected = select_call.args[0]
    assert "approval_deadline" not in selected
    assert "wc_deadline" not in selected
    assert "partner_success_deadline" in selected

def test_get_partner_success_fixtures_attaches_platform_names(mock_sb, monkeypatch):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"id": "f1", "away_team": "Wolves", "match_date": "2026-06-05",
         "partner_success_deadline": "2026-06-04", "team_id": "t1", "teams": {"name": "Chelsea"}},
    ])
    monkeypatch.setattr(db, "get_platforms", lambda client=None: [
        {"id": "p1", "name": "Big Screen"}, {"id": "p2", "name": "Programme Page"},
    ])
    monkeypatch.setattr(db, "get_team_platforms", lambda team_id, client=None: ["p1"])
    result = db.get_partner_success_fixtures(client=client)
    assert result[0]["platform_names"] == ["Big Screen"]

def test_get_deadline_weekdays_by_team_groups_by_team(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"team_id": "t1", "match_weekday": 5, "deadline_weekday": 2},
        {"team_id": "t1", "match_weekday": 1, "deadline_weekday": 3},
        {"team_id": "t2", "match_weekday": 0, "deadline_weekday": 2},
    ])
    result = db.get_deadline_weekdays_by_team(client=client)
    assert result == {"t1": {5: 2, 1: 3}, "t2": {0: 2}}

def test_get_team_deadline_weekdays_returns_map_for_one_team(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[{"match_weekday": 5, "deadline_weekday": 2}])
    result = db.get_team_deadline_weekdays("t1", client=client)
    assert result == {5: 2}

def test_set_team_deadline_weekdays_deletes_then_inserts(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.set_team_deadline_weekdays("t1", {5: 2, 1: 3}, client=client)
    chain.delete.assert_called_once()
    inserted = chain.insert.call_args[0][0]
    assert {"team_id": "t1", "match_weekday": 5, "deadline_weekday": 2} in inserted
    assert {"team_id": "t1", "match_weekday": 1, "deadline_weekday": 3} in inserted

def test_set_team_deadline_weekdays_empty_rules_skips_insert(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.set_team_deadline_weekdays("t1", {}, client=client)
    chain.delete.assert_called_once()
    chain.insert.assert_not_called()

def test_set_team_deadline_active_updates_flag(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.set_team_deadline_active("t1", False, client=client)
    payload = chain.update.call_args[0][0]
    assert payload == {"deadline_active": False}

def test_get_overridden_feed_event_ids_filters_null(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"feed_event_id": "evt1"}, {"feed_event_id": None},
    ])
    result = db.get_overridden_feed_event_ids(client=client)
    assert result == {"evt1"}

def test_set_fixture_deadline_override_writes_derived_fields(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.set_fixture_deadline_override("fix-1", date(2026, 6, 3), client=client)
    payload = chain.update.call_args[0][0]
    assert payload["approval_deadline"] == "2026-06-03"
    assert payload["wc_deadline"] == "2026-06-01"
    assert payload["sales_deadline"] == "2026-05-30"
    assert payload["partner_success_deadline"] == "2026-06-02"
    assert payload["deadline_override"] is True

def test_clear_fixture_deadline_override_recomputes_and_clears_flag(mock_sb):
    client, chain = mock_sb
    chain.execute.side_effect = [
        MagicMock(data={"id": "fix-1", "team_id": "t1", "match_date": "2026-06-05"}),  # fixture select
        MagicMock(data={"id": "t1", "deadline_days": 3, "deadline_active": True}),  # get_team
        MagicMock(data=[]),  # get_team_deadline_weekdays
        MagicMock(data=[]),  # get_holidays
        MagicMock(data=[]),  # the update
    ]
    db.clear_fixture_deadline_override("fix-1", client=client)
    payload = chain.update.call_args[0][0]
    assert payload["deadline_override"] is False
    # Friday 2026-06-05, flat 3-day fallback (no weekday rule configured) -> 2026-06-02
    assert payload["approval_deadline"] == "2026-06-02"

def test_recalculate_future_deadlines_skips_overridden_fixtures(mock_sb):
    client, chain = mock_sb
    chain.execute.side_effect = [
        MagicMock(data=[]),  # get_holidays
        MagicMock(data=[{"id": "t1", "name": "Chelsea", "deadline_days": 3, "deadline_active": True, "season": "2026"}]),  # get_teams
        MagicMock(data=[]),  # get_deadline_weekdays_by_team
        MagicMock(data=[{"id": "f1", "team_id": "t1", "match_date": "2026-06-05", "deadline_override": True}]),  # future fixtures
    ]
    count = db.recalculate_future_deadlines(client=client)
    assert count == 0
    chain.update.assert_not_called()

def test_recalculate_future_deadlines_inactive_team_writes_none(mock_sb):
    client, chain = mock_sb
    chain.execute.side_effect = [
        MagicMock(data=[]),  # get_holidays
        MagicMock(data=[{"id": "t1", "name": "Chelsea", "deadline_days": 3, "deadline_active": False, "season": "2026"}]),  # get_teams
        MagicMock(data=[]),  # get_deadline_weekdays_by_team
        MagicMock(data=[{"id": "f1", "team_id": "t1", "match_date": "2026-06-05", "deadline_override": False}]),  # future fixtures
        MagicMock(data=[]),  # update
    ]
    db.recalculate_future_deadlines(client=client)
    update_payload = chain.update.call_args[0][0]
    assert update_payload["approval_deadline"] is None
    assert update_payload["wc_deadline"] is None
    assert update_payload["sales_deadline"] is None
    assert update_payload["partner_success_deadline"] is None
