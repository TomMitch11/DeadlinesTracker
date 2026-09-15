from __future__ import annotations
import io
from datetime import date, datetime, timedelta, timezone as _tz
from zoneinfo import ZoneInfo
import pandas as pd

_INFO_COLS = ["Competition", "Venue", "Local Kickoff", "UK Kickoff", "Home Team", "Away Team",
              "Approval Deadline", "WC Deadline", "Sales Deadline", "Notes"]


def _parse_offset(offset_str: str) -> timedelta | None:
    """Parse a UTC offset string like '-05:00' or '+01:00' into a timedelta."""
    if not offset_str or len(offset_str) < 6:
        return None
    try:
        sign = 1 if offset_str[0] == "+" else -1
        hours = int(offset_str[1:3])
        minutes = int(offset_str[4:6])
        return timedelta(hours=sign * hours, minutes=sign * minutes)
    except (ValueError, IndexError):
        return None


def _utc_dt(match_date: str, match_time: str) -> datetime | None:
    try:
        return datetime(
            int(match_date[:4]), int(match_date[5:7]), int(match_date[8:10]),
            int(match_time[:2]), int(match_time[3:5]),
            tzinfo=_tz.utc,
        )
    except (ValueError, IndexError):
        return None


def _fmt_local_kickoff(match_date: str, match_time: str | None, utc_offset: str | None) -> str:
    """Format kickoff in venue local time using the per-match UTC offset from the feed."""
    if not match_time:
        try:
            return date.fromisoformat(match_date).strftime("%a %d %b")
        except ValueError:
            return match_date
    utc = _utc_dt(match_date, match_time)
    if utc is None:
        return match_date
    offset = _parse_offset(utc_offset or "")
    if offset is not None:
        return (utc + offset).strftime("%a %d %b, %H:%M")
    return utc.strftime("%a %d %b, %H:%M UTC")


def _fmt_uk_kickoff(match_date: str, match_time: str | None) -> str:
    """Format kickoff in UK time (GMT/BST), accounting for daylight saving."""
    if not match_time:
        try:
            return date.fromisoformat(match_date).strftime("%a %d %b")
        except ValueError:
            return match_date
    utc = _utc_dt(match_date, match_time)
    if utc is None:
        return match_date
    uk_dt = utc.astimezone(ZoneInfo("Europe/London"))
    return uk_dt.strftime("%a %d %b, %H:%M")


def build_tracker_df(
    fixtures: list[dict],
    platforms: list[dict],
    statuses: list[dict],
) -> pd.DataFrame:
    status_by_id = {s["id"]: s for s in statuses}
    rows = []
    for f in fixtures:
        status_map = {
            us["platform_id"]: status_by_id.get(us["status_id"], {})
            for us in f.get("upload_statuses", [])
        }
        match_time = f.get("match_time")
        utc_offset = f.get("match_utc_offset")

        team_info = f.get("teams") or {}
        row: dict = {
            "Competition": team_info.get("competition") or "",
            "Venue": f.get("venue") or "",
            "Local Kickoff": _fmt_local_kickoff(f["match_date"], match_time, utc_offset),
            "UK Kickoff": _fmt_uk_kickoff(f["match_date"], match_time),
            "Home Team": team_info.get("name", ""),
            "Away Team": f.get("away_team", ""),
            "Approval Deadline": f["approval_deadline"],
            "WC Deadline": f["wc_deadline"],
            "Sales Deadline": f.get("sales_deadline") or "",
            "Notes": (f.get("notes") or ""),
        }
        for p in platforms:
            s = status_map.get(p["id"])
            row[p["name"]] = s.get("label", "—") if s else "—"
        rows.append(row)
    return pd.DataFrame(rows)


def style_tracker_df(
    df: pd.DataFrame,
    platforms: list[dict],
    statuses: list[dict],
    today: date | None = None,
) -> pd.Styler:
    today = today or date.today()
    colour_map = {s["label"]: s["colour"] for s in statuses}
    platform_names = [p["name"] for p in platforms]

    def cell_style(val: str) -> str:
        if val == "—":
            return "background-color: #bdc3c7; color: #5d6d7e"
        c = colour_map.get(val)
        return f"background-color: {c}; color: white" if c else ""

    def notes_cell_style(val: str) -> str:
        return "background-color: #d1ecf1; color: #0c5460" if str(val).strip() else ""

    pending_label = next((s["label"] for s in statuses if s["name"] == "pending"), "Pending")
    today_str = today.isoformat()

    def row_style(row: pd.Series) -> list[str]:
        deadline = row.get("Approval Deadline")
        if deadline and str(deadline)[:10] < today_str:
            if any(row.get(p) == pending_label for p in platform_names):
                return [
                    "background-color: #fff3cd; color: #856404" if col not in platform_names else ""
                    for col in row.index
                ]
        return [""] * len(row)

    def fmt_date(val: str) -> str:
        if not val:
            return ""
        try:
            return date.fromisoformat(str(val)).strftime("%a %d %b")
        except ValueError:
            return str(val)

    deadline_cols = [c for c in ["Approval Deadline", "WC Deadline", "Sales Deadline"] if c in df.columns]

    styler = df.style.map(cell_style, subset=platform_names)
    styler = styler.apply(row_style, axis=1)
    if "Notes" in df.columns:
        styler = styler.map(notes_cell_style, subset=["Notes"])
    styler = styler.format(fmt_date, subset=deadline_cols)
    return styler


def build_excel_export(export_df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    export_df.to_excel(buffer, index=False, engine="openpyxl", sheet_name="Deadlines")
    return buffer.getvalue()


def has_overdue_pending(row: pd.Series, platform_names: list[str]) -> bool:
    deadline = row.get("Approval Deadline")
    if not deadline or str(deadline)[:10] >= date.today().isoformat():
        return False
    return any(row.get(p) not in ("Uploaded", "—") for p in platform_names)
