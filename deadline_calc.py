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
