from datetime import date
from deadline_calc import (
    calc_approval_deadline,
    calc_wc_deadline,
    calc_all_deadlines,
    calc_approval_deadline_from_weekday,
    calc_fixture_deadlines,
    deadlines_to_str,
)

def test_approval_deadline_counts_back_working_days():
    # Friday 2026-06-05, 3 working days back = Tuesday 2026-06-02
    match = date(2026, 6, 5)
    result = calc_approval_deadline(match, 3, [])
    assert result == date(2026, 6, 2)

def test_approval_deadline_skips_weekend():
    # Monday 2026-06-08, 1 working day back = Friday 2026-06-05
    match = date(2026, 6, 8)
    result = calc_approval_deadline(match, 1, [])
    assert result == date(2026, 6, 5)

def test_approval_deadline_skips_holidays():
    # Wednesday 2026-06-10, 2 working days back, Monday 2026-06-08 is holiday
    # Count: Tue 2026-06-09 = day 1, Mon skipped (holiday), Fri 2026-06-05 = day 2 → 2026-06-05
    match = date(2026, 6, 10)
    holidays = [date(2026, 6, 8)]
    result = calc_approval_deadline(match, 2, holidays)
    assert result == date(2026, 6, 5)

def test_approval_deadline_weekend_match_returns_weekday():
    # Saturday 2026-06-06, 3 working days back = Wednesday 2026-06-03
    saturday = date(2026, 6, 6)
    result = calc_approval_deadline(saturday, 3, [])
    assert result == date(2026, 6, 3)

def test_wc_deadline_is_monday_of_approval_week():
    # Wednesday 2026-06-03 → Monday 2026-06-01
    result = calc_wc_deadline(date(2026, 6, 3))
    assert result == date(2026, 6, 1)

def test_wc_deadline_is_same_day_if_monday():
    result = calc_wc_deadline(date(2026, 6, 1))
    assert result == date(2026, 6, 1)

def test_calc_all_deadlines_returns_all_four_dates():
    # Friday 2026-06-05, 3 working days back = Tuesday 2026-06-02
    match = date(2026, 6, 5)
    result = calc_all_deadlines(match, 3, [])
    assert result == {
        "approval_deadline": date(2026, 6, 2),
        "wc_deadline": date(2026, 6, 1),
        "sales_deadline": date(2026, 5, 29),
        "partner_success_deadline": date(2026, 6, 1),
    }

def test_calc_all_deadlines_sales_and_partner_success_can_land_on_weekend():
    # Approval deadline Monday 2026-06-08 -> sales deadline (-4d) = Thursday 2026-06-04
    # partner success (-1d) = Sunday 2026-06-07 (weekend is fine, it's a client-facing buffer)
    match = date(2026, 6, 9)
    result = calc_all_deadlines(match, 1, [])
    assert result["approval_deadline"] == date(2026, 6, 8)
    assert result["partner_success_deadline"] == date(2026, 6, 7)
    assert result["sales_deadline"] == date(2026, 6, 4)


def test_calc_approval_deadline_from_weekday_walks_back_to_prior_occurrence():
    # Saturday 2026-06-06 (weekday 5), deadline weekday Wed (2) -> 3 days back = Wed 2026-06-03
    result = calc_approval_deadline_from_weekday(date(2026, 6, 6), 2)
    assert result == date(2026, 6, 3)

def test_calc_approval_deadline_from_weekday_wraps_full_week_when_same_weekday():
    # Tuesday 2026-06-09 (weekday 1), deadline weekday also Tue (1) -> must go back a full
    # week, not 0 days (a deadline can't fall on match day itself)
    result = calc_approval_deadline_from_weekday(date(2026, 6, 9), 1)
    assert result == date(2026, 6, 2)

def test_calc_approval_deadline_from_weekday_matches_known_matrix_row():
    # Aston Villa: Tuesday match -> Thursday deadline (gospel-confirmed n=4/4 in the matrix)
    # Tuesday 2026-06-09 (weekday 1), deadline weekday Thu (3) -> most recent prior Thu = 2026-06-04
    result = calc_approval_deadline_from_weekday(date(2026, 6, 9), 3)
    assert result == date(2026, 6, 4)

def test_calc_fixture_deadlines_inactive_team_returns_all_none():
    team = {"deadline_days": 3, "deadline_active": False}
    result = calc_fixture_deadlines(date(2026, 6, 5), team, {}, [])
    assert result == {
        "approval_deadline": None,
        "wc_deadline": None,
        "sales_deadline": None,
        "partner_success_deadline": None,
    }

def test_calc_fixture_deadlines_uses_weekday_rule_when_present():
    # Friday 2026-06-05 (weekday 4) has a rule -> Wed (2), 2 days back = 2026-06-03
    team = {"deadline_days": 3, "deadline_active": True}
    result = calc_fixture_deadlines(date(2026, 6, 5), team, {4: 2}, [])
    assert result["approval_deadline"] == date(2026, 6, 3)
    assert result["wc_deadline"] == date(2026, 6, 1)
    assert result["sales_deadline"] == date(2026, 5, 30)
    assert result["partner_success_deadline"] == date(2026, 6, 2)

def test_calc_fixture_deadlines_falls_back_to_flat_days_when_no_weekday_rule():
    # Friday 2026-06-05 is weekday 4; the rule map only has weekday 0 -> falls back
    # to the existing flat calc_all_deadlines, unchanged from today's behavior
    team = {"deadline_days": 3, "deadline_active": True}
    result = calc_fixture_deadlines(date(2026, 6, 5), team, {0: 2}, [])
    assert result == calc_all_deadlines(date(2026, 6, 5), 3, [])

def test_deadlines_to_str_converts_dates_and_preserves_none():
    result = deadlines_to_str({
        "approval_deadline": date(2026, 6, 3),
        "wc_deadline": None,
    })
    assert result == {"approval_deadline": "2026-06-03", "wc_deadline": None}
