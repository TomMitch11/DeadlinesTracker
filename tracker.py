from __future__ import annotations
from datetime import date
import pandas as pd

_INFO_COLS = ["fixture_id", "Match Date", "Home Team", "Away Team",
              "Approval Deadline", "WC Deadline", "Sales Deadline", "Notes"]

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
        row: dict = {
            "fixture_id": f["id"],
            "Match Date": f["match_date"],
            "Home Team": f["teams"]["name"],
            "Away Team": f["away_team"],
            "Approval Deadline": f["approval_deadline"],
            "WC Deadline": f["wc_deadline"],
            "Sales Deadline": f.get("sales_deadline") or "",
            "Notes": "📝" if f.get("notes") else "",
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

    def row_style(row: pd.Series) -> list[str]:
        deadline = row.get("Approval Deadline")
        if deadline and deadline < str(today):
            pending_label = next(
                (s["label"] for s in statuses if s["name"] == "pending"), "Pending"
            )
            if any(row.get(p) == pending_label for p in platform_names):
                return ["background-color: #fff3cd"] * len(row)
        return [""] * len(row)

    styler = df.style.map(cell_style, subset=platform_names)
    styler = styler.apply(row_style, axis=1)
    return styler


def has_overdue_pending(row: pd.Series, platform_names: list[str]) -> bool:
    deadline = row.get("Approval Deadline")
    if not deadline or deadline >= str(date.today()):
        return False
    return any(row.get(p) not in ("Uploaded", "—") for p in platform_names)
