from unittest.mock import patch

import sync_fixtures


def test_run_all_syncs_returns_true_when_all_clean():
    with patch("sync_fixtures.sync_all_ical_teams", return_value={"Team A": {"upserted": 1}}), \
         patch("sync_fixtures.sync_all_opta_teams", return_value={"Team B": {"upserted": 2}}), \
         patch("sync_fixtures.sync_all_stats_perform_teams", return_value={}), \
         patch("sync_fixtures.sync_all_api_football_teams", return_value={}):
        assert sync_fixtures.run_all_syncs() is True


def test_run_all_syncs_returns_false_when_any_team_errors():
    with patch("sync_fixtures.sync_all_ical_teams", return_value={"Team A": {"upserted": 1}}), \
         patch("sync_fixtures.sync_all_opta_teams", return_value={"Team B": {"error": "Opta network error: timeout"}}), \
         patch("sync_fixtures.sync_all_stats_perform_teams", return_value={}), \
         patch("sync_fixtures.sync_all_api_football_teams", return_value={}):
        assert sync_fixtures.run_all_syncs() is False


def test_run_all_syncs_calls_every_source_even_when_an_earlier_one_errors():
    with patch("sync_fixtures.sync_all_ical_teams", return_value={"Team A": {"error": "boom"}}) as m_ical, \
         patch("sync_fixtures.sync_all_opta_teams", return_value={}) as m_opta, \
         patch("sync_fixtures.sync_all_stats_perform_teams", return_value={}) as m_sp, \
         patch("sync_fixtures.sync_all_api_football_teams", return_value={}) as m_af:
        sync_fixtures.run_all_syncs()
        m_ical.assert_called_once()
        m_opta.assert_called_once()
        m_sp.assert_called_once()
        m_af.assert_called_once()


def test_run_all_syncs_handles_source_with_no_configured_teams():
    with patch("sync_fixtures.sync_all_ical_teams", return_value={}), \
         patch("sync_fixtures.sync_all_opta_teams", return_value={}), \
         patch("sync_fixtures.sync_all_stats_perform_teams", return_value={}), \
         patch("sync_fixtures.sync_all_api_football_teams", return_value={}):
        assert sync_fixtures.run_all_syncs() is True
