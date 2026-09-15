import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import db

st.set_page_config(page_title="Partner Success — Deadlines", layout="wide")
st.title("Partner Success deadlines")


def _fmt_date(date_str):
    if not date_str:
        return ""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %d %b")


try:
    fixtures = db.get_partner_success_fixtures(days=14)
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
            "Partner Success Deadline": _fmt_date(f["partner_success_deadline"]),
            "Platforms Needed": ", ".join(f["platform_names"]) if f["platform_names"] else "",
        }
        for f in fixtures
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)
