from __future__ import annotations
from datetime import date, timedelta
from supabase import create_client, Client
from config import get_db_config

def _client() -> Client:
    cfg = get_db_config()
    return create_client(cfg["url"], cfg["key"])

# ── Fixtures ──────────────────────────────────────────────────────────────────

def get_upcoming_fixtures(
    days: int | None = 14,
    team_ids: list[str] | None = None,
    *,
    client: Client | None = None,
) -> list[dict]:
    cl = client or _client()
    today = date.today()
    q = (
        cl.table("fixtures")
        .select(
            "id, team_id, away_team, match_date, match_time, match_utc_offset, approval_deadline, "
            "wc_deadline, sales_deadline, partner_success_deadline, deadline_override, notes, season, source, venue, "
            "teams(id, name, competition), "
            "upload_statuses("
            "  platform_id, status_id, updated_by, updated_at, "
            "  statuses(id, name, label, colour), "
            "  platforms(id, name, display_order)"
            ")"
        )
        .gte("match_date", str(today))
    )
    if days is not None:
        cutoff = today + timedelta(days=days)
        q = q.lte("match_date", str(cutoff))
    if team_ids:
        q = q.in_("team_id", team_ids)
    return q.order("approval_deadline").execute().data

def get_sales_fixtures(days: int = 14, *, client: Client | None = None) -> list[dict]:
    """Sales-facing fixtures. Deliberately selects only sales_deadline —
    never approval_deadline or wc_deadline, so the real deadline can never
    reach this view."""
    cl = client or _client()
    today = date.today()
    cutoff = today + timedelta(days=days)
    return (
        cl.table("fixtures")
        .select("id, away_team, match_date, sales_deadline, teams(name)")
        .gte("match_date", str(today))
        .lte("match_date", str(cutoff))
        .order("sales_deadline")
        .execute()
        .data
    )

def get_partner_success_fixtures(days: int = 14, *, client: Client | None = None) -> list[dict]:
    """Partner Success-facing fixtures. Deliberately selects only
    partner_success_deadline — never approval_deadline or wc_deadline.
    Attaches each fixture's active platform names (queried separately via
    the existing get_platforms/get_team_platforms, not a nested join, to
    avoid depending on an unverified multi-level Supabase relationship)."""
    cl = client or _client()
    today = date.today()
    cutoff = today + timedelta(days=days)
    fixtures = (
        cl.table("fixtures")
        .select("id, away_team, match_date, partner_success_deadline, team_id, teams(name)")
        .gte("match_date", str(today))
        .lte("match_date", str(cutoff))
        .order("partner_success_deadline")
        .execute()
        .data
    )
    platform_names_by_id = {p["id"]: p["name"] for p in get_platforms(client=cl)}
    team_platform_cache: dict[str, list[str]] = {}
    for f in fixtures:
        team_id = f["team_id"]
        if team_id not in team_platform_cache:
            platform_ids = get_team_platforms(team_id, client=cl)
            team_platform_cache[team_id] = [platform_names_by_id[pid] for pid in platform_ids if pid in platform_names_by_id]
        f["platform_names"] = team_platform_cache[team_id]
    return fixtures

def get_fixture(fixture_id: str, *, client: Client | None = None) -> dict:
    cl = client or _client()
    return (
        cl.table("fixtures")
        .select(
            "*, teams(id, name), "
            "upload_statuses("
            "  platform_id, status_id, updated_by, updated_at, "
            "  statuses(id, name, label, colour), "
            "  platforms(id, name, display_order)"
            ")"
        )
        .eq("id", fixture_id)
        .single()
        .execute()
        .data
    )

# ── Teams ─────────────────────────────────────────────────────────────────────

def get_teams(*, client: Client | None = None) -> list[dict]:
    cl = client or _client()
    return cl.table("teams").select("*").order("name").execute().data

def get_team(team_id: str, *, client: Client | None = None) -> dict:
    cl = client or _client()
    return cl.table("teams").select("*").eq("id", team_id).single().execute().data

def get_team_platforms(team_id: str, *, client: Client | None = None) -> list[str]:
    cl = client or _client()
    rows = cl.table("team_platforms").select("platform_id").eq("team_id", team_id).execute().data
    return [r["platform_id"] for r in rows]

