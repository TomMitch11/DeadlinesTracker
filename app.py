import streamlit as st
import db
from tracker import build_tracker_df, style_tracker_df

st.set_page_config(page_title="Deadlines Tracker", layout="wide")

# ── Helper functions ──────────────────────────────────────────────────────────

def _show_detail(
    fixture: dict,
    platforms: list[dict],
    statuses: list[dict],
    user_name: str,
) -> None:
    with st.sidebar:
        team_name = fixture["teams"]["name"]
        st.subheader(f"{team_name} vs {fixture['away_team']}")
        st.caption(f"Match date: {fixture['match_date']}")

        notes = st.text_area(
            "Notes",
            value=fixture.get("notes", ""),
            key=f"notes_{fixture['id']}",
            height=120,
        )
        if st.button("Save notes", key=f"save_notes_{fixture['id']}"):
            db.update_fixture_notes(fixture["id"], notes)
            st.cache_data.clear()
            st.success("Notes saved.")

        st.divider()

        st.markdown("**Upload statuses**")
        status_map = {us["platform_id"]: us for us in fixture.get("upload_statuses", [])}
        status_options = {s["label"]: s["id"] for s in statuses}
        contacts = {
            dc["platform_id"]: dc["contact_info"]
            for dc in db.get_delivery_contacts(fixture["team_id"])
        }

        for p in sorted(platforms, key=lambda x: x["display_order"]):
            us = status_map.get(p["id"])
            if us is None:
                continue
            current_label = us["statuses"]["label"]
            col1, col2 = st.columns([2, 1])
            with col1:
                new_label = st.selectbox(
                    p["name"],
                    list(status_options.keys()),
                    index=list(status_options.keys()).index(current_label),
                    key=f"status_{fixture['id']}_{p['id']}",
                )
                if contacts.get(p["id"]):
                    st.caption(f"📬 {contacts[p['id']]}")
            with col2:
                st.caption(f"Updated by: {us.get('updated_by', '—')}")
                if new_label != current_label:
                    if st.button("Save", key=f"save_{fixture['id']}_{p['id']}"):
                        db.update_upload_status(
                            fixture["id"], p["id"], status_options[new_label], user_name
                        )
                        st.cache_data.clear()
                        st.rerun()

        if fixture.get("source") == "manual":
            st.divider()
            with st.expander("✏️ Edit fixture"):
                from datetime import date as _date
                from deadline_calc import calc_approval_deadline, calc_wc_deadline
                new_away = st.text_input("Away team", value=fixture["away_team"], key=f"eaway_{fixture['id']}")
                new_date = st.date_input("Match date", value=_date.fromisoformat(fixture["match_date"]), key=f"edate_{fixture['id']}")
                new_sales = st.date_input(
                    "Sales deadline (optional)",
                    value=_date.fromisoformat(fixture["sales_deadline"]) if fixture.get("sales_deadline") else None,
                    key=f"esales_{fixture['id']}",
                )
                holidays_raw = db.get_holidays()
                holidays = [_date.fromisoformat(h["date"]) for h in holidays_raw]
                team_data = db.get_team(fixture["team_id"])
                new_approval = calc_approval_deadline(new_date, team_data["deadline_days"], holidays)
                new_wc = calc_wc_deadline(new_approval)
                st.caption(f"Approval deadline: **{new_approval}** | WC deadline: **{new_wc}**")
                if st.button("Save changes", key=f"esave_{fixture['id']}"):
                    db.update_fixture_manual(
                        fixture["id"], new_away.strip(), str(new_date),
                        str(new_approval), str(new_wc),
                        str(new_sales) if new_sales else None,
                    )
                    st.cache_data.clear()
                    st.rerun()


