import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import db

st.set_page_config(page_title="Sales — Deadlines", layout="wide")
st.title("Sales deadlines")


def _fmt_date(date_str):
    if not date_str:
        return ""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %d %b")


try:
    fixtures = db.get_sales_fixtures(days=14)
except Exception as e:
    st.error(f"Could not load fixtures: {e}")
    st.stop()

if not fixtures:
    st.info("No upcoming fixtures in the next 14 days.")
else:
    rows = [
        {
            "Team": f["teams"]["name"],
            "Away Team": f["away_team"],
            "Match Date": _fmt_date(f["match_date"]),
            "Sales Deadline": _fmt_date(f["sales_deadline"]),
        }
        for f in fixtures
    ]
    row_height = 35
    header_height = 38
    table_height = header_height + row_height * min(len(rows), 15)
    st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
        height=table_height,
        row_height=row_height,
    )
