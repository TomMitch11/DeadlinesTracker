from __future__ import annotations
import requests
import xml.etree.ElementTree as ET
from datetime import date

from config import get_opta_config
import db
from deadline_calc import calc_all_deadlines


def _ensure_list(value) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _attr(node: dict) -> dict:
    return node.get("@attributes", {})


def _parse_f1_json(data: dict) -> tuple[list[dict], dict[str, str], str]:
    if "SoccerFeed" in data:
        root = data["SoccerFeed"]["SoccerDocument"]
    elif "Games" in data:
        root = data["Games"]
    else:
        raise KeyError(f"Unexpected F1 JSON structure, top-level keys: {list(data.keys())}")

    doc_attrs = _attr(root) if isinstance(root, dict) else {}
    competition_name = (
        doc_attrs.get("competition_name")
        or (root.get("competition_name") if isinstance(root, dict) else "")
        or ""
    )

    teams_raw = _ensure_list(root.get("Team") or root.get("TeamRef"))
    teams: dict[str, str] = {}
    for t in teams_raw:
        attrs = _attr(t)
        uid = attrs.get("uID") or attrs.get("TeamRef", "")
        name_node = t.get("Name", {})
        name = (
            name_node.get("@value") if isinstance(name_node, dict) else str(name_node)
        ) or attrs.get("Name", uid)
        teams[uid] = name

    matches = []
    for match in _ensure_list(root.get("MatchData")):
        attrs = _attr(match)
        raw_uid = match.get("uID") or attrs.get("uID", attrs.get("MatchID", ""))
        game_id = raw_uid[1:] if isinstance(raw_uid, str) and raw_uid.startswith("g") else str(raw_uid)

        match_info = match.get("MatchInfo", {})
        date_node = match_info.get("Date", {}) if isinstance(match_info, dict) else {}
        date_str = (
            date_node.get("@value", "") if isinstance(date_node, dict) else str(date_node)
        )

        utc_offset = ""
        if isinstance(match_info, dict):
            dl = match_info.get("DateLocal", {})
            if isinstance(dl, dict):
                utc_offset = _attr(dl).get("Offset", "") or dl.get("Offset", "")

        home_id = away_id = ""
        for td in _ensure_list(match.get("TeamData")):
            td_attrs = _attr(td)
            side = td_attrs.get("Side") or td.get("Side", "")
            team_ref = td_attrs.get("TeamRef") or td.get("TeamRef", "")
            if side == "Home":
                home_id = team_ref
            elif side == "Away":
                away_id = team_ref

        matches.append({
            "game_id": game_id,
            "date": date_str,
            "home_team_id": home_id,
            "away_team_id": away_id,
            "utc_offset": utc_offset,
        })
    return matches, teams, competition_name


def _parse_f1_xml(text: str) -> tuple[list[dict], dict[str, str], str]:
    root = ET.fromstring(text)
    found = root.find("SoccerDocument")
    doc = found if found is not None else root
    competition_name = doc.get("competition_name", "")

    teams: dict[str, str] = {}
    for team in doc.findall("Team"):
        uid = team.get("uID", "")
        name_el = team.find("Name")
        name = (name_el.text or uid) if name_el is not None else uid
        teams[uid] = name

    matches = []
    for match in doc.findall("MatchData"):
        raw_uid = match.get("uID", "")
        game_id = raw_uid[1:] if raw_uid.startswith("g") else raw_uid

        match_info = match.find("MatchInfo")
        date_el = match_info.find("Date") if match_info is not None else None
        date_str = (date_el.text or "") if date_el is not None else ""

        date_local_el = match_info.find("DateLocal") if match_info is not None else None
        utc_offset = date_local_el.get("Offset", "") if date_local_el is not None else ""

        home_id = away_id = ""
        for td in match.findall("TeamData"):
            if td.get("Side") == "Home":
                home_id = td.get("TeamRef", "")
            elif td.get("Side") == "Away":
                away_id = td.get("TeamRef", "")

        matches.append({
            "game_id": game_id,
            "date": date_str,
            "home_team_id": home_id,
            "away_team_id": away_id,
            "utc_offset": utc_offset,
        })
    return matches, teams, competition_name