# ── Team deadline weekdays ──────────────────────────────────────────────────

def get_deadline_weekdays_by_team(*, client: Client | None = None) -> dict[str, dict[int, int]]:
    cl = client or _client()
    rows = cl.table("team_deadline_weekdays").select("team_id, match_weekday, deadline_weekday").execute().data
    result: dict[str, dict[int, int]] = {}
    for r in rows:
        result.setdefault(r["team_id"], {})[r["match_weekday"]] = r["deadline_weekday"]
    return result

def get_team_deadline_weekdays(team_id: str, *, client: Client | None = None) -> dict[int, int]:
    cl = client or _client()
    rows = (
        cl.table("team_deadline_weekdays")
        .select("match_weekday, deadline_weekday")
        .eq("team_id", team_id)
        .execute()
        .data
    )
    return {r["match_weekday"]: r["deadline_weekday"] for r in rows}

def set_team_deadline_weekdays(team_id: str, rules: dict[int, int], *, client: Client | None = None) -> None:
    cl = client or _client()
    cl.table("team_deadline_weekdays").delete().eq("team_id", team_id).execute()
    if rules:
        cl.table("team_deadline_weekdays").insert([
            {"team_id": team_id, "match_weekday": mw, "deadline_weekday": dw}
            for mw, dw in rules.items()
        ]).execute()

def set_team_deadline_active(team_id: str, active: bool, *, client: Client | None = None) -> None:
    cl = client or _client()
    cl.table("teams").update({"deadline_active": active}).eq("id", team_id).execute()

# ── Platforms ─────────────────────────────────────────────────────────────────

def get_platforms(*, client: Client | None = None) -> list[dict]:
    cl = client or _client()
    return cl.table("platforms").select("*").order("display_order").execute().data

# ── Statuses ──────────────────────────────────────────────────────────────────

def get_statuses(*, client: Client | None = None) -> list[dict]:
    cl = client or _client()
    return cl.table("statuses").select("*").order("display_order").execute().data

# ── Upload statuses ───────────────────────────────────────────────────────────

def get_upload_statuses(fixture_id: str, *, client: Client | None = None) -> list[dict]:
    cl = client or _client()
    return (
        cl.table("upload_statuses")
        .select("*, statuses(id, name, label, colour), platforms(id, name, display_order)")
        .eq("fixture_id", fixture_id)
        .execute()
        .data
    )

# ── Delivery contacts ─────────────────────────────────────────────────────────

def get_delivery_contacts(team_id: str, *, client: Client | None = None) -> list[dict]:
    cl = client or _client()
    return (
        cl.table("delivery_contacts")
        .select("*, platforms(name)")
        .eq("team_id", team_id)
        .execute()
        .data
    )

# ── Holidays ──────────────────────────────────────────────────────────────────

def get_holidays(*, client: Client | None = None) -> list[dict]:
    cl = client or _client()
    return cl.table("holidays").select("*").order("date").execute().data

# ── Fixture reads (single) ────────────────────────────────────────────────────

def get_fixture_by_feed_event_id(feed_event_id: str, *, client: Client | None = None) -> dict | None:
    cl = client or _client()
    result = (
        cl.table("fixtures")
        .select("id, match_date, match_time, away_team, approval_deadline")
        .eq("feed_event_id", feed_event_id)
        .execute()
    )
    return result.data[0] if result.data else None

# ── Fixture writes ────────────────────────────────────────────────────────────

def upsert_fixture(fixture: dict, *, client: Client | None = None) -> str:
    cl = client or _client()
    if fixture.get("feed_event_id"):
        result = cl.table("fixtures").upsert(fixture, on_conflict="feed_event_id").execute()
    else:
        result = cl.table("fixtures").insert(fixture).execute()
    return result.data[0]["id"]

def update_fixture_notes(fixture_id: str, notes: str, *, client: Client | None = None) -> None:
    cl = client or _client()
    cl.table("fixtures").update({"notes": notes}).eq("id", fixture_id).execute()

def update_fixture_venue(fixture_id: str, venue: str | None, *, client: Client | None = None) -> None:
    cl = client or _client()
    cl.table("fixtures").update({"venue": venue}).eq("id", fixture_id).execute()

