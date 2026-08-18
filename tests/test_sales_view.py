import os
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

def test_sales_view_shows_only_team_date_and_sales_deadline():
    fake_fixtures = [
        {"id": "f1", "away_team": "Wolves", "match_date": "2026-06-05",
         "sales_deadline": "2026-06-01", "teams": {"name": "Chelsea"}},
    ]
    with patch("db.get_sales_fixtures", return_value=fake_fixtures):
        sales_view_path = os.path.join(os.path.dirname(__file__), "..", "views", "sales_view.py")
        at = AppTest.from_file(sales_view_path)
        at.run()
    assert not at.exception
    page_text = " ".join(m.value for m in at.markdown) + " ".join(t.value for t in at.text) + " ".join(str(d.value) for d in at.dataframe)
    assert "Chelsea" in page_text
    assert "Wolves" in page_text
    assert "2026-06-01" in page_text

def test_sales_view_handles_zero_fixtures():
    with patch("db.get_sales_fixtures", return_value=[]):
        sales_view_path = os.path.join(os.path.dirname(__file__), "..", "views", "sales_view.py")
        at = AppTest.from_file(sales_view_path)
        at.run()
    assert not at.exception
