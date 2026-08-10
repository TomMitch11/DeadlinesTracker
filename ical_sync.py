from __future__ import annotations
import requests
from datetime import date, datetime, timezone as _tz
from icalendar import Calendar
import db
from deadline_calc import calc_approval_deadline, calc_wc_deadline

_BASE_TEAM = "https://ics.fixtur.es/v2/home/{}.ics"
_BASE_LEAGUE = "https://ics.fixtur.es/v2/league/{}.ics"


def _fetch_events(url: str) -> list:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.Timeout:
        raise ConnectionError(f"iCal request timed out: {url}")
    except requests.RequestException as e:
        raise ConnectionError(f"iCal network error: {e}")
    cal = Calendar.from_ical(resp.content)
    return [c for c in cal.walk() if c.name == "VEVENT"]


def _league_home_uids(league_slug: str, team_name: str) -> set[str]:
    """Return UIDs of fixtures where team_name is the home side in the league feed."""
    try:
        events = _fetch_events(_BASE_LEAGUE.format(league_slug))
    except ConnectionError:
        return set()
    prefix = team_name.lower()
    uids = set()
    for e in events:
        summary = str(e.get("SUMMARY", "")).lower()
        if summary.startswith(prefix):
            uids.add(str(e.get("UID", "")))
    return uids


def _parse_dt(dt_val) -> tuple[date, str | None]:
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is not None:
            dt_val = dt_val.astimezone(_tz.utc)
        return dt_val.date(), dt_val.strftime("%H:%M")
    return dt_val, None


def _parse_away_team(summary: str) -> str:
    for sep in [" - ", " vs ", " VS ", " v "]:
        if sep in summary:
            return summary.split(sep, 1)[1].strip()
    return ""


def sync_team(team: dict, holidays: list[date]) -> tuple[dict, list[dict], list[dict]]:
    """Returns (stats, new_fixtures, rescheduled_fixtures)."""
    slug = team.get("feed_team_id", "")
    if not slug:
        raise ValueError(f"No feed_team_id (fixtur.es slug) set for team '{team['name']}'")

    events = _fetch_events(_BASE_TEAM.format(slug))

    # Build set of league UIDs for cup detection (only if league slug configured)
    league_slug = team.get("feed_competition_id", "")
    league_uids = _league_home_uids(league_slug, team["name"]) if league_slug else set()

    today = date.today()
    upserted = skipped_past = skipped_other = 0
    new_fixtures: list[dict] = []
    rescheduled_fixtures: list[dict] = []

    for event in events:
        summary = str(event.get("SUMMARY", ""))
        dt_start = event.get("DTSTART")
        if not dt_start:
            skipped_other += 1
            continue

        match_date, match_time = _parse_dt(dt_start.dt)
        if match_date < today:
            skipped_past += 1
            continue

        away_name = _parse_away_team(summary)
        if not away_name:
            skipped_other += 1
            continue

        uid = str(event.get("UID", ""))
        game_id = f"ical_{uid}" if uid else None

        # Cup detection: in team feed but not in league feed
        cup_warning = None
        if league_uids and uid and uid not in league_uids:
            cup_warning = f"This fixture may be a cup game — not found in the {team.get('competition', 'league')} feed."

        approval = calc_approval_deadline(match_date, team["deadline_days"], holidays)
        wc = calc_wc_deadline(approval)

        # Check for existing fixture to detect reschedules
        existing = db.get_fixture_by_feed_event_id(game_id) if game_id else None
        is_new = existing is None
        is_rescheduled = (
            not is_new and
            (str(existing["match_date"]) != str(match_date) or
             (existing.get("match_time") or "") != (match_time or ""))
        )

        fixture = {
            "team_id": team["id"],
            "away_team": away_name,
            "match_date": str(match_date),
            "match_time": match_time,
            "match_utc_offset": "+00:00" if match_time else None,
            "approval_deadline": str(approval),
            "wc_deadline": str(wc),
            "season": team["season"],
            "source": "ical",
            "feed_event_id": game_id,
            "venue": team.get("default_venue") if is_new else existing.get("venue"),
        }
        fid = db.upsert_fixture(fixture)
        if is_new:
            db.create_upload_statuses_for_fixture(fid, team["id"])

        notification_data = {
            "home_team": team["name"],
            "away_team": away_name,
            "match_date": str(match_date),
            "competition": team.get("competition") or "",
            "venue": team.get("default_venue") or "",
            "approval_deadline": str(approval),
            "cup_warning": cup_warning,
        }
        if is_new:
            new_fixtures.append(notification_data)
            upserted += 1
        elif is_rescheduled:
            notification_data["old_date"] = str(existing["match_date"])
            rescheduled_fixtures.append(notification_data)
            upserted += 1

    stats = {
        "upserted": upserted,
        "skipped_past": skipped_past,
        "skipped_other": skipped_other,
        "total_home": len(events) - skipped_other - skipped_past,
        "total_matches": len(events),
    }
    return stats, new_fixtures, rescheduled_fixtures


def sync_all_ical_teams() -> dict[str, dict]:
    """Sync all iCal teams and send email notification if anything changed."""
    holidays_raw = db.get_holidays()
    holidays = [date.fromisoformat(h["date"]) for h in holidays_raw]
    teams = [t for t in db.get_teams() if t.get("feed_source") == "ical"]

    all_new: list[dict] = []
    all_rescheduled: list[dict] = []
    results: dict[str, dict] = {}

    for team in teams:
        try:
            stats, new_f, resched_f = sync_team(team, holidays)
        except (ConnectionError, PermissionError, ValueError) as e:
            results[team["name"]] = {"error": str(e)}
            continue
        results[team["name"]] = stats
        all_new.extend(new_f)
        all_rescheduled.extend(resched_f)

    if all_new or all_rescheduled:
        from notifications import send_sync_summary
        send_sync_summary(all_new, all_rescheduled)

    return results
