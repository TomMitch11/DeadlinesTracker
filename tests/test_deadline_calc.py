from datetime import date
from deadline_calc import calc_approval_deadline, calc_wc_deadline, calc_all_deadlines

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
