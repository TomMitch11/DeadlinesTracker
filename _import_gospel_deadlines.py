"""One-off script to make every current-season fixture's deadline match the
real, human-verified value in MASTER_Deadline Sheet_2026.xlsx, via the
manual-override mechanism, rather than trusting the weekday-rule calc (which
is known wrong for ~43% of confirmed team+weekday combos — see Task 7 in
docs/superpowers/plans/2026-08-20-weekday-deadline-rules.md).
Run once: python _import_gospel_deadlines.py"""
from datetime import date, datetime

from _import_deadline_weekdays import ALIASES


def _to_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def match_gospel_rows(
    gospel_rows: list[tuple],
    app_fixtures: list[dict],
    teams_by_id: dict[str, str],
) -> list[tuple[str, date]]:
    """gospel_rows: (match_date, team_home, team_away, approval_deadline) tuples
    from the gospel sheet. app_fixtures: {id, team_id, match_date} dicts already
    in the app. teams_by_id: {team_id: team_name} for every app team. Returns
    (fixture_id, approval_deadline) pairs for every gospel row that resolves to
    a real app team (through ALIASES) and matches an app fixture on the same
    match date."""
    fixtures_by_key: dict[tuple[str, date], str] = {}
    for f in app_fixtures:
        match_date = _to_date(f["match_date"])
        if match_date is None:
            continue
        team_name = teams_by_id.get(f["team_id"])
        if team_name is None:
            continue
        fixtures_by_key[(team_name, match_date)] = f["id"]

    results: list[tuple[str, date]] = []
    for match_date, team_home, _team_away, approval_deadline in gospel_rows:
        md = _to_date(match_date)
        ad = _to_date(approval_deadline)
        if md is None or ad is None:
            continue
        team_name = ALIASES.get(team_home, team_home)
        fixture_id = fixtures_by_key.get((team_name, md))
        if fixture_id is not None:
            results.append((fixture_id, ad))
    return results


def main() -> None:
    import openpyxl
    import db

    wb = openpyxl.load_workbook("MASTER_Deadline Sheet_2026.xlsx", data_only=True)
    ws = wb["2026-27"]
    gospel_rows = [
        (row[0], row[1], row[2], row[3])
        for row in ws.iter_rows(min_row=2, values_only=True)
        if row[0] and row[1]
    ]

    teams = db.get_teams()
    teams_by_id = {t["id"]: t["name"] for t in teams}
    app_fixtures = db.get_upcoming_fixtures(days=None)

    matches = match_gospel_rows(gospel_rows, app_fixtures, teams_by_id)
    for fixture_id, approval_deadline in matches:
        db.set_fixture_deadline_override(fixture_id, approval_deadline)

    print(
        f"\n{len(matches)} fixture(s) overridden to match the gospel sheet "
        f"out of {len(gospel_rows)} gospel row(s) and {len(app_fixtures)} app fixture(s)."
    )


if __name__ == "__main__":
    main()