def update_fixture_manual(
    fixture_id: str,
    away_team: str,
    match_date: str,
    approval_deadline: str,
    wc_deadline: str,
    sales_deadline: str,
    partner_success_deadline: str,
    match_time: str | None = None,
    match_utc_offset: str | None = None,
    *,
    client: Client | None = None,
) -> None:
    cl = client or _client()
    payload = {
        "away_team": away_team,
        "match_date": match_date,
        "approval_deadline": approval_deadline,
        "wc_deadline": wc_deadline,
        "sales_deadline": sales_deadline,
        "partner_success_deadline": partner_success_deadline,
        "match_time": match_time,
        "match_utc_offset": match_utc_offset,
    }
    cl.table("fixtures").update(payload).eq("id", fixture_id).execute()

# ── Fixture deadline overrides ───────────────────────────────────────────────

def get_overridden_feed_event_ids(*, client: Client | None = None) -> set[str]:
    cl = client or _client()
    rows = cl.table("fixtures").select("feed_event_id").eq("deadline_override", True).execute().data
    return {r["feed_event_id"] for r in rows if r["feed_event_id"]}

def set_fixture_deadline_override(fixture_id: str, approval_deadline: date, *, client: Client | None = None) -> None:
    from deadline_calc import calc_wc_deadline
    cl = client or _client()
    cl.table("fixtures").update({
        "approval_deadline": str(approval_deadline),
        "wc_deadline": str(calc_wc_deadline(approval_deadline)),
        "sales_deadline": str(approval_deadline - timedelta(days=4)),
        "partner_success_deadline": str(approval_deadline - timedelta(days=1)),
        "deadline_override": True,
    }).eq("id", fixture_id).execute()

def clear_fixture_deadline_override(fixture_id: str, *, client: Client | None = None) -> None:
    from deadline_calc import calc_fixture_deadlines, deadlines_to_str
    cl = client or _client()
    fixture = cl.table("fixtures").select("id, team_id, match_date").eq("id", fixture_id).single().execute().data
    team = get_team(fixture["team_id"], client=cl)
    weekday_rules = get_team_deadline_weekdays(fixture["team_id"], client=cl)
    holidays_raw = get_holidays(client=cl)
    holiday_dates = [date.fromisoformat(h["date"]) for h in holidays_raw]
    match_date = date.fromisoformat(fixture["match_date"])
    deadlines = deadlines_to_str(calc_fixture_deadlines(match_date, team, weekday_rules, holiday_dates))
    cl.table("fixtures").update({**deadlines, "deadline_override": False}).eq("id", fixture_id).execute()

# ── Upload status writes ──────────────────────────────────────────────────────

def create_upload_statuses_for_fixture(
    fixture_id: str,
    team_id: str,
    *,
    client: Client | None = None,
) -> None:
    cl = client or _client()
    platform_ids = get_team_platforms(team_id, client=cl)
    if not platform_ids:
        return
    pending = cl.table("statuses").select("id").eq("name", "pending").single().execute().data
    existing = cl.table("upload_statuses").select("platform_id").eq("fixture_id", fixture_id).execute().data
    existing_ids = {r["platform_id"] for r in existing}
    new_ids = [pid for pid in platform_ids if pid not in existing_ids]
    if new_ids:
        cl.table("upload_statuses").insert([
            {"fixture_id": fixture_id, "platform_id": pid, "status_id": pending["id"]}
            for pid in new_ids
        ]).execute()

