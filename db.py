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
    team_id: str | None = None,
    *,
    client: Client | None = None,
) -> list[dict]:
    cl = client or _client()
    today = date.today()
    q = (
        cl.table("fixtures")
        .select(
            "id, team_id, away_team, match_date, approval_deadline, "
            "wc_deadline, sales_deadline, notes, season, source, "
            "teams(id, name), "
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
    if team_id:
        q = q.eq("team_id", team_id)
    return q.order("approval_deadline").execute().data

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
    cl.table("fixtures").update({"notes": notes, "updated_at": "now()"}).eq("id", fixture_id).execute()

def update_fixture_dates(
    fixture_id: str,
    match_date: str,
    approval_deadline: str,
    wc_deadline: str,
    *,
    client: Client | None = None,
) -> None:
    cl = client or _client()
    cl.table("fixtures").update({
        "match_date": match_date,
        "approval_deadline": approval_deadline,
        "wc_deadline": wc_deadline,
        "updated_at": "now()",
    }).eq("id", fixture_id).execute()

def update_fixture_manual(
    fixture_id: str,
    away_team: str,
    match_date: str,
    approval_deadline: str,
    wc_deadline: str,
    sales_deadline: str | None,
    *,
    client: Client | None = None,
) -> None:
    cl = client or _client()
    payload = {
        "away_team": away_team,
        "match_date": match_date,
        "approval_deadline": approval_deadline,
        "wc_deadline": wc_deadline,
        "updated_at": "now()",
    }
    if sales_deadline:
        payload["sales_deadline"] = sales_deadline
    cl.table("fixtures").update(payload).eq("id", fixture_id).execute()

# ── Upload status writes ──────────────────────────────────────────────────────

def create_upload_statuses_for_fixture(
    fixture_id: str,
    team_id: str,
    *,
    client: Client | None = None,
) -> None:
    cl = client or _client()
    platform_ids = get_team_platforms(team_id, client=cl)
    pending = cl.table("statuses").select("id").eq("name", "pending").single().execute().data
    if platform_ids:
        cl.table("upload_statuses").insert([
            {"fixture_id": fixture_id, "platform_id": pid, "status_id": pending["id"]}
            for pid in platform_ids
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
    """Recalculate approval_deadline and wc_deadline for all future fixtures.
    Called after holidays are added or removed. Returns count of updated fixtures."""
    from deadline_calc import calc_approval_deadline, calc_wc_deadline
    import datetime
    cl = client or _client()
    today = str(datetime.date.today())
    holidays_raw = get_holidays(client=cl)
    holiday_dates = [datetime.date.fromisoformat(h["date"]) for h in holidays_raw]
    teams = get_teams(client=cl)
    deadline_by_team = {t["id"]: t["deadline_days"] for t in teams}
    future = cl.table("fixtures").select("id, team_id, match_date").gte("match_date", today).execute().data
    count = 0
    for f in future:
        deadline_days = deadline_by_team.get(f["team_id"], 3)
        match_date = datetime.date.fromisoformat(f["match_date"])
        approval = calc_approval_deadline(match_date, deadline_days, holiday_dates)
        wc = calc_wc_deadline(approval)
        cl.table("fixtures").update({
            "approval_deadline": str(approval),
            "wc_deadline": str(wc),
        }).eq("id", f["id"]).execute()
        count += 1
    return count
