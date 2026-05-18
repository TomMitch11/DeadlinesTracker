import pandas as pd
from tracker import build_tracker_df, style_tracker_df, has_overdue_pending

PLATFORMS = [
    {"id": "p1", "name": "CF", "display_order": 1},
    {"id": "p2", "name": "Big Screen", "display_order": 2},
]

STATUSES = [
    {"id": "s1", "name": "pending",  "label": "Pending",  "colour": "#e74c3c"},
    {"id": "s2", "name": "uploaded", "label": "Uploaded", "colour": "#27ae60"},
]

FIXTURE = {
    "id": "f1",
    "away_team": "Portland",
    "match_date": "2026-06-10",
    "approval_deadline": "2026-06-05",
    "wc_deadline": "2026-06-01",
    "sales_deadline": None,
    "notes": "VIP artwork needed",
    "source": "opta",
    "teams": {"id": "t1", "name": "LA Galaxy"},
    "upload_statuses": [
        {
            "platform_id": "p1",
            "status_id": "s1",
            "statuses": {"id": "s1", "name": "pending", "label": "Pending", "colour": "#e74c3c"},
            "platforms": {"id": "p1", "name": "CF", "display_order": 1},
        },
        {
            "platform_id": "p2",
            "status_id": "s2",
            "statuses": {"id": "s2", "name": "uploaded", "label": "Uploaded", "colour": "#27ae60"},
            "platforms": {"id": "p2", "name": "Big Screen", "display_order": 2},
        },
    ],
}

def test_build_tracker_df_columns():
    df = build_tracker_df([FIXTURE], PLATFORMS, STATUSES)
    assert "Home Team" in df.columns
    assert "CF" in df.columns
    assert "Big Screen" in df.columns

def test_build_tracker_df_status_labels():
    df = build_tracker_df([FIXTURE], PLATFORMS, STATUSES)
    assert df.iloc[0]["CF"] == "Pending"
    assert df.iloc[0]["Big Screen"] == "Uploaded"

def test_build_tracker_df_grey_for_inactive_platform():
    fixture_no_p2 = {**FIXTURE, "upload_statuses": [FIXTURE["upload_statuses"][0]]}
    df = build_tracker_df([fixture_no_p2], PLATFORMS, STATUSES)
    assert df.iloc[0]["Big Screen"] == "—"

def test_build_tracker_df_notes_icon():
    df = build_tracker_df([FIXTURE], PLATFORMS, STATUSES)
    assert df.iloc[0]["Notes"] == "📝"

def test_build_tracker_df_no_notes_empty():
    quiet = {**FIXTURE, "notes": ""}
    df = build_tracker_df([quiet], PLATFORMS, STATUSES)
    assert df.iloc[0]["Notes"] == ""

def test_has_overdue_pending_true():
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    fixture = {**FIXTURE, "approval_deadline": yesterday}
    df = build_tracker_df([fixture], PLATFORMS, STATUSES)
    assert has_overdue_pending(df.iloc[0], ["CF", "Big Screen"])

def test_has_overdue_pending_false_when_all_uploaded():
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    all_uploaded = {**FIXTURE, "approval_deadline": yesterday, "upload_statuses": [
        {**FIXTURE["upload_statuses"][0], "status_id": "s2",
         "statuses": {"id": "s2", "name": "uploaded", "label": "Uploaded", "colour": "#27ae60"}},
        FIXTURE["upload_statuses"][1],
    ]}
    df = build_tracker_df([all_uploaded], PLATFORMS, STATUSES)
    assert not has_overdue_pending(df.iloc[0], ["CF", "Big Screen"])
