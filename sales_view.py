import streamlit as st
import db

st.set_page_config(page_title="Sales — Deadlines", layout="wide")
st.title("Sales deadlines")

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
            "Match Date": f["match_date"],
            "Sales Deadline": f["sales_deadline"] or "",
        }
        for f in fixtures
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)
