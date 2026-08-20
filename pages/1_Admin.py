import streamlit as st
import db

st.set_page_config(page_title="Admin — Deadlines Tracker", layout="wide")
st.title("Admin")

tab_teams, tab_platforms, tab_statuses, tab_holidays = st.tabs(
    ["Teams", "Platforms", "Statuses", "Holidays"]
)


@st.dialog("Quick add team")
def _quick_add_team(platforms: list[dict], existing_competitions: list[str]) -> None:
    with st.form("quick_add_form"):
        qa_name = st.text_input("Team name")
        qa_competition = st.selectbox(
            "Competition",
            [""] + existing_competitions + ["+ New competition"],
            key="qa_comp_sel",
        )
        if qa_competition == "+ New competition":
            qa_competition = st.text_input("Competition name", key="qa_comp_new")
        qa_deadline = st.number_input("Deadline days", min_value=1, max_value=14, value=3)
        st.markdown("**Platforms**")
        qa_platforms = [p["id"] for p in platforms if st.checkbox(p["name"], value=True, key=f"qa_plat_{p['id']}")]
        if st.form_submit_button("Add team"):
            if qa_name.strip():
                payload = {
                    "name": qa_name.strip(),
                    "competition": qa_competition.strip() or None,
                    "deadline_days": int(qa_deadline),
                    "feed_source": "manual",
                    "season": "2025-26",
                }
                team_id = db.upsert_team(payload)
                db.set_team_platforms(team_id, qa_platforms)
                st.success(f"'{qa_name.strip()}' added. Edit the full record below to add feed details.")
                st.rerun()
            else:
                st.warning("Team name is required.")


# ── Teams tab ─────────────────────────────────────────────────────────────────
with tab_teams:
    teams = db.get_teams()
    platforms = db.get_platforms()

    col_hdr, col_btn = st.columns([4, 1])
    with col_hdr:
        st.subheader("Teams")
    with col_btn:
        if st.button("Quick add", use_container_width=True, type="primary"):
            existing_competitions = sorted({t["competition"] for t in teams if t.get("competition")})
            _quick_add_team(platforms, existing_competitions)

    team_names = [t["name"] for t in teams] + ["+ Add new team"]
    chosen = st.selectbox("Select team to edit", team_names)

    if chosen == "+ Add new team":
        editing = {}
    else:
        editing = next(t for t in teams if t["name"] == chosen)

    with st.form("team_form"):
        name = st.text_input("Team name", value=editing.get("name", ""))
        deadline_active = st.checkbox("Active deal", value=editing.get("deadline_active", True))
        deadline_days = st.number_input(
            "Fallback (days before match, used when no weekday rule is set below)",
            min_value=1, max_value=21,
            value=editing.get("deadline_days", 3)
        )
        st.markdown("**Deadline weekday by match weekday** (leave 'No rule' to use the fallback above)")
        _WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        _weekday_options = ["No rule"] + _WEEKDAY_LABELS
        existing_rules = db.get_team_deadline_weekdays(editing["id"]) if editing.get("id") else {}
        weekday_cols = st.columns(7)
        selected_rules: dict[int, int] = {}
        for i, wd_label in enumerate(_WEEKDAY_LABELS):
            with weekday_cols[i]:
                current_rule = existing_rules.get(i)
                default_label = _WEEKDAY_LABELS[current_rule] if current_rule is not None else "No rule"
                choice = st.selectbox(
                    wd_label, _weekday_options,
                    index=_weekday_options.index(default_label),
                    key=f"wd_{i}",
                )
                if choice != "No rule":
                    selected_rules[i] = _WEEKDAY_LABELS.index(choice)
        _feed_sources = ["manual", "opta", "statsperform", "api_football", "ical"]
        feed_source = st.selectbox(
            "Feed source",
            _feed_sources,
            index=_feed_sources.index(editing.get("feed_source", "manual")),
        )
        feed_competition_id = st.text_input(
            "Competition / League ID (Opta competition ID or API-Football league ID)",
            value=editing.get("feed_competition_id") or "",
        )
        _ical_hint = " — for iCal, this is the fixtur.es slug e.g. tottenham-hotspur-women" if editing.get("feed_source") == "ical" else ""
        feed_team_id = st.text_input(
            f"Team ID in feed (Opta / Stats Perform / API-Football ID, or fixtur.es slug for iCal){_ical_hint}",
            value=editing.get("feed_team_id") or "",
        )
        default_venue = st.text_input(
            "Default venue (used when syncing fixtures — can be overridden per fixture)",
            value=editing.get("default_venue") or "",
        )
        competition = st.text_input("Competition / league (e.g. MLS, Championship)", value=editing.get("competition") or "")
        season = st.text_input("Current season", value=editing.get("season", "2025-26"))
        st.markdown("**Active platforms for this team**")
        active_platform_ids = db.get_team_platforms(editing["id"]) if editing.get("id") else []
        selected_platforms = []
        for p in platforms:
            checked = st.checkbox(p["name"], value=p["id"] in active_platform_ids, key=f"plat_{p['id']}")
            if checked:
                selected_platforms.append(p["id"])

        submitted = st.form_submit_button("Save team")

    if submitted and name.strip():
        payload = {
            "name": name.strip(),
            "competition": competition.strip() or None,
            "deadline_days": int(deadline_days),
            "deadline_active": deadline_active,
            "feed_source": feed_source,
            "feed_competition_id": feed_competition_id.strip() or None,
            "feed_team_id": feed_team_id.strip() or None,
            "season": season.strip(),
            "default_venue": default_venue.strip() or None,
        }
        if editing.get("id"):
            payload["id"] = editing["id"]
        team_id = db.upsert_team(payload)
        db.set_team_deadline_weekdays(team_id, selected_rules)
        db.set_team_platforms(team_id, selected_platforms)
        # Propagate competition name to all teams in the same feed competition
        comp_val = competition.strip()
        comp_id_val = feed_competition_id.strip()
        if comp_val and comp_id_val:
            db.propagate_competition_name(comp_id_val, comp_val)
        st.success(f"Team '{name}' saved.")
        st.rerun()

    if editing.get("id"):
        st.subheader("Delivery contacts")
        contacts = {
            dc["platform_id"]: dc["contact_info"]
            for dc in db.get_delivery_contacts(editing["id"])
        }
        with st.form("contacts_form"):
            contact_inputs = {}
            for p in platforms:
                if p["id"] in active_platform_ids:
                    contact_inputs[p["id"]] = st.text_area(
                        p["name"],
                        value=contacts.get(p["id"], ""),
                        height=80,
                        key=f"contact_{p['id']}",
                    )
            if st.form_submit_button("Save contacts"):
                for pid, info in contact_inputs.items():
                    db.upsert_delivery_contact(editing["id"], pid, info)
                st.success("Contacts saved.")