def update_upload_status(
    fixture_id: str,
    platform_id: str,
    status_id: str,
    updated_by: str,
    *,
    client: Client | None = None,
) -> None:
    from datetime import datetime, timezone
    cl = client or _client()
    cl.table("upload_statuses").update({
        "status_id": status_id,
        "updated_by": updated_by,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("fixture_id", fixture_id).eq("platform_id", platform_id).execute()

# ── Team writes ───────────────────────────────────────────────────────────────

def update_team_competition(team_id: str, competition: str, *, client: Client | None = None) -> None:
    cl = client or _client()
    cl.table("teams").update({"competition": competition}).eq("id", team_id).execute()

def propagate_competition_name(feed_competition_id: str, competition: str, *, client: Client | None = None) -> None:
    """Set the competition display name on every team sharing the same feed_competition_id."""
    cl = client or _client()
    cl.table("teams").update({"competition": competition}).eq("feed_competition_id", feed_competition_id).execute()

def upsert_team(team: dict, *, client: Client | None = None) -> str:
    cl = client or _client()
    result = cl.table("teams").upsert(team, on_conflict="id").execute()
    return result.data[0]["id"]

def set_team_platforms(
    team_id: str,
    platform_ids: list[str],
    *,
    client: Client | None = None,
) -> None:
    cl = client or _client()
    cl.table("team_platforms").delete().eq("team_id", team_id).execute()
    if platform_ids:
        cl.table("team_platforms").insert([
            {"team_id": team_id, "platform_id": pid} for pid in platform_ids
        ]).execute()

def upsert_delivery_contact(
    team_id: str,
    platform_id: str,
    contact_info: str,
    *,
    client: Client | None = None,
) -> None:
    cl = client or _client()
    cl.table("delivery_contacts").upsert(
        {"team_id": team_id, "platform_id": platform_id, "contact_info": contact_info},
        on_conflict="team_id,platform_id",
    ).execute()

# ── Platform writes ───────────────────────────────────────────────────────────

def upsert_platform(platform: dict, *, client: Client | None = None) -> str:
    cl = client or _client()
    result = cl.table("platforms").upsert(platform, on_conflict="id").execute()
    return result.data[0]["id"]

def delete_platform(platform_id: str, *, client: Client | None = None) -> None:
    cl = client or _client()
    refs = cl.table("upload_statuses").select("fixture_id").eq("platform_id", platform_id).limit(1).execute()
    if refs.data:
        raise ValueError(f"Platform {platform_id} is in use by existing upload statuses")
    cl.table("platforms").delete().eq("id", platform_id).execute()

# ── Status writes ─────────────────────────────────────────────────────────────

def upsert_status(status: dict, *, client: Client | None = None) -> str:
    cl = client or _client()
    result = cl.table("statuses").upsert(status, on_conflict="id").execute()
    return result.data[0]["id"]

def delete_status(status_id: str, *, client: Client | None = None) -> None:
    cl = client or _client()
    row = cl.table("statuses").select("is_system").eq("id", status_id).single().execute().data
    if row["is_system"]:
        raise ValueError(f"Cannot delete system status {status_id}")
    cl.table("statuses").delete().eq("id", status_id).execute()

# ── Holiday writes ────────────────────────────────────────────────────────────

def upsert_holiday(date_str: str, description: str, *, client: Client | None = None) -> None:
    cl = client or _client()
    cl.table("holidays").upsert({"date": date_str, "description": description}, on_conflict="date").execute()

def delete_holiday(date_str: str, *, client: Client | None = None) -> None:
    cl = client or _client()
    cl.table("holidays").delete().eq("date", date_str).execute()

def recalculate_future_deadlines(*, client: Client | None = None) -> int:
    """Recalculate approval/wc/sales/partner-success deadlines for all future fixtures
    that aren't manually overridden. Called after holidays are added or removed, or
    after the one-off weekday-rule import. Returns count of updated fixtures."""
    from deadline_calc import calc_fixture_deadlines, deadlines_to_str
    import datetime
    cl = client or _client()
    today = str(datetime.date.today())
    holidays_raw = get_holidays(client=cl)
    holiday_dates = [datetime.date.fromisoformat(h["date"]) for h in holidays_raw]
    teams = get_teams(client=cl)
    team_by_id = {t["id"]: t for t in teams}
    weekday_map = get_deadline_weekdays_by_team(client=cl)
    future = (
        cl.table("fixtures")
        .select("id, team_id, match_date, deadline_override")
        .gte("match_date", today)
        .execute()
        .data
    )
    count = 0
    for f in future:
        if f.get("deadline_override"):
            continue
        team = team_by_id.get(f["team_id"], {"deadline_days": 3, "deadline_active": True})
        weekday_rules = weekday_map.get(f["team_id"], {})
        match_date = datetime.date.fromisoformat(f["match_date"])
        deadlines = deadlines_to_str(calc_fixture_deadlines(match_date, team, weekday_rules, holiday_dates))
        cl.table("fixtures").update(deadlines).eq("id", f["id"]).execute()
        count += 1
    return count
