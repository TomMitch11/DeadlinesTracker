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
    db.get_upcoming_fixtures(days=14, team_id="team-abc", client=client)
    chain.eq.assert_called_with("team_id", "team-abc")

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
