import os
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

def test_partner_success_view_shows_fixture_and_platforms():
    fake_fixtures = [
        {"id": "f1", "away_team": "Wolves", "match_date": "2026-06-05",
         "partner_success_deadline": "2026-06-04", "teams": {"name": "Chelsea"},
         "platform_names": ["Big Screen", "Programme Page"]},
    ]
    with patch("db.get_partner_success_fixtures", return_value=fake_fixtures):
        partner_success_view_path = os.path.join(os.path.dirname(__file__), "..", "views", "partner_success_view.py")
        at = AppTest.from_file(partner_success_view_path)
        at.run()
    assert not at.exception
    page_text = " ".join(m.value for m in at.markdown) + " ".join(t.value for t in at.text) + " ".join(str(d.value) for d in at.dataframe)
    assert "Chelsea" in page_text
    assert "2026-06-04" in page_text
    assert "Big Screen" in page_text
    assert "Programme Page" in page_text

def test_partner_success_view_handles_zero_fixtures():
    with patch("db.get_partner_success_fixtures", return_value=[]):
        partner_success_view_path = os.path.join(os.path.dirname(__file__), "..", "views", "partner_success_view.py")
        at = AppTest.from_file(partner_success_view_path)
        at.run()
    assert not at.exception
