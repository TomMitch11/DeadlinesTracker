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