# ── Platforms tab ─────────────────────────────────────────────────────────────
with tab_platforms:
    platforms = db.get_platforms()
    st.subheader("Platforms")
    st.caption("Display order controls column order in the tracker.")

    plat_names = [p["name"] for p in platforms] + ["+ Add new platform"]
    chosen_plat = st.selectbox("Select platform", plat_names, key="plat_sel")

    if chosen_plat == "+ Add new platform":
        editing_plat = {}
    else:
        editing_plat = next(p for p in platforms if p["name"] == chosen_plat)

    with st.form("platform_form"):
        pname = st.text_input("Platform name", value=editing_plat.get("name", ""))
        porder = st.number_input(
            "Display order", min_value=0, value=editing_plat.get("display_order", len(platforms))
        )
        if st.form_submit_button("Save platform"):
            payload = {"name": pname.strip(), "display_order": int(porder)}
            if editing_plat.get("id"):
                payload["id"] = editing_plat["id"]
            db.upsert_platform(payload)
            st.success(f"Platform '{pname}' saved.")
            st.rerun()

    if editing_plat.get("id"):
        if st.button("Delete platform", type="secondary"):
            try:
                db.delete_platform(editing_plat["id"])
                st.success("Deleted.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

# ── Statuses tab ──────────────────────────────────────────────────────────────
with tab_statuses:
    statuses = db.get_statuses()
    st.subheader("Upload statuses")
    st.caption("'pending' and 'uploaded' are system statuses and cannot be deleted.")

    stat_names = [s["name"] for s in statuses if not s["is_system"]] + ["+ Add custom status"]
    chosen_stat = st.selectbox("Select status", stat_names, key="stat_sel")

    if chosen_stat == "+ Add custom status":
        editing_stat = {}
    elif statuses:
        editing_stat = next((s for s in statuses if s["name"] == chosen_stat), {})
    else:
        editing_stat = {}

    with st.form("status_form"):
        sname = st.text_input("Internal name (no spaces)", value=editing_stat.get("name", ""))
        slabel = st.text_input("Display label", value=editing_stat.get("label", ""))
        scolour = st.color_picker("Colour", value=editing_stat.get("colour", "#f39c12"))
        sorder = st.number_input("Display order", min_value=0, value=editing_stat.get("display_order", len(statuses)))
        if st.form_submit_button("Save status"):
            payload = {
                "name": sname.strip().replace(" ", "_"),
                "label": slabel.strip(),
                "colour": scolour,
                "display_order": int(sorder),
                "is_system": False,
            }
            if editing_stat.get("id"):
                payload["id"] = editing_stat["id"]
            db.upsert_status(payload)
            st.success(f"Status '{slabel}' saved.")
            st.rerun()

    if editing_stat.get("id") and not editing_stat.get("is_system"):
        if st.button("Delete status", type="secondary", key="del_stat"):
            try:
                db.delete_status(editing_stat["id"])
                st.success("Deleted.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    st.divider()
    st.subheader("All statuses")
    for s in statuses:
        col1, col2, col3 = st.columns([2, 2, 1])
        col1.markdown(f"**{s['label']}**")
        col2.markdown(f"`{s['name']}`")
        col3.markdown(
            f"<span style='background:{s['colour']};padding:4px 12px;border-radius:4px;color:white'>"
            f"&nbsp;</span>",
            unsafe_allow_html=True,
        )

# ── Holidays tab ──────────────────────────────────────────────────────────────
with tab_holidays:
    from datetime import date as _date
    holidays = db.get_holidays()
    st.subheader("Holiday calendar")
    st.caption("Used in deadline calculation. Adding/removing a date recalculates deadlines automatically.")

    with st.form("add_holiday"):
        new_date = st.date_input("Date", key="hol_date")
        new_desc = st.text_input("Description (e.g. Christmas Day)", key="hol_desc")
        if st.form_submit_button("Add holiday"):
            db.upsert_holiday(str(new_date), new_desc.strip())
            n = db.recalculate_future_deadlines()
            st.success(f"Holiday {new_date} added. Recalculated deadlines for {n} future fixtures.")
            st.rerun()

    st.divider()
    for h in holidays:
        col1, col2, col3 = st.columns([2, 4, 1])
        col1.write(h["date"])
        col2.write(h["description"])
        if col3.button("Remove", key=f"del_hol_{h['date']}"):
            db.delete_holiday(h["date"])
            n = db.recalculate_future_deadlines()
            st.success(f"Holiday removed. Recalculated deadlines for {n} future fixtures.")
            st.rerun()
