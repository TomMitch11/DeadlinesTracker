"""
Helper script to find API-Football league and team IDs.

Usage:
    python find_api_football_ids.py leagues "NWSL"
    python find_api_football_ids.py leagues "Eerste Divisie"
    python find_api_football_ids.py teams <league_id> <season_year> "Houston"
    python find_api_football_ids.py teams 253 2026 "Houston"
"""
import sys
import requests
from config import get_api_football_config

_BASE = "https://v3.football.api-sports.io"


def _get(path: str, params: dict) -> list:
    cfg = get_api_football_config()
    headers = {"x-apisports-key": cfg["api_key"]}
    resp = requests.get(f"{_BASE}{path}", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        print("API error:", data["errors"])
        sys.exit(1)
    return data.get("response", [])


def search_leagues(query: str) -> None:
    results = _get("/leagues", {"search": query})
    if not results:
        print(f"No leagues found for '{query}'")
        return
    print(f"\nLeagues matching '{query}':")
    print(f"{'ID':<8} {'Country':<20} {'Name'}")
    print("-" * 60)
    for r in results:
        lg = r["league"]
        country = r["country"]["name"]
        print(f"{lg['id']:<8} {country:<20} {lg['name']}")


def search_teams(league_id: int, season: int, query: str) -> None:
    results = _get("/teams", {"league": league_id, "season": season})
    if not results:
        print(f"No teams found in league {league_id} season {season}")
        return
    q = query.lower()
    matches = [r for r in results if q in r["team"]["name"].lower()]
    source = matches if matches else results
    label = f"matching '{query}'" if matches else "(all — no match found)"
    print(f"\nTeams {label} in league {league_id}, season {season}:")
    print(f"{'ID':<8} {'Name'}")
    print("-" * 40)
    for r in source:
        t = r["team"]
        print(f"{t['id']:<8} {t['name']}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "leagues":
        search_leagues(sys.argv[2])
    elif cmd == "teams":
        if len(sys.argv) < 5:
            print("Usage: python find_api_football_ids.py teams <league_id> <season_year> <search>")
            sys.exit(1)
        search_teams(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    else:
        print(__doc__)
