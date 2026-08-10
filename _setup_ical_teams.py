"""One-off script to add iCal teams and new platforms."""
import db

# ── 1. Ensure StatTV and StadiumTV platforms exist ────────────────────────────
existing_platforms = db.get_platforms()
existing_names = {p["name"]: p["id"] for p in existing_platforms}
print("Existing platforms:", list(existing_names.keys()))

from supabase import create_client
from config import get_db_config
cfg = get_db_config()
cl = create_client(cfg["url"], cfg["key"])

new_platforms = ["StatTV", "StadiumTV"]
for name in new_platforms:
    if name not in existing_names:
        result = cl.table("platforms").insert({"name": name, "display_order": 99}).execute()
        existing_names[name] = result.data[0]["id"]
        print(f"Added platform: {name}")
    else:
        print(f"Platform already exists: {name}")

stat_tv_id = existing_names["StatTV"]
stadium_tv_id = existing_names["StadiumTV"]

# ── 2. Team definitions ───────────────────────────────────────────────────────
teams = [
    {
        "name": "Tottenham Hotspur Women",
        "competition": "FA WSL",
        "season": "2025-26",
        "deadline_days": 3,
        "feed_source": "ical",
        "feed_team_id": "tottenham-hotspur-women",
        "default_venue": "Leyton Orient Stadium",
    },
    {
        "name": "Aston Villa Women",
        "competition": "FA WSL",
        "season": "2025-26",
        "deadline_days": 3,
        "feed_source": "ical",
        "feed_team_id": "aston-villa-women",
        "default_venue": "Villa Park",
    },
    {
        "name": "Leicester City Women",
        "competition": "FA WSL",
        "season": "2025-26",
        "deadline_days": 3,
        "feed_source": "ical",
        "feed_team_id": "leicester-city-women",
        "default_venue": "King Power Stadium",
    },
    {
        "name": "Houston Dash",
        "competition": "NWSL",
        "season": "2026",
        "deadline_days": 3,
        "feed_source": "ical",
        "feed_team_id": "houston-dash",
        "default_venue": "",
    },
    {
        "name": "Jong PSV",
        "competition": "Eerste Divisie",
        "season": "2025-26",
        "deadline_days": 3,
        "feed_source": "ical",
        "feed_team_id": "Jong_PSV",
        "default_venue": "",
    },
    {
        "name": "PSV Vrouwen",
        "competition": "Eredivisie Women",
        "season": "2025-26",
        "deadline_days": 3,
        "feed_source": "ical",
        "feed_team_id": "psv-vrouwen",
        "default_venue": "",
    },
]

# ── 3. Upsert teams and assign StatTV + StadiumTV ─────────────────────────────
existing_teams = {t["name"]: t["id"] for t in db.get_teams()}

for team in teams:
    if team["name"] in existing_teams:
        team["id"] = existing_teams[team["name"]]
    team_id = db.upsert_team(team)
    db.set_team_platforms(team_id, [stat_tv_id, stadium_tv_id])
    print(f"Added/updated team: {team['name']} (id: {team_id})")

print("\nDone. Open Admin to review and adjust venues/platforms as needed.")
