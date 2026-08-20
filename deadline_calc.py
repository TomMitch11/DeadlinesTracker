from datetime import date, timedelta


def calc_approval_deadline(match_date: date, deadline_days: int, holidays: list[date]) -> date:
    holidays_set = set(holidays)
    result = match_date
    days_counted = 0
    while days_counted < deadline_days:
        result -= timedelta(days=1)
        if result.weekday() < 5 and result not in holidays_set:
            days_counted += 1
    return result


def calc_wc_deadline(approval_deadline: date) -> date:
    return approval_deadline - timedelta(days=approval_deadline.weekday())


def calc_all_deadlines(match_date: date, deadline_days: int, holidays: list[date]) -> dict:
    approval = calc_approval_deadline(match_date, deadline_days, holidays)
    wc = calc_wc_deadline(approval)
    return {
        "approval_deadline": approval,
        "wc_deadline": wc,
        "sales_deadline": approval - timedelta(days=4),
        "partner_success_deadline": approval - timedelta(days=1),
    }


def calc_approval_deadline_from_weekday(match_date: date, deadline_weekday: int) -> date:
    """Most recent occurrence of deadline_weekday strictly before match_date.
    A zero-day gap (deadline weekday == match weekday) wraps to a full week back,
    since a deadline can't fall on match day itself."""
    delta = (match_date.weekday() - deadline_weekday) % 7
    return match_date - timedelta(days=delta or 7)


def calc_fixture_deadlines(
    match_date: date,
    team: dict,
    weekday_rules: dict[int, int],
    holidays: list[date],
) -> dict:
    """Compute all four deadline fields for one fixture:
    1. team['deadline_active'] is False -> all four fields are None (expired/no active deal).
    2. weekday_rules has an entry for match_date.weekday() -> weekday-based calc, no holiday
       adjustment (see Global Constraints).
    3. otherwise -> the existing flat calc_all_deadlines (business-day walk, holiday-aware)."""
    if not team.get("deadline_active", True):
        return {
            "approval_deadline": None,
            "wc_deadline": None,
            "sales_deadline": None,
            "partner_success_deadline": None,
        }
    deadline_weekday = weekday_rules.get(match_date.weekday())
    if deadline_weekday is not None:
        approval = calc_approval_deadline_from_weekday(match_date, deadline_weekday)
        return {
            "approval_deadline": approval,
            "wc_deadline": calc_wc_deadline(approval),
            "sales_deadline": approval - timedelta(days=4),
            "partner_success_deadline": approval - timedelta(days=1),
        }
    return calc_all_deadlines(match_date, team["deadline_days"], holidays)


def deadlines_to_str(deadlines: dict) -> dict:
    """Convert a calc_all_deadlines/calc_fixture_deadlines result to DB-writable
    strings, preserving None (e.g. for an inactive team)."""
    return {k: (str(v) if v is not None else None) for k, v in deadlines.items()}
