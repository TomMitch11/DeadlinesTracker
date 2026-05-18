from datetime import date, timedelta

def calc_approval_deadline(match_date: date, deadline_days: int, holidays: list[date]) -> date:
    if match_date.weekday() >= 5:
        return match_date
    holidays_set = set(holidays)
    result = match_date
    days_counted = 0
    holidays_encountered = 0
    target_days = deadline_days

    while days_counted < target_days:
        result -= timedelta(days=1)
        if result.weekday() >= 5:
            # Skip weekends
            continue
        if result in holidays_set:
            # Skip holidays and count them
            holidays_encountered += 1
            # Adjust target to account for the holiday
            target_days = deadline_days + holidays_encountered
            continue
        # Count working days
        days_counted += 1
    return result

def calc_wc_deadline(approval_deadline: date) -> date:
    return approval_deadline - timedelta(days=approval_deadline.weekday())
