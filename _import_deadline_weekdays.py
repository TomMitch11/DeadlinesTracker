"""One-off script to import Team Deadline Matrix.xlsx into team_deadline_weekdays
and mark expired teams inactive. Run once: python _import_deadline_weekdays.py"""

WEEKDAY_NAMES = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

# (column index in the raw row tuple, Python weekday it represents).
# Sheet column order is Team, Source, Sat, Sun, Mon, Tue, Wed, Thu, Fri.
_MATRIX_COLUMNS = [(2, 5), (3, 6), (4, 0), (5, 1), (6, 2), (7, 3), (8, 4)]

ALIASES = {
    "Millwall FC": "Millwall",
    "Houston Dynamo": "Houston",
    "Atlanta United FC": "Atlanta United",
    "FC Copenhagen": "FCK",
    "London Stadium": "West Ham",
    "New York Jets": "New York Jets LLC",
    "Seattle Seahawks": "Seahawks (Seattle)",
    "New Orleans Saints": "Saints (New Orleans)",
    "PSV Women": "PSV Vrouwen",
}


def _parse_weekday_cell(value) -> int | None:
    """Extract the leading weekday name from a cell like 'Wed (n=14/14)'.
    Returns None if the cell is empty or doesn't start with a recognized weekday name."""
    if not value:
        return None
    token = str(value).split(" ", 1)[0].strip()
    return WEEKDAY_NAMES.get(token)


def parse_deadline_matrix(rows: list[tuple]) -> tuple[dict[str, dict[int, int]], set[str]]:
    """Parse Team Deadline Matrix rows (as yielded by
    ws.iter_rows(min_row=5, values_only=True)) into (rules_by_team_name,
    expired_team_names). Team names are resolved through ALIASES. Cells that
    don't parse to a recognized weekday name are skipped, not guessed."""
    rules: dict[str, dict[int, int]] = {}
    expired: set[str] = set()
    for row in rows:
        matrix_name = row[0]
        if not matrix_name:
            continue
        team_name = ALIASES.get(matrix_name, matrix_name)
        source = str(row[1] or "")
        if source.startswith("Expired"):
            expired.add(team_name)
            continue
        for col_idx, match_weekday in _MATRIX_COLUMNS:
            deadline_weekday = _parse_weekday_cell(row[col_idx])
            if deadline_weekday is not None:
                rules.setdefault(team_name, {})[match_weekday] = deadline_weekday
    return rules, expired


def main() -> None:
    import openpyxl
    import db

    wb = openpyxl.load_workbook("Team Deadline Matrix.xlsx", data_only=True)
    ws = wb["Deadline Matrix"]
    rows = list(ws.iter_rows(min_row=5, values_only=True))
    rules, expired = parse_deadline_matrix(rows)

    teams_by_name = {t["name"]: t["id"] for t in db.get_teams()}

    applied = skipped_no_team = 0

    for team_name in expired:
        team_id = teams_by_name.get(team_name)
        if team_id is None:
            print(f"  SKIP (expired, no matching team) {team_name}")
            skipped_no_team += 1
            continue
        db.set_team_deadline_active(team_id, False)
        print(f"  INACTIVE {team_name}")

    for team_name, weekday_rules in rules.items():
        team_id = teams_by_name.get(team_name)
        if team_id is None:
            print(f"  SKIP (no matching team) {team_name}: {weekday_rules}")
            skipped_no_team += 1
            continue
        db.set_team_deadline_weekdays(team_id, weekday_rules)
        print(f"  SET {team_name}: {len(weekday_rules)} weekday rule(s)")
        applied += 1

    print(
        f"\n{applied} team(s) given weekday rules, {len(expired)} marked inactive, "
        f"{skipped_no_team} skipped (no matching team in the app)."
    )


if __name__ == "__main__":
    main()