def _show_add_form(teams: list[dict], platforms: list[dict], statuses: list[dict]) -> None:
    from datetime import date as _date
    from deadline_calc import calc_approval_deadline, calc_wc_deadline
    import db as _db

    with st.sidebar:
        st.subheader("Add fixture")
        team_names = [t["name"] for t in teams]
        chosen_team_name = st.selectbox("Home team (client)", team_names, key="add_team")
        team = next(t for t in teams if t["name"] == chosen_team_name)
        away = st.text_input("Away team", key="add_away")
        match_date = st.date_input("Match date", min_value=_date.today(), key="add_date")
        sales_deadline = st.date_input(
            "Sales deadline (optional)", value=None, key="add_sales"
        )

        holidays_raw = _db.get_holidays()
        holidays = [_date.fromisoformat(h["date"]) for h in holidays_raw]
        approval = calc_approval_deadline(match_date, team["deadline_days"], holidays)
        wc = calc_wc_deadline(approval)
        st.caption(f"Approval deadline: **{approval}** | WC deadline: **{wc}**")

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("Save", key="add_save") and away.strip():
                fixture = {
                    "team_id": team["id"],
                    "away_team": away.strip(),
                    "match_date": str(match_date),
                    "approval_deadline": str(approval),
                    "wc_deadline": str(wc),
                    "sales_deadline": str(sales_deadline) if sales_deadline else None,
                    "season": team["season"],
                    "source": "manual",
                }
                fid = _db.upsert_fixture(fixture)
                _db.create_upload_statuses_for_fixture(fid, team["id"])
                st.cache_data.clear()
                st.session_state.show_add_form = False
                st.success("Fixture added.")
                st.rerun()
        with col_cancel:
            if st.button("Cancel", key="add_cancel"):
                st.session_state.show_add_form = False
                st.rerun()


# ── Name prompt (persists for the browser session) ────────────────────────────
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "show_add_form" not in st.session_state:
    st.session_state.show_add_form = False

if st.session_state.user_name is None:
    st.title("Deadlines Tracker")
    name = st.text_input("Your name (shown when you update a status):")
    if st.button("Continue") and name.strip():
        st.session_state.user_name = name.strip()
        st.rerun()
    st.stop()

# ── Load reference data ───────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_teams():
    return db.get_teams()

@st.cache_data(ttl=60)
def load_platforms():
    return db.get_platforms()

@st.cache_data(ttl=60)
def load_statuses():
    return db.get_statuses()

teams = load_teams()
platforms = load_platforms()
statuses = load_statuses()
platform_names = [p["name"] for p in platforms]

# ── Filters ───────────────────────────────────────────────────────────────────
st.title("Deadlines Tracker")
col_name, col_days = st.columns([3, 1])
with col_name:
    team_options = ["All clients"] + [t["name"] for t in teams]
    selected_team_name = st.selectbox("Client", team_options)
with col_days:
    days_options = {"Next 7 days": 7, "Next 14 days": 14, "Next 30 days": 30, "All upcoming": None}
    selected_label = st.selectbox("Time window", list(days_options.keys()), index=1)

selected_team_id = None
if selected_team_name != "All clients":
    selected_team_id = next(t["id"] for t in teams if t["name"] == selected_team_name)

days = days_options[selected_label]

# ── Add fixture button ────────────────────────────────────────────────────────
with st.sidebar:
    if st.button("➕ Add fixture", use_container_width=True):
        st.session_state.show_add_form = True

# ── Load fixtures ─────────────────────────────────────────────────────────────
fixtures = db.get_upcoming_fixtures(days=days, team_id=selected_team_id)

if not fixtures:
    st.info("No upcoming fixtures for the selected filters.")
    st.stop()

df = build_tracker_df(fixtures, platforms, statuses)
styled = style_tracker_df(df, platforms, statuses)

# ── Tracker table ─────────────────────────────────────────────────────────────
st.caption(f"Showing {len(fixtures)} fixture(s). Click a row to view details and update statuses.")

event = st.dataframe(
    styled.hide(axis="columns", subset=["fixture_id"]),
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ── Detail panel ──────────────────────────────────────────────────────────────
if event.selection and event.selection.rows:
    idx = event.selection.rows[0]
    selected = fixtures[idx]
    _show_detail(selected, platforms, statuses, st.session_state.user_name)

# ── Add fixture form ──────────────────────────────────────────────────────────
if st.session_state.get("show_add_form"):
    _show_add_form(teams, platforms, statuses)
