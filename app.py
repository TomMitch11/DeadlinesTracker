from datetime import date as _date

import streamlit as st
import db
from tracker import build_excel_export, build_tracker_df, style_tracker_df

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

        venue = st.text_input(
            "Venue",
            value=fixture.get("venue") or "",
            key=f"venue_{fixture['id']}",
        )
        if st.button("Save venue", key=f"save_venue_{fixture['id']}"):
            db.update_fixture_venue(fixture["id"], venue.strip() or None)
            st.cache_data.clear()
            st.rerun()

        st.divider()

        notes = st.text_area(
            "Notes",
            value=fixture.get("notes", ""),
            key=f"notes_{fixture['id']}",
            height=120,
        )
        if st.button("Save notes", key=f"save_notes_{fixture['id']}"):
            db.update_fixture_notes(fixture["id"], notes)
            st.cache_data.clear()
            st.rerun()

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
                status_keys = list(status_options.keys())
                current_idx = status_keys.index(current_label) if current_label in status_keys else 0
                new_label = st.selectbox(
                    p["name"],
                    status_keys,
                    index=current_idx,
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
                from deadline_calc import calc_all_deadlines
                new_away = st.text_input("Away team", value=fixture["away_team"], key=f"eaway_{fixture['id']}")
                new_date = st.date_input("Match date", value=_date.fromisoformat(fixture["match_date"]), key=f"edate_{fixture['id']}")
                existing_time = fixture.get("match_time") or ""
                new_time_str = st.text_input(
                    "Kickoff time, UTC (HH:MM, leave blank if unknown)",
                    value=existing_time,
                    key=f"etime_{fixture['id']}",
                )
                holidays_raw = db.get_holidays()
                holidays = [_date.fromisoformat(h["date"]) for h in holidays_raw]
                team_data = db.get_team(fixture["team_id"])
                new_deadlines = calc_all_deadlines(new_date, team_data["deadline_days"], holidays)
                st.caption(
                    f"Approval deadline: **{new_deadlines['approval_deadline']}** | "
                    f"WC deadline: **{new_deadlines['wc_deadline']}**"
                )
                if st.button("Save changes", key=f"esave_{fixture['id']}"):
                    import re
                    clean_time = new_time_str.strip()
                    match_time = clean_time if re.match(r"^\d{2}:\d{2}$", clean_time) else None
                    db.update_fixture_manual(
                        fixture["id"], new_away.strip(), str(new_date),
                        str(new_deadlines["approval_deadline"]), str(new_deadlines["wc_deadline"]),
                        str(new_deadlines["sales_deadline"]), str(new_deadlines["partner_success_deadline"]),
                        match_time,
                    )
                    st.cache_data.clear()
                    st.rerun()


def _show_add_form(teams: list[dict], platforms: list[dict], statuses: list[dict]) -> None:
    from datetime import date as _date
    from deadline_calc import calc_all_deadlines
    import db as _db

    with st.sidebar:
        st.subheader("Add fixture")
        team_names = [t["name"] for t in teams]
        chosen_team_name = st.selectbox("Home team (client)", team_names, key="add_team")
        team = next((t for t in teams if t["name"] == chosen_team_name), None)
        if team is None:
            st.error("Selected team not found.")
            return
        away = st.text_input("Away team", key="add_away")
        match_date = st.date_input("Match date", min_value=_date.today(), key="add_date")
        match_time_str = st.text_input(
            "Kickoff time, UTC (HH:MM, leave blank if unknown)", key="add_time"
        )

        holidays_raw = _db.get_holidays()
        holidays = [_date.fromisoformat(h["date"]) for h in holidays_raw]
        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)
        st.caption(
            f"Approval deadline: **{deadlines['approval_deadline']}** | "
            f"WC deadline: **{deadlines['wc_deadline']}**"
        )

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("Save", key="add_save") and away.strip():
                import re as _re
                _t = match_time_str.strip()
                _match_time = _t if _re.match(r"^\d{2}:\d{2}$", _t) else None
                fixture = {
                    "team_id": team["id"],
                    "away_team": away.strip(),
                    "match_date": str(match_date),
                    "match_time": _match_time,
                    "approval_deadline": str(deadlines["approval_deadline"]),
                    "wc_deadline": str(deadlines["wc_deadline"]),
                    "sales_deadline": str(deadlines["sales_deadline"]),
                    "partner_success_deadline": str(deadlines["partner_success_deadline"]),
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
col_comp, col_name, col_days = st.columns([2, 3, 1])
with col_comp:
    competition_options = sorted({t["competition"] for t in teams if t.get("competition")})
    selected_competitions = st.multiselect("Competition (leave blank for all)", competition_options)
with col_name:
    team_options = [
        t["name"] for t in teams
        if not selected_competitions or t.get("competition") in selected_competitions
    ]
    selected_team_names = st.multiselect("Clients (leave blank for all)", team_options)
with col_days:
    days_options = {"Next 7 days": 7, "Next 14 days": 14, "Next 30 days": 30, "All upcoming": None}
    selected_label = st.selectbox("Time window", list(days_options.keys()), index=1)

# Resolve team IDs: competition filter narrows the pool, team filter narrows further
filtered_teams = [
    t for t in teams
    if (not selected_competitions or t.get("competition") in selected_competitions)
    and (not selected_team_names or t["name"] in selected_team_names)
]
selected_team_ids = [t["id"] for t in filtered_teams] if (selected_competitions or selected_team_names) else None
days = days_options[selected_label]

# ── Sidebar controls ─────────────────────────────────────────────────────────
with st.sidebar:
    if st.button("➕ Add fixture", use_container_width=True):
        st.session_state.show_add_form = True

    if st.button("🔄 Sync from iCal", use_container_width=True):
        from ical_sync import sync_all_ical_teams
        try:
            with st.spinner("Syncing..."):
                results = sync_all_ical_teams()
            if not results:
                st.info("No teams configured with iCal feed source.")
            else:
                any_new = False
                for team_name, s in results.items():
                    if "error" in s:
                        st.error(f"{team_name}: {s['error']}")
                    elif s["upserted"] > 0:
                        st.success(f"{team_name}: {s['upserted']} fixture(s) added/updated.")
                        any_new = True
                    else:
                        st.info(f"{team_name}: nothing new ({s['total_home']} home match(es) found).")
                if any_new:
                    st.cache_data.clear()
                    st.rerun()
        except EnvironmentError as e:
            st.error(str(e))
        except (ConnectionError, PermissionError, ValueError) as e:
            st.error(str(e))

    if st.button("🔄 Sync from API-Football", use_container_width=True):
        from api_football_sync import sync_all_api_football_teams
        try:
            with st.spinner("Syncing..."):
                results = sync_all_api_football_teams()
            if not results:
                st.info("No teams configured with API-Football feed source.")
            else:
                any_new = False
                for team_name, s in results.items():
                    if "error" in s:
                        st.error(f"{team_name}: {s['error']}")
                    elif s["upserted"] > 0:
                        st.success(f"{team_name}: {s['upserted']} fixture(s) added/updated.")
                        any_new = True
                    else:
                        st.info(f"{team_name}: nothing new ({s['total_home']} home match(es) found).")
                if any_new:
                    st.cache_data.clear()
                    st.rerun()
        except EnvironmentError as e:
            st.error(str(e))
        except (ConnectionError, PermissionError, ValueError) as e:
            st.error(str(e))

    if st.button("🔄 Sync from Opta", use_container_width=True):
        from opta_sync import sync_all_opta_teams
        try:
            with st.spinner("Syncing..."):
                results = sync_all_opta_teams()
            if not results:
                st.info("No teams configured with Opta feed source.")
            else:
                any_new = False
                for team_name, s in results.items():
                    if "error" in s:
                        st.error(f"{team_name}: {s['error']}")
                    elif s["upserted"] > 0:
                        st.success(f"{team_name}: {s['upserted']} fixture(s) added/updated.")
                        any_new = True
                    elif s["total_home"] == 0:
                        st.warning(f"{team_name}: no home matches found in feed ({s['total_matches']} total matches checked). Check competition ID and feed team ID.")
                    else:
                        st.info(f"{team_name}: {s['total_home']} home match(es) found — {s['skipped_past']} in the past, {s['skipped_other']} unusable. Nothing new to add.")
                if any_new:
                    st.cache_data.clear()
                    st.rerun()
        except EnvironmentError as e:
            st.error(str(e))
        except (ConnectionError, PermissionError, ValueError) as e:
            st.error(str(e))

    st.divider()
    with st.expander("Columns", expanded=False):
        all_info_cols = ["Competition", "Local Kickoff", "UK Kickoff", "Home Team",
                         "Away Team", "Approval Deadline", "WC Deadline", "Sales Deadline", "Notes"]
        hidden_cols = [
            col for col in all_info_cols
            if not st.checkbox(col, value=True, key=f"col_{col}")
        ]

# ── Load fixtures ─────────────────────────────────────────────────────────────
fixtures = db.get_upcoming_fixtures(days=days, team_ids=selected_team_ids)

if not fixtures:
    st.info("No upcoming fixtures for the selected filters.")
    st.stop()

df = build_tracker_df(fixtures, platforms, statuses)
styled = style_tracker_df(df, platforms, statuses)

# Apply column visibility — hide deselected info columns but keep platform columns
visible_cols = [c for c in df.columns if c not in hidden_cols]
styled = styled.hide(axis="columns", subset=[c for c in hidden_cols if c in df.columns])

with st.sidebar:
    st.download_button(
        "⬇️ Download Excel",
        data=build_excel_export(df[visible_cols]),
        file_name=f"deadlines_tracker_{_date.today().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

# ── Tracker table ─────────────────────────────────────────────────────────────
st.caption(f"Showing {len(fixtures)} fixture(s). Click a row to view details and update statuses.")

event = st.dataframe(
    styled,
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
