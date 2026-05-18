from datetime import date
from deadline_calc import calc_approval_deadline, calc_wc_deadline

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
    # Expect: skip Mon, count Fri 2026-06-05 as day 1, Thu 2026-06-04 as day 2 → 2026-06-04
    match = date(2026, 6, 10)
    holidays = [date(2026, 6, 8)]
    result = calc_approval_deadline(match, 2, holidays)
    assert result == date(2026, 6, 4)

def test_approval_deadline_returns_match_date_for_weekend():
    saturday = date(2026, 6, 6)
    result = calc_approval_deadline(saturday, 3, [])
    assert result == saturday

def test_wc_deadline_is_monday_of_approval_week():
    # Wednesday 2026-06-03 → Monday 2026-06-01
    result = calc_wc_deadline(date(2026, 6, 3))
    assert result == date(2026, 6, 1)

def test_wc_deadline_is_same_day_if_monday():
    result = calc_wc_deadline(date(2026, 6, 1))
    assert result == date(2026, 6, 1)
