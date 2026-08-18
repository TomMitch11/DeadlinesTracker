from __future__ import annotations
import requests
from datetime import date, datetime, timezone as _tz
from config import get_api_football_config
import db
from deadline_calc import calc_all_deadlines

_BASE = "https://v3.football.api-sports.io"


def _get(path: str, params: dict, cfg: dict) -> dict:
    headers = {"x-apisports-key": cfg["api_key"]}
    try:
        resp = requests.get(f"{_BASE}{path}", headers=headers, params=params, timeout=30)
        resp.raise_for_status()
    except requests.Timeout:
        raise ConnectionError("API-Football request timed out.")
    except requests.RequestException as e:
        raise ConnectionError(f"API-Football network error: {e}")
    data = resp.json()
    errors = data.get("errors", {})
    if errors:
        raise PermissionError(f"API-Football error: {errors}")
    return data


def _season_year(season: str) -> str:
    """Extract the four-digit start year from a season string ('2025-26' → '2025', '2026' → '2026')."""
    return season.split("-")[0]


def _parse_fixture_date(date_str: str) -> tuple[date, str | None, str | None]:
    """Return (match_date, match_time_utc, utc_offset_str) from an ISO date string."""
    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError:
        return None, None, None

    match_date = dt.astimezone(_tz.utc).date()
    match_time = dt.astimezone(_tz.utc).strftime("%H:%M")

    offset_td = dt.utcoffset()
    if offset_td is not None:
        total = int(offset_td.total_seconds())
        sign = "+" if total >= 0 else "-"
        h, m = divmod(abs(total), 3600)
        utc_offset = f"{sign}{h:02d}:{m // 60:02d}"
    else:
        utc_offset = None

    return match_date, match_time, utc_offset


def sync_team(team: dict, holidays: list[date]) -> dict:
    if not team.get("feed_team_id"):
        raise ValueError(f"No feed_team_id (API-Football team ID) set for team '{team['name']}'")

    cfg = get_api_football_config()
    season_year = _season_year(team["season"])
    team_feed_id = int(team["feed_team_id"])

    data = _get("/fixtures", {
        "league": team["feed_competition_id"],
        "season": season_year,
        "team": team_feed_id,
        "timezone": "UTC",
    }, cfg)

    fixtures = data.get("response", [])
    today = date.today()
    upserted = skipped_past = skipped_other = total_home = 0

    for item in fixtures:
        if item["teams"]["home"]["id"] != team_feed_id:
            continue
        total_home += 1

        match_date, match_time, utc_offset = _parse_fixture_date(item["fixture"]["date"])
        if match_date is None:
            skipped_other += 1
            continue
        if match_date < today:
            skipped_past += 1
            continue

        away_name = item["teams"]["away"]["name"]
        game_id = f"apif_{item['fixture']['id']}"

        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)

        fixture = {
            "team_id": team["id"],
            "away_team": away_name,
            "match_date": str(match_date),
            "match_time": match_time,
            "match_utc_offset": utc_offset,
            "approval_deadline": str(deadlines["approval_deadline"]),
            "wc_deadline": str(deadlines["wc_deadline"]),
            "sales_deadline": str(deadlines["sales_deadline"]),
            "partner_success_deadline": str(deadlines["partner_success_deadline"]),
            "season": team["season"],
            "source": "api_football",
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
        "total_matches": len(fixtures),
    }


def sync_all_api_football_teams() -> dict[str, dict]:
    holidays_raw = db.get_holidays()
    holidays = [date.fromisoformat(h["date"]) for h in holidays_raw]
    teams = [t for t in db.get_teams() if t.get("feed_source") == "api_football"]
    results: dict[str, dict] = {}
    for team in teams:
        try:
            results[team["name"]] = sync_team(team, holidays)
        except (ConnectionError, PermissionError, ValueError) as e:
            results[team["name"]] = {"error": str(e)}
    return results