def _fetch_and_parse(competition_id: str, season_id: str, cfg: dict) -> tuple[list[dict], dict[str, str], str]:
    url = (
        f"{cfg['base_url']}/competition.php"
        f"?feed_type=f1&competition={competition_id}&season_id={season_id}"
        f"&user={cfg['username']}&psw={cfg['password']}&json"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.Timeout:
        raise ConnectionError("Opta request timed out.")
    except requests.RequestException as e:
        raise ConnectionError(f"Opta network error: {e}")

    try:
        data = resp.json()
        if isinstance(data, dict) and "response" in data:
            raise PermissionError(f"Opta error: {data['response']}")
        return _parse_f1_json(data)
    except (ValueError, KeyError):
        pass

    try:
        return _parse_f1_xml(resp.text)
    except ET.ParseError as e:
        raise ValueError(f"Could not parse Opta response as JSON or XML: {e}")


def sync_team(team: dict, holidays: list[date]) -> dict:
    """Sync upcoming home fixtures for one Opta team.

    Fetches both the primary season and the preceding season to handle leagues
    where a single calendar season spans two Opta season IDs (e.g. MLS 2026).
    Competition name and UTC offset are read directly from the feed — no manual
    configuration required on the team record.
    """
    if not team.get("feed_team_id"):
        raise ValueError(f"No feed_team_id (Opta team ID) set for team '{team['name']}'")

    cfg = get_opta_config()
    primary_season_id = int(team["season"].split("-")[0])
    comp_id = str(team["feed_competition_id"])

    all_matches: dict[str, dict] = {}
    all_teams: dict[str, str] = {}
    competition_name = team.get("competition") or ""

    prev_season_id = str(primary_season_id - 1)
    try:
        prev_matches, prev_teams, _ = _fetch_and_parse(comp_id, prev_season_id, cfg)
        all_teams.update(prev_teams)
        for m in prev_matches:
            all_matches[m["game_id"]] = m
    except (ConnectionError, PermissionError, ValueError):
        pass

    curr_matches, curr_teams, feed_comp_name = _fetch_and_parse(comp_id, str(primary_season_id), cfg)
    all_teams.update(curr_teams)
    for m in curr_matches:
        all_matches[m["game_id"]] = m

    # Auto-populate competition name from the feed if not already set
    if feed_comp_name and not competition_name:
        competition_name = feed_comp_name
        db.update_team_competition(team["id"], feed_comp_name)

    def _norm(tid: str) -> str:
        return tid[1:] if tid.startswith("t") else tid

    feed_team_id = _norm(team.get("feed_team_id", ""))
    today = date.today()
    upserted = skipped_past = skipped_other = total_home = 0

    for m in all_matches.values():
        if _norm(m["home_team_id"]) != feed_team_id:
            continue
        total_home += 1
        try:
            match_date = date.fromisoformat(m["date"][:10])
        except ValueError:
            skipped_other += 1
            continue
        if match_date < today:
            skipped_past += 1
            continue

        away_id = m["away_team_id"]
        away_name = all_teams.get(away_id) or all_teams.get(_norm(away_id)) or away_id

        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)

        raw_date = m["date"]
        match_time_utc = raw_date[11:16] if len(raw_date) > 10 and raw_date[10] == " " else None
        utc_offset = m.get("utc_offset") or None

        fixture = {
            "team_id": team["id"],
            "away_team": away_name,
            "match_date": str(match_date),
            "match_time": match_time_utc,
            "match_utc_offset": utc_offset,
            "approval_deadline": str(deadlines["approval_deadline"]),
            "wc_deadline": str(deadlines["wc_deadline"]),
            "sales_deadline": str(deadlines["sales_deadline"]),
            "partner_success_deadline": str(deadlines["partner_success_deadline"]),
            "season": team["season"],
            "source": "opta",
            "feed_event_id": m["game_id"],
        }
        fid = db.upsert_fixture(fixture)
        db.create_upload_statuses_for_fixture(fid, team["id"])
        upserted += 1

    return {
        "upserted": upserted,
        "skipped_past": skipped_past,
        "skipped_other": skipped_other,
        "total_home": total_home,
        "total_matches": len(all_matches),
    }


def sync_all_opta_teams() -> dict[str, dict]:
    """Sync all teams with feed_source='opta'. Returns {team_name: stats_dict}."""
    holidays_raw = db.get_holidays()
    holidays = [date.fromisoformat(h["date"]) for h in holidays_raw]
    teams = [t for t in db.get_teams() if t.get("feed_source") == "opta"]
    results: dict[str, dict] = {}
    for team in teams:
        try:
            results[team["name"]] = sync_team(team, holidays)
        except (ConnectionError, PermissionError, ValueError) as e:
            results[team["name"]] = {"error": str(e)}
    return results
