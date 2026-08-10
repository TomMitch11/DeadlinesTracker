"""One-off: set feed_competition_id (league slug) on iCal teams for cup detection."""
import db

slugs = {
    "Tottenham Hotspur Women": "fa-womens-super-league",
    "Aston Villa Women":       "fa-womens-super-league",
    "Leicester City Women":    "fa-womens-super-league",
    "Houston Dash":            "nwsl-national-womens-soccer-league",
    "Jong PSV":                "eerste-divisie",
    "PSV Vrouwen":             "eredivisie-vrouwen",
}

teams = {t["name"]: t for t in db.get_teams()}
for name, slug in slugs.items():
    if name not in teams:
        print(f"Team not found: {name}")
        continue
    t = teams[name]
    db.upsert_team({**t, "feed_competition_id": slug})
    print(f"Set league slug for {name}: {slug}")

print("Done.")
