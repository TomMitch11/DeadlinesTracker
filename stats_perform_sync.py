from __future__ import annotations
import hashlib
import time
import requests
from datetime import date, datetime

from config import get_sp_config
import db
from deadline_calc import calc_fixture_deadlines, deadlines_to_str

_SP_BASE = "http://api.stats.com/v1/stats"
_SPORT = "football"
_LEAGUE = "nfl"


def _sp_sig(api_key: str, secret: str) -> dict:
    timestamp = str(int(time.time()))
    sig = hashlib.sha256((api_key + secret + timestamp).encode()).hexdigest()
    return {"api_key": api_key, "sig": sig, "accept": "json"}


def _season_year(season: str) -> str:
    """Extract the four-digit season year ('2026-27' -> '2026', '2026' -> '2026')."""
    return season.split("-")[0]


def _fetch_schedule(team_id: str, season_year: str, cfg: dict) -> dict:
    """Omitting the season param returns only the single next/current event
    instead of the full season — always pass it explicitly."""
    url = f"{_SP_BASE}/{_SPORT}/{_LEAGUE}/events/teams/{team_id}/"
    params = {**_sp_sig(cfg["sp_api_key"], cfg["sp_api_secret"]), "season": season_year}
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
    except requests.Timeout:
        raise ConnectionError("Stats Perform request timed out.")
    except requests.RequestException as e:
        raise ConnectionError(f"Stats Perform network error: {e}")
    return resp.json()


def _parse_event_date(start_date: list[dict]) -> tuple[date, str, str] | tuple[None, None, None]:
    """Returns (match_date, match_time_utc, utc_offset) from an event's startDate array.
    match_date/match_time come from the UTC entry (matching how ical_sync/api_football_sync
    normalize to UTC); utc_offset is derived from the Local entry, when present."""
    utc_entry = next((d for d in start_date if d.get("dateType") == "UTC"), None)
    if utc_entry is None:
        return None, None, None
    try:
        utc_dt = datetime.fromisoformat(utc_entry["full"])
    except (KeyError, ValueError):
        return None, None, None

    match_date = utc_dt.date()
    match_time = utc_dt.strftime("%H:%M")

    utc_offset = None
    local_entry = next((d for d in start_date if d.get("dateType") == "Local"), None)
    if local_entry is not None:
        try:
            local_dt = datetime.fromisoformat(local_entry["full"])
        except (KeyError, ValueError):
            local_dt = None
        if local_dt is not None:
            total_minutes = int((local_dt - utc_dt).total_seconds() // 60)
            sign = "+" if total_minutes >= 0 else "-"
            h, m = divmod(abs(total_minutes), 60)
            utc_offset = f"{sign}{h:02d}:{m:02d}"

    return match_date, match_time, utc_offset


def sync_team(
    team: dict,
    holidays: list[date],
    weekday_rules: dict[int, int] | None = None,
    overridden_ids: set[str] | None = None,
) -> dict:
    """Sync upcoming home fixtures for one Stats Perform (NFL) team."""
    if not team.get("feed_team_id"):
        raise ValueError(f"No feed_team_id (Stats Perform team ID) set for team '{team['name']}'")
    weekday_rules = weekday_rules or {}
    overridden_ids = overridden_ids or set()

    cfg = get_sp_config()
    raw = _fetch_schedule(team["feed_team_id"], _season_year(team["season"]), cfg)

    try:
        event_types = raw["apiResults"][0]["league"]["season"]["eventType"]
    except (KeyError, IndexError):
        event_types = []

    today = date.today()
    upserted = skipped_past = skipped_other = total_home = total_matches = 0

    for et in event_types:
        events = et.get("events", [])
        total_matches += len(events)
        for event in events:
            teams = event.get("teams", [])
            home = next(
                (t for t in teams if t.get("teamLocationType", {}).get("teamLocationTypeId") == 1),
                None,
            )
            if home is None or str(home.get("teamId")) != str(team["feed_team_id"]):
                continue
            total_home += 1

            match_date, match_time, utc_offset = _parse_event_date(event.get("startDate", []))
            if match_date is None:
                skipped_other += 1
                continue
            if match_date < today:
                skipped_past += 1
                continue

            away = next(
                (t for t in teams if t.get("teamLocationType", {}).get("teamLocationTypeId") == 2),
                {},
            )
            away_name = f"{away.get('location', '')} {away.get('nickname', '')}".strip()
            if not away_name:
                skipped_other += 1
                continue

            game_id = f"sp_{event.get('eventId')}"

            if game_id in overridden_ids:
                deadline_fields = {}
            else:
                deadlines = calc_fixture_deadlines(match_date, team, weekday_rules, holidays)
                deadline_fields = deadlines_to_str(deadlines)

            fixture = {
                "team_id": team["id"],
                "away_team": away_name,
                "match_date": str(match_date),
                "match_time": match_time,
                "match_utc_offset": utc_offset,
                **deadline_fields,
                "season": team["season"],
                "source": "statsperform",
                "feed_event_id": game_id,
            }
            fid = db.upsert_fixture(fixture)
            db.create_upload_statuses_for_fixture(fid, team["id"])
            upserted += 1

    return {
        "upserted": upserted,
        "skipped_past": skipped_past,
        "skipped_other": skipped_other,
        "total_home": total_home,
        "total_matches": total_matches,
    }


def sync_all_stats_perform_teams() -> dict[str, dict]:
    holidays_raw = db.get_holidays()
    holidays = [date.fromisoformat(h["date"]) for h in holidays_raw]
    weekday_map = db.get_deadline_weekdays_by_team()
    overridden_ids = db.get_overridden_feed_event_ids()
    teams = [t for t in db.get_teams() if t.get("feed_source") == "statsperform"]
    results: dict[str, dict] = {}
    for team in teams:
        try:
            results[team["name"]] = sync_team(team, holidays, weekday_map.get(team["id"], {}), overridden_ids)
        except (ConnectionError, PermissionError, ValueError) as e:
            results[team["name"]] = {"error": str(e)}
    return results
