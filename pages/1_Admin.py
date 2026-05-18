import streamlit as st
import db

st.set_page_config(page_title="Admin — Deadlines Tracker", layout="wide")
st.title("Admin")

tab_teams, tab_platforms, tab_statuses, tab_holidays = st.tabs(
    ["Teams", "Platforms", "Statuses", "Holidays"]
)

# ── Teams tab ─────────────────────────────────────────────────────────────────
with tab_teams:
    teams = db.get_teams()
    platforms = db.get_platforms()

    st.subheader("Teams")
    team_names = [t["name"] for t in teams] + ["+ Add new team"]
    chosen = st.selectbox("Select team to edit", team_names)

    if chosen == "+ Add new team":
        editing = {}
    else:
        editing = next(t for t in teams if t["name"] == chosen)

    with st.form("team_form"):
        name = st.text_input("Team name", value=editing.get("name", ""))
        deadline_days = st.number_input(
            "Deadline days (working days before match)", min_value=1, max_value=14,
            value=editing.get("deadline_days", 3)
        )
        feed_source = st.selectbox(
            "Feed source",
            ["manual", "opta", "statsperform"],
            index=["manual", "opta", "statsperform"].index(editing.get("feed_source", "manual")),
        )
        feed_competition_id = st.text_input(
            "Opta competition ID (leave blank if not Opta)",
            value=editing.get("feed_competition_id") or "",
        )
        feed_team_id = st.text_input(
            "Stats Perform team ID (leave blank if not Stats Perform)",
            value=editing.get("feed_team_id") or "",
        )
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
            "deadline_days": int(deadline_days),
            "feed_source": feed_source,
            "feed_competition_id": feed_competition_id.strip() or None,
            "feed_team_id": feed_team_id.strip() or None,
            "season": season.strip(),
        }
        if editing.get("id"):
            payload["id"] = editing["id"]
        team_id = db.upsert_team(payload)
        db.set_team_platforms(team_id, selected_platforms)
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
