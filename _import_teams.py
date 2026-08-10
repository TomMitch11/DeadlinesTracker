"""One-off script to bulk-import teams from the Deadlines Sheet spreadsheet."""
import sys
sys.path.insert(0, r"C:\Users\TomMitchell\OneDrive - Eleven Sports Media Limited\PC\Documents 1\ClaudeCode\DeadlinesTracker")
import db

existing = {t["name"] for t in db.get_teams()}
all_platform_ids = [p["id"] for p in db.get_platforms()]

teams = [
    # NFL
    {"name": "Atlanta Falcons",         "competition": "NFL"},
    {"name": "Baltimore Ravens",         "competition": "NFL"},
    {"name": "Carolina Panthers",        "competition": "NFL"},
    {"name": "Denver Broncos",           "competition": "NFL"},
    {"name": "Miami Dolphins",           "competition": "NFL"},
    {"name": "New York Jets LLC",        "competition": "NFL"},
    {"name": "Saints (New Orleans)",     "competition": "NFL"},
    {"name": "Seahawks (Seattle)",       "competition": "NFL"},
    # MLS
    {"name": "Atlanta United",           "competition": "MLS"},
    {"name": "Charlotte FC",             "competition": "MLS"},
    {"name": "Chicago Fire",             "competition": "MLS"},
    {"name": "FC Dallas",                "competition": "MLS"},
    {"name": "New York City F.C.",       "competition": "MLS"},
    # Premier League
    {"name": "Aston Villa",             "competition": "Premier League"},
    {"name": "Crystal Palace",           "competition": "Premier League"},
    {"name": "Leicester City",           "competition": "Premier League"},
    # EFL Championship
    {"name": "Birmingham City",          "competition": "EFL Championship"},
    {"name": "Blackburn Rovers",         "competition": "EFL Championship"},
    {"name": "Bristol City",             "competition": "EFL Championship"},
    {"name": "Cardiff City",             "competition": "EFL Championship"},
    {"name": "Huddersfield Town AFC",    "competition": "EFL Championship"},
    {"name": "Leeds United",             "competition": "EFL Championship"},
    {"name": "Millwall",                 "competition": "EFL Championship"},
    {"name": "Norwich City",             "competition": "EFL Championship"},
    {"name": "Preston North End",        "competition": "EFL Championship"},
    {"name": "Queens Park Rangers",      "competition": "EFL Championship"},
    {"name": "Sheffield United",         "competition": "EFL Championship"},
    {"name": "Swansea City",             "competition": "EFL Championship"},
    {"name": "Watford FC",               "competition": "EFL Championship"},
    # EFL lower leagues
    {"name": "Leyton Orient",            "competition": "EFL League One"},
    {"name": "Peterborough Utd",         "competition": "EFL League One"},
    {"name": "Wycombe Wanderers",        "competition": "EFL League Two"},
    # Scottish Premiership
    {"name": "Celtic FC",                "competition": "Scottish Premiership"},
    {"name": "Hibernian FC",             "competition": "Scottish Premiership"},
    # European
    {"name": "PSV Eindhoven",            "competition": "Eredivisie"},
    {"name": "Jong PSV",                 "competition": "Eredivisie"},
    {"name": "FCK",                      "competition": "Danish Superliga"},
    # NBA
    {"name": "Brooklyn Nets",            "competition": "NBA"},
    {"name": "LA Clippers",              "competition": "NBA"},
    {"name": "Milwaukee Bucks",          "competition": "NBA"},
    {"name": "New Jersey Devils",        "competition": "NHL"},
    {"name": "Portland Trail Blazers",   "competition": "NBA"},
    {"name": "Sacramento Kings",         "competition": "NBA"},
    # NCAA
    {"name": "Clemson",                  "competition": "NCAA"},
    # Venue / other
    {"name": "London Stadium",           "competition": None},
]

added = skipped = 0
for t in teams:
    if t["name"] in existing:
        print(f"  SKIP  {t['name']}")
        skipped += 1
        continue
    payload = {
        "name": t["name"],
        "competition": t["competition"],
        "deadline_days": 3,
        "feed_source": "manual",
        "season": "2025-26",
    }
    team_id = db.upsert_team(payload)
    db.set_team_platforms(team_id, all_platform_ids)
    print(f"  ADDED {t['name']}  ({t['competition']})")
    added += 1

print(f"\n{added} added, {skipped} skipped (already existed)")
