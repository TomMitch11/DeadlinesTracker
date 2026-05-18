import streamlit as st
import db
from tracker import build_tracker_df, style_tracker_df
from datetime import date

st.set_page_config(page_title="Archive — Deadlines Tracker", layout="wide")
st.title("Archive")
st.caption("Past seasons — read only.")

teams = db.get_teams()
platforms = db.get_platforms()
statuses = db.get_statuses()

seasons = sorted(set(t["season"] for t in teams), reverse=True)
season_options = ["All seasons"] + seasons
chosen_season = st.selectbox("Season", season_options)

team_options = ["All clients"] + [t["name"] for t in teams]
selected_team_name = st.selectbox("Client", team_options)
selected_team_id = None
if selected_team_name != "All clients":
    selected_team_id = next(t["id"] for t in teams if t["name"] == selected_team_name)

cl = db._client()
q = cl.table("fixtures").select(
    "id, team_id, away_team, match_date, approval_deadline, "
    "wc_deadline, sales_deadline, notes, season, source, "
    "teams(id, name), "
    "upload_statuses("
    "  platform_id, status_id, updated_by, updated_at, "
    "  statuses(id, name, label, colour), "
    "  platforms(id, name, display_order)"
    ")"
).lt("match_date", str(date.today()))

if selected_team_id:
    q = q.eq("team_id", selected_team_id)
if chosen_season != "All seasons":
    q = q.eq("season", chosen_season)

fixtures = q.order("match_date", desc=True).execute().data

if not fixtures:
    st.info("No past fixtures for the selected filters.")
else:
    df = build_tracker_df(fixtures, platforms, statuses)
    styled = style_tracker_df(df, platforms, statuses, today=date.today())
    st.dataframe(
        styled.hide(axis="columns", subset=["fixture_id"]),
        use_container_width=True,
        hide_index=True,
    )
