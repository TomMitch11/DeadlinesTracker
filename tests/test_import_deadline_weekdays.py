from _import_deadline_weekdays import parse_deadline_matrix, ALIASES


def test_parse_deadline_matrix_extracts_weekday_rules():
    # Column order in the sheet: Team, Source, Sat, Sun, Mon, Tue, Wed, Thu, Fri
    rows = [
        ("Aston Villa", "2026-27 fixtures (gospel)", "Wed (n=14/14)", "Wed", "Wed", "Thu", "Fri (n=3/3)", "Mon", "Tue"),
    ]
    rules, expired = parse_deadline_matrix(rows)
    # Sat(5)->Wed(2), Sun(6)->Wed(2), Mon(0)->Wed(2), Tue(1)->Thu(3), Wed(2)->Fri(4), Thu(3)->Mon(0), Fri(4)->Tue(1)
    assert rules["Aston Villa"] == {5: 2, 6: 2, 0: 2, 1: 3, 2: 4, 3: 0, 4: 1}
    assert expired == set()


def test_parse_deadline_matrix_skips_unparseable_cells():
    rows = [
        ("Some Team", "source", "–", "", None, "Tue (n=2/2)", "–", "–", "–"),
    ]
    rules, expired = parse_deadline_matrix(rows)
    assert rules["Some Team"] == {1: 1}


def test_parse_deadline_matrix_marks_expired_teams_and_skips_rules():
    rows = [
        ("Leyton Orient", "Expired — no active deal", "Expired", "Expired", "Expired",
         "Expired", "Expired", "Expired", "Expired"),
    ]
    rules, expired = parse_deadline_matrix(rows)
    assert expired == {"Leyton Orient"}
    assert "Leyton Orient" not in rules


def test_parse_deadline_matrix_resolves_aliases():
    rows = [
        ("London Stadium", "2026-27 fixtures (gospel)", "Wed (n=15/16)", None, None, "Thu (n=4/4)", None, None, None),
    ]
    rules, expired = parse_deadline_matrix(rows)
    assert rules["West Ham"] == {5: 2, 1: 3}


def test_parse_deadline_matrix_skips_blank_team_name_row():
    rows = [(None, None, None, None, None, None, None, None, None)]
    rules, expired = parse_deadline_matrix(rows)
    assert rules == {}
    assert expired == set()


def test_aliases_cover_known_name_mismatches():
    assert ALIASES == {
        "Millwall FC": "Millwall",
        "Houston Dynamo": "Houston",
        "Atlanta United FC": "Atlanta United",
        "FC Copenhagen": "FCK",
        "London Stadium": "West Ham",
    }
