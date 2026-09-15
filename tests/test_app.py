import os
import sys
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

def test_app_has_no_manual_sales_deadline_widget():
    app_source = (Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8")
    assert "Sales deadline" not in app_source
    assert "add_sales" not in app_source
    assert "esales_" not in app_source


# ── Override vs manual-edit-form conflict ──────────────────────────────────
#
# Driving this through the real app.py top-to-bottom flow would require
# AppTest to simulate a st.dataframe row-selection event (the mechanism
# app.py uses to open the detail sidebar). streamlit.testing.v1's Dataframe
# element wrapper only exposes `.value` (the rendered arrow data) — there is
# no supported way to set `event.selection.rows` from a test, and none of
# the existing tests in this suite attempt it. So instead of reimplementing
# that scaffolding, this test imports app.py as a module (mocking just
# enough of `db` for the top-level script to run to completion without
# hitting st.stop()) and then calls the real, unmodified `_show_detail`
# function directly with a crafted fixture — exercising the exact code
# path from the fix via genuine Streamlit widgets (AppTest date_input /
# button interactions), not a source-text reimplementation.

APP_PATH = str(Path(__file__).parent.parent / "app.py")

_FIXTURE_ID = "fx-override-1"

_BASE_FIXTURE = {
    "id": _FIXTURE_ID,
    "team_id": "team-1",
    "away_team": "Wolves",
    "match_date": "2026-06-05",
    "match_time": None,
    "venue": "",
    "notes": "",
    "source": "manual",
    "deadline_override": True,
    "approval_deadline": "2026-05-20",
    "wc_deadline": "2026-05-25",
    "sales_deadline": "2026-05-28",
    "partner_success_deadline": "2026-05-29",
    "upload_statuses": [],
    "teams": {"name": "Chelsea"},
}

_TEAM = {"id": "team-1", "name": "Chelsea", "season": "2025-26", "deadline_days": 3}
_PLATFORMS: list[dict] = []
_STATUSES: list[dict] = []


def _edit_form_script(fixture, platforms, statuses):
    # NOTE: AppTest.from_function only captures this function's own source
    # text (via inspect.getsourcelines) and execs it as a standalone module,
    # so it cannot close over names from the test module — everything it
    # needs must be passed in via `args=` or imported/patched here directly.
    import sys as _sys
    from unittest.mock import patch as _patch
    import streamlit as _st

    with _patch("db.get_teams", return_value=[{"id": "team-1", "name": "Chelsea", "season": "2025-26"}]), \
         _patch("db.get_platforms", return_value=platforms), \
         _patch("db.get_statuses", return_value=statuses), \
         _patch("db.get_upcoming_fixtures", return_value=[fixture]):
        _st.session_state["user_name"] = "Tester"
        _sys.modules.pop("app", None)
        import app as _app_module

    _app_module._show_detail(fixture, platforms, statuses, "Tester")


def _drive_edit_form(fixture: dict, new_date_iso: str):
    """Render `_show_detail` for `fixture`, set a new match date in the edit
    form, click Save changes, and return the args db.update_fixture_manual
    was called with (or None if it wasn't called)."""
    from datetime import date as _date

    captured = {}

    with patch("db.get_delivery_contacts", return_value=[]), \
         patch("db.get_holidays", return_value=[]) as mock_get_holidays, \
         patch("db.get_team", return_value=_TEAM) as mock_get_team, \
         patch("db.get_team_deadline_weekdays", return_value={}) as mock_get_weekdays, \
         patch("db.update_fixture_manual") as mock_update:
        at = AppTest.from_function(
            _edit_form_script, args=(fixture, _PLATFORMS, _STATUSES)
        )
        at.run(timeout=15)
        assert not at.exception

        date_key = f"edate_{fixture['id']}"
        save_key = f"esave_{fixture['id']}"
        at.date_input(key=date_key).set_value(_date.fromisoformat(new_date_iso))
        at.button(key=save_key).click()
        at.run(timeout=15)
        assert not at.exception

        captured["update_call_args"] = mock_update.call_args
        captured["holidays_called"] = mock_get_holidays.called
        captured["team_called"] = mock_get_team.called
        captured["weekdays_called"] = mock_get_weekdays.called

    return captured


def test_edit_fixture_form_preserves_overridden_deadline():
    fixture = dict(_BASE_FIXTURE)
    result = _drive_edit_form(fixture, "2026-06-12")

    assert result["update_call_args"] is not None, "Save changes should have called db.update_fixture_manual"
    args, kwargs = result["update_call_args"]
    # db.update_fixture_manual(fixture_id, away_team, match_date, approval_deadline,
    #                           wc_deadline, sales_deadline, partner_success_deadline, match_time)
    assert args[0] == _FIXTURE_ID
    assert args[2] == "2026-06-12"  # match date edit still applies
    assert args[3] == _BASE_FIXTURE["approval_deadline"]
    assert args[4] == _BASE_FIXTURE["wc_deadline"]
    assert args[5] == _BASE_FIXTURE["sales_deadline"]
    assert args[6] == _BASE_FIXTURE["partner_success_deadline"]

    # The recompute path must not even be consulted when overridden.
    assert result["holidays_called"] is False
    assert result["team_called"] is False
    assert result["weekdays_called"] is False


def test_edit_fixture_form_recomputes_when_not_overridden():
    fixture = dict(_BASE_FIXTURE)
    fixture["deadline_override"] = False
    result = _drive_edit_form(fixture, "2026-06-12")

    assert result["update_call_args"] is not None
    args, kwargs = result["update_call_args"]
    assert args[2] == "2026-06-12"
    # Recompute path was consulted.
    assert result["holidays_called"] is True
    assert result["team_called"] is True
    assert result["weekdays_called"] is True


def test_show_detail_venue_is_collapsed_in_its_own_expander():
    fixture = dict(_BASE_FIXTURE)
    fixture["notes"] = "Existing note text"
    with patch("db.get_delivery_contacts", return_value=[]):
        at = AppTest.from_function(
            _edit_form_script, args=(fixture, _PLATFORMS, _STATUSES)
        )
        at.run(timeout=15)
        assert not at.exception

    venue_expander = next(e for e in at.expander if e.label == "Venue")
    assert venue_expander.proto.expanded is False
    venue_key = f"venue_{fixture['id']}"
    assert venue_expander.text_input(key=venue_key).value == ""


def test_show_detail_notes_rendered_outside_any_expander():
    fixture = dict(_BASE_FIXTURE)
    fixture["notes"] = "Existing note text"
    with patch("db.get_delivery_contacts", return_value=[]):
        at = AppTest.from_function(
            _edit_form_script, args=(fixture, _PLATFORMS, _STATUSES)
        )
        at.run(timeout=15)
        assert not at.exception

    notes_key = f"notes_{fixture['id']}"
    # Notes must still be directly readable/settable at the top level...
    assert at.text_area(key=notes_key).value == "Existing note text"
    # ...and must NOT have ended up nested inside any expander (Venue,
    # Columns, Edit fixture, Admin & Sync) — it should stand on its own,
    # not be tucked away like the de-prioritized controls.
    for e in at.expander:
        assert notes_key not in [w.key for w in e.text_area]


def test_admin_and_sync_controls_are_collapsed_together():
    fixture = dict(_BASE_FIXTURE)
    with patch("db.get_delivery_contacts", return_value=[]):
        at = AppTest.from_function(
            _edit_form_script, args=(fixture, _PLATFORMS, _STATUSES)
        )
        at.run(timeout=15)
        assert not at.exception

    admin_expander = next(e for e in at.expander if e.label == "⚙️ Admin & Sync")
    assert admin_expander.proto.expanded is False
    admin_button_labels = [b.label for b in admin_expander.button]
    assert "➕ Add fixture" in admin_button_labels
    assert "🔄 Sync from iCal" in admin_button_labels
    assert "🔄 Sync from API-Football" in admin_button_labels
    assert "🔄 Sync from Opta" in admin_button_labels
    assert "🔄 Sync from Stats Perform" in admin_button_labels
    # The Columns picker must still live inside this same collapsed section.
    nested_expander_labels = [e2.label for e2 in admin_expander.expander]
    assert "Columns" in nested_expander_labels


def test_teams_filter_label_is_renamed():
    fixture = dict(_BASE_FIXTURE)
    with patch("db.get_delivery_contacts", return_value=[]):
        at = AppTest.from_function(
            _edit_form_script, args=(fixture, _PLATFORMS, _STATUSES)
        )
        at.run(timeout=15)
        assert not at.exception

    multiselect_labels = [m.label for m in at.multiselect]
    assert "Teams (leave blank for all)" in multiselect_labels
