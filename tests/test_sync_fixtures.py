import pytest
from unittest.mock import patch

import sync_fixtures


@pytest.fixture(autouse=True)
def _mock_preflight_config():
    """Prevents run_all_syncs()'s preflight credential checks from reading
    real environment variables during tests -- every test in this file gets
    a clean, always-passing preflight unless it explicitly overrides one of
    these three patches itself (see the dedicated preflight-failure test)."""
    with patch("sync_fixtures.get_db_config"), \
         patch("sync_fixtures.get_opta_config"), \
         patch("sync_fixtures.get_sp_config"):
        yield


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


def test_scrub_credentials_redacts_known_param_names():
    text = "401 Client Error: Unauthorized for url: http://omo.akamai.opta.net/x?USER=bob&PSW=hunter2&other=fine"
    scrubbed = sync_fixtures._scrub_credentials(text)
    assert "hunter2" not in scrubbed
    assert "bob" not in scrubbed
    assert "other=fine" in scrubbed


def test_scrub_credentials_redacts_all_five_param_names_case_insensitively():
    text = (
        "psw=secretpsw&PSW=SECRETPSW&"
        "user=secretuser&USER=SECRETUSER&"
        "api_key=secretapikey&API_KEY=SECRETAPIKEY&"
        "sig=secretsig&SIG=SECRETSIG&"
        "key=secretkey&KEY=SECRETKEY&"
        "safe=untouched"
    )
    scrubbed = sync_fixtures._scrub_credentials(text)
    for secret in (
        "secretpsw", "SECRETPSW",
        "secretuser", "SECRETUSER",
        "secretapikey", "SECRETAPIKEY",
        "secretsig", "SECRETSIG",
        "secretkey", "SECRETKEY",
    ):
        assert secret not in scrubbed
    assert "safe=untouched" in scrubbed


def test_run_all_syncs_scrubs_credentials_from_team_error_before_printing(capsys):
    secret_error = "401 Client Error: Unauthorized for url: http://omo.akamai.opta.net/x?user=bob&psw=hunter2"
    with patch("sync_fixtures.sync_all_ical_teams", return_value={}), \
         patch("sync_fixtures.sync_all_opta_teams", return_value={"Team B": {"error": secret_error}}), \
         patch("sync_fixtures.sync_all_stats_perform_teams", return_value={}), \
         patch("sync_fixtures.sync_all_api_football_teams", return_value={}):
        sync_fixtures.run_all_syncs()
    captured = capsys.readouterr()
    assert "hunter2" not in captured.out
    assert "bob" not in captured.out
    assert "Team B" in captured.out
    assert "psw=[redacted]" in captured.out
    assert "user=[redacted]" in captured.out


def test_run_all_syncs_continues_past_unexpected_exception_and_returns_false():
    with patch("sync_fixtures.sync_all_ical_teams", side_effect=ConnectionError("db blip")) as m_ical, \
         patch("sync_fixtures.sync_all_opta_teams", return_value={"Team B": {"upserted": 1}}) as m_opta, \
         patch("sync_fixtures.sync_all_stats_perform_teams", return_value={"Team C": {"upserted": 1}}) as m_sp, \
         patch("sync_fixtures.sync_all_api_football_teams", return_value={"Team D": {"upserted": 1}}) as m_af:
        result = sync_fixtures.run_all_syncs()
        assert result is False
        m_ical.assert_called_once()
        m_opta.assert_called_once()
        m_sp.assert_called_once()
        m_af.assert_called_once()


def test_run_all_syncs_preflight_missing_credential_stops_before_any_source():
    with patch("sync_fixtures.get_db_config"), \
         patch("sync_fixtures.get_opta_config", side_effect=EnvironmentError("OMO_USERNAME and OMO_PASSWORD must be set")), \
         patch("sync_fixtures.get_sp_config"), \
         patch("sync_fixtures.sync_all_ical_teams") as m_ical, \
         patch("sync_fixtures.sync_all_opta_teams") as m_opta, \
         patch("sync_fixtures.sync_all_stats_perform_teams") as m_sp, \
         patch("sync_fixtures.sync_all_api_football_teams") as m_af:
        with pytest.raises(EnvironmentError):
            sync_fixtures.run_all_syncs()
        m_ical.assert_not_called()
        m_opta.assert_not_called()
        m_sp.assert_not_called()
        m_af.assert_not_called()


def test_run_all_syncs_returns_false_when_zero_teams_synced_with_no_errors():
    # Every source runs cleanly but contributes zero teams (e.g. a wrong
    # Supabase key returning no rows instead of erroring) — must not be
    # reported as a silent success.
    with patch("sync_fixtures.sync_all_ical_teams", return_value={}), \
         patch("sync_fixtures.sync_all_opta_teams", return_value={}), \
         patch("sync_fixtures.sync_all_stats_perform_teams", return_value={}), \
         patch("sync_fixtures.sync_all_api_football_teams", return_value={}):
        assert sync_fixtures.run_all_syncs() is False
