# Audience-Specific Deadline Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Partner Success and Sales their own read-only deadline views (−1 day and −4 days off the real deadline respectively), with Sales structurally unable to ever fetch the real `approval_deadline`, while Delivery keeps the existing app unchanged.

**Architecture:** Consolidate the app's five duplicated deadline-calculation call sites into one `deadline_calc.calc_all_deadlines()` that also computes `sales_deadline`/`partner_success_deadline` as simple calendar-day shifts off the already-computed `approval_deadline`. Add two new `db.py` query functions whose `.select()` strings can never include the sensitive columns. Ship two new standalone Streamlit scripts (not pages under the existing app) that only ever call those restricted queries.

**Tech Stack:** Python 3, Streamlit, Supabase (existing stack, no new dependencies).

## Global Constraints

- `sales_deadline = approval_deadline - 4 calendar days`; `partner_success_deadline = approval_deadline - 1 calendar day` — plain calendar-day shifts off the already holiday/weekend-aware `approval_deadline`, not a second business-day walk.
- The existing manually-entered Sales Deadline UI in `app.py` is removed — `sales_deadline` becomes always-computed.
- Sales and Partner Success views are separate standalone scripts, not new files under `pages/` (which would appear in the main app's sidebar navigation).
- `get_sales_fixtures`/`get_partner_success_fixtures` must never `.select()` `approval_deadline` or `wc_deadline` — this is the actual security property, enforced at the query layer, not by page code discipline.
- No new database migration tooling — `supabase/schema.sql` is the single source of truth, updated directly; the corresponding `alter table` is a manual step run once against the live database (not part of any task's automated steps).

---

### Task 1: `calc_all_deadlines()` in `deadline_calc.py`

**Files:**
- Modify: `deadline_calc.py`
- Test: `tests/test_deadline_calc.py`

**Interfaces:**
- Produces: `calc_all_deadlines(match_date: date, deadline_days: int, holidays: list[date]) -> dict` returning `{"approval_deadline": date, "wc_deadline": date, "sales_deadline": date, "partner_success_deadline": date}`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_deadline_calc.py`:

```python
from deadline_calc import calc_all_deadlines

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd DeadlinesTracker && python -m pytest tests/test_deadline_calc.py -k calc_all_deadlines -v`
Expected: FAIL with `ImportError: cannot import name 'calc_all_deadlines'`

- [ ] **Step 3: Write minimal implementation**

Add to `deadline_calc.py` (the file currently only has `calc_approval_deadline` and `calc_wc_deadline` — leave both unchanged, add this function after them):

```python
def calc_all_deadlines(match_date: date, deadline_days: int, holidays: list[date]) -> dict:
    approval = calc_approval_deadline(match_date, deadline_days, holidays)
    wc = calc_wc_deadline(approval)
    return {
        "approval_deadline": approval,
        "wc_deadline": wc,
        "sales_deadline": approval - timedelta(days=4),
        "partner_success_deadline": approval - timedelta(days=1),
    }
```

Add `timedelta` to the existing top-of-file import (currently `from datetime import date, timedelta` — check first; if `timedelta` isn't already imported, add it):

```python
from datetime import date, timedelta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd DeadlinesTracker && python -m pytest tests/test_deadline_calc.py -v`
Expected: PASS (all tests in the file, including the 6 pre-existing ones)

- [ ] **Step 5: Commit**

```bash
cd DeadlinesTracker
git add deadline_calc.py tests/test_deadline_calc.py
git commit -m "feat: add calc_all_deadlines computing sales/partner success deadlines"
```

---

### Task 2: Schema — add `partner_success_deadline` column

**Files:**
- Modify: `supabase/schema.sql`

**Interfaces:**
- Produces: `fixtures.partner_success_deadline` column, consumed by Task 3's writes and Task 4's `get_partner_success_fixtures` query.

- [ ] **Step 1: Modify the schema file**

In `supabase/schema.sql`, find the `fixtures` table definition:

```sql
create table fixtures (
    id uuid primary key default uuid_generate_v4(),
    team_id uuid not null references teams(id) on delete cascade,
    away_team text not null,
    match_date date not null,
    match_time text,
    match_utc_offset text,
    approval_deadline date,
    wc_deadline date,
    sales_deadline date,
    notes text not null default '',
```

Add `partner_success_deadline date,` immediately after `sales_deadline date,`:

```sql
create table fixtures (
    id uuid primary key default uuid_generate_v4(),
    team_id uuid not null references teams(id) on delete cascade,
    away_team text not null,
    match_date date not null,
    match_time text,
    match_utc_offset text,
    approval_deadline date,
    wc_deadline date,
    sales_deadline date,
    partner_success_deadline date,
    notes text not null default '',
```

- [ ] **Step 2: Verify the change**

Run: `grep -A 12 "create table fixtures" supabase/schema.sql`
Expected: output shows `partner_success_deadline date,` on the line after `sales_deadline date,`

- [ ] **Step 3: Commit**

```bash
cd DeadlinesTracker
git add supabase/schema.sql
git commit -m "feat: add partner_success_deadline column to fixtures schema"
```

- [ ] **Step 4: Manual step — apply to the live database (not automated, do this once)**

Run this against the live Supabase database via its SQL editor (this is a one-time manual step, not part of the codebase's automated deployment):

```sql
alter table fixtures add column partner_success_deadline date;
```

---

### Task 3: Wire `calc_all_deadlines` into all five call sites, remove manual Sales Deadline UI

**Files:**
- Modify: `api_football_sync.py:89-99`
- Modify: `ical_sync.py:96-115`
- Modify: `opta_sync.py:218-232`
- Modify: `db.py:162-185` (`update_fixture_manual`), `db.py:304-324` (`recalculate_future_deadlines`)
- Modify: `app.py:83-113` (edit-fixture form), `app.py:117-165` (add-fixture form)
- Test: `tests/test_api_football_sync.py`, `tests/test_ical_sync.py`, `tests/test_opta_sync.py`, `tests/test_db.py`

**Interfaces:**
- Consumes: `deadline_calc.calc_all_deadlines(match_date, deadline_days, holidays) -> dict` (Task 1).
- Produces: `db.update_fixture_manual(fixture_id, away_team, match_date, approval_deadline, wc_deadline, sales_deadline, partner_success_deadline, match_time=None, match_utc_offset=None, *, client=None) -> None` — new required `partner_success_deadline` parameter added after `sales_deadline`.

- [ ] **Step 1: Write the failing tests**

Check `tests/test_db.py` for the existing `mock_sb` fixture (already defined near the top of that file) and reuse it. Add:

```python
def test_update_fixture_manual_includes_partner_success_deadline(mock_sb):
    client, chain = mock_sb
    db.update_fixture_manual(
        "fixture-1", "Chelsea", "2026-06-05",
        "2026-06-02", "2026-06-01", "2026-05-29", "2026-06-01",
        client=client,
    )
    payload = chain.update.call_args[0][0]
    assert payload["sales_deadline"] == "2026-05-29"
    assert payload["partner_success_deadline"] == "2026-06-01"

def test_recalculate_future_deadlines_writes_all_four_fields(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"id": "t1", "name": "Chelsea", "deadline_days": 3, "season": "2026"},
    ])
    # First call (get_holidays) returns no holidays, second (get_teams) returns the team above,
    # third (future fixtures query) returns one fixture. Configure via side_effect in call order.
    chain.execute.side_effect = [
        MagicMock(data=[]),  # get_holidays
        MagicMock(data=[{"id": "t1", "name": "Chelsea", "deadline_days": 3, "season": "2026"}]),  # get_teams
        MagicMock(data=[{"id": "f1", "team_id": "t1", "match_date": "2026-06-05"}]),  # future fixtures
        MagicMock(data=[]),  # the .update().execute() call
    ]
    db.recalculate_future_deadlines(client=client)
    update_payload = chain.update.call_args[0][0]
    assert update_payload["sales_deadline"] == "2026-05-29"
    assert update_payload["partner_success_deadline"] == "2026-06-01"
```

Check `tests/test_api_football_sync.py`, `tests/test_ical_sync.py`, `tests/test_opta_sync.py` for how each currently asserts on the built `fixture` dict passed to `db.upsert_fixture` — find the assertion that checks `fixture["wc_deadline"]` or `fixture["approval_deadline"]` in each file's existing sync test, and add a parallel line to each of those same test functions (do not create new test functions — extend the existing ones that already build a fixture and check its dict, since the fixture dict itself is gaining two more keys):

```python
    assert fixture["sales_deadline"] == "2026-05-29"
    assert fixture["partner_success_deadline"] == "2026-06-01"
```

(Adjust the exact date literals to match whatever match date each existing test already uses — read the existing test first to find its match date and compute the corresponding `-4`/`-1` day values before adding the assertion.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd DeadlinesTracker && python -m pytest tests/test_db.py tests/test_api_football_sync.py tests/test_ical_sync.py tests/test_opta_sync.py -v`
Expected: FAIL — `KeyError: 'sales_deadline'` or `TypeError: update_fixture_manual() missing 1 required positional argument`

- [ ] **Step 3: Update `db.py`**

Replace the `update_fixture_manual` signature and body (currently at line 162):

```python
def update_fixture_manual(
    fixture_id: str,
    away_team: str,
    match_date: str,
    approval_deadline: str,
    wc_deadline: str,
    sales_deadline: str,
    partner_success_deadline: str,
    match_time: str | None = None,
    match_utc_offset: str | None = None,
    *,
    client: Client | None = None,
) -> None:
    cl = client or _client()
    payload = {
        "away_team": away_team,
        "match_date": match_date,
        "approval_deadline": approval_deadline,
        "wc_deadline": wc_deadline,
        "sales_deadline": sales_deadline,
        "partner_success_deadline": partner_success_deadline,
        "match_time": match_time,
        "match_utc_offset": match_utc_offset,
    }
    cl.table("fixtures").update(payload).eq("id", fixture_id).execute()
```

Replace `recalculate_future_deadlines` (currently at line 304) to use `calc_all_deadlines`:

```python
def recalculate_future_deadlines(*, client: Client | None = None) -> int:
    """Recalculate approval/wc/sales/partner-success deadlines for all future fixtures.
    Called after holidays are added or removed. Returns count of updated fixtures."""
    from deadline_calc import calc_all_deadlines
    import datetime
    cl = client or _client()
    today = str(datetime.date.today())
    holidays_raw = get_holidays(client=cl)
    holiday_dates = [datetime.date.fromisoformat(h["date"]) for h in holidays_raw]
    teams = get_teams(client=cl)
    deadline_by_team = {t["id"]: t["deadline_days"] for t in teams}
    future = cl.table("fixtures").select("id, team_id, match_date").gte("match_date", today).execute().data
    count = 0
    for f in future:
        deadline_days = deadline_by_team.get(f["team_id"], 3)
        match_date = datetime.date.fromisoformat(f["match_date"])
        deadlines = calc_all_deadlines(match_date, deadline_days, holiday_dates)
        cl.table("fixtures").update({
            "approval_deadline": str(deadlines["approval_deadline"]),
            "wc_deadline": str(deadlines["wc_deadline"]),
            "sales_deadline": str(deadlines["sales_deadline"]),
            "partner_success_deadline": str(deadlines["partner_success_deadline"]),
        }).eq("id", f["id"]).execute()
        count += 1
    return count
```

- [ ] **Step 4: Update `api_football_sync.py`**

Replace (around line 89):

```python
        approval = calc_approval_deadline(match_date, team["deadline_days"], holidays)
        wc = calc_wc_deadline(approval)
```

with:

```python
        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)
```

Update the fixture dict a few lines below (currently `"approval_deadline": str(approval),` / `"wc_deadline": str(wc),`):

```python
            "approval_deadline": str(deadlines["approval_deadline"]),
            "wc_deadline": str(deadlines["wc_deadline"]),
            "sales_deadline": str(deadlines["sales_deadline"]),
            "partner_success_deadline": str(deadlines["partner_success_deadline"]),
```

Update the import at the top of the file: `from deadline_calc import calc_approval_deadline, calc_wc_deadline` becomes `from deadline_calc import calc_all_deadlines`.

- [ ] **Step 5: Update `ical_sync.py`**

Same pattern. Replace (around line 96):

```python
        approval = calc_approval_deadline(match_date, team["deadline_days"], holidays)
        wc = calc_wc_deadline(approval)
```

with:

```python
        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)
```

In the `fixture` dict (around line 114):

```python
            "approval_deadline": str(deadlines["approval_deadline"]),
            "wc_deadline": str(deadlines["wc_deadline"]),
            "sales_deadline": str(deadlines["sales_deadline"]),
            "partner_success_deadline": str(deadlines["partner_success_deadline"]),
```

In the separate `notification_data` dict (around line 131), which only needs the approval deadline for the notification message, update `"approval_deadline": str(approval),` to `"approval_deadline": str(deadlines["approval_deadline"]),`.

Update the import: `from deadline_calc import calc_approval_deadline, calc_wc_deadline` becomes `from deadline_calc import calc_all_deadlines`.

- [ ] **Step 6: Update `opta_sync.py`**

Same pattern. Replace (around line 218):

```python
        approval = calc_approval_deadline(match_date, team["deadline_days"], holidays)
        wc = calc_wc_deadline(approval)
```

with:

```python
        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)
```

In the `fixture` dict (around line 231):

```python
            "approval_deadline": str(deadlines["approval_deadline"]),
            "wc_deadline": str(deadlines["wc_deadline"]),
            "sales_deadline": str(deadlines["sales_deadline"]),
            "partner_success_deadline": str(deadlines["partner_success_deadline"]),
```

Update the import: `from deadline_calc import calc_approval_deadline, calc_wc_deadline` becomes `from deadline_calc import calc_all_deadlines`.

- [ ] **Step 7: Update `app.py` — edit-fixture form**

Read the current `app.py` first — the edit-fixture form is inside `_show_detail`, guarded by `if fixture.get("source") == "manual":`. Replace this block:

```python
        if fixture.get("source") == "manual":
            st.divider()
            with st.expander("✏️ Edit fixture"):
                from datetime import date as _date
                from deadline_calc import calc_approval_deadline, calc_wc_deadline
                new_away = st.text_input("Away team", value=fixture["away_team"], key=f"eaway_{fixture['id']}")
                new_date = st.date_input("Match date", value=_date.fromisoformat(fixture["match_date"]), key=f"edate_{fixture['id']}")
                new_sales = st.date_input(
                    "Sales deadline (optional)",
                    value=_date.fromisoformat(fixture["sales_deadline"]) if fixture.get("sales_deadline") else None,
                    key=f"esales_{fixture['id']}",
                )
                existing_time = fixture.get("match_time") or ""
                new_time_str = st.text_input(
                    "Kickoff time, UTC (HH:MM, leave blank if unknown)",
                    value=existing_time,
                    key=f"etime_{fixture['id']}",
                )
                holidays_raw = db.get_holidays()
                holidays = [_date.fromisoformat(h["date"]) for h in holidays_raw]
                team_data = db.get_team(fixture["team_id"])
                new_approval = calc_approval_deadline(new_date, team_data["deadline_days"], holidays)
                new_wc = calc_wc_deadline(new_approval)
                st.caption(f"Approval deadline: **{new_approval}** | WC deadline: **{new_wc}**")
                if st.button("Save changes", key=f"esave_{fixture['id']}"):
                    import re
                    clean_time = new_time_str.strip()
                    match_time = clean_time if re.match(r"^\d{2}:\d{2}$", clean_time) else None
                    db.update_fixture_manual(
                        fixture["id"], new_away.strip(), str(new_date),
                        str(new_approval), str(new_wc),
                        str(new_sales) if new_sales else None,
                        match_time,
                    )
                    st.cache_data.clear()
                    st.rerun()
```

with:

```python
        if fixture.get("source") == "manual":
            st.divider()
            with st.expander("✏️ Edit fixture"):
                from datetime import date as _date
                from deadline_calc import calc_all_deadlines
                new_away = st.text_input("Away team", value=fixture["away_team"], key=f"eaway_{fixture['id']}")
                new_date = st.date_input("Match date", value=_date.fromisoformat(fixture["match_date"]), key=f"edate_{fixture['id']}")
                existing_time = fixture.get("match_time") or ""
                new_time_str = st.text_input(
                    "Kickoff time, UTC (HH:MM, leave blank if unknown)",
                    value=existing_time,
                    key=f"etime_{fixture['id']}",
                )
                holidays_raw = db.get_holidays()
                holidays = [_date.fromisoformat(h["date"]) for h in holidays_raw]
                team_data = db.get_team(fixture["team_id"])
                new_deadlines = calc_all_deadlines(new_date, team_data["deadline_days"], holidays)
                st.caption(
                    f"Approval deadline: **{new_deadlines['approval_deadline']}** | "
                    f"WC deadline: **{new_deadlines['wc_deadline']}**"
                )
                if st.button("Save changes", key=f"esave_{fixture['id']}"):
                    import re
                    clean_time = new_time_str.strip()
                    match_time = clean_time if re.match(r"^\d{2}:\d{2}$", clean_time) else None
                    db.update_fixture_manual(
                        fixture["id"], new_away.strip(), str(new_date),
                        str(new_deadlines["approval_deadline"]), str(new_deadlines["wc_deadline"]),
                        str(new_deadlines["sales_deadline"]), str(new_deadlines["partner_success_deadline"]),
                        match_time,
                    )
                    st.cache_data.clear()
                    st.rerun()
```

- [ ] **Step 8: Update `app.py` — add-fixture form**

Replace this block in `_show_add_form`:

```python
def _show_add_form(teams: list[dict], platforms: list[dict], statuses: list[dict]) -> None:
    from datetime import date as _date
    from deadline_calc import calc_approval_deadline, calc_wc_deadline
    import db as _db

    with st.sidebar:
        st.subheader("Add fixture")
        team_names = [t["name"] for t in teams]
        chosen_team_name = st.selectbox("Home team (client)", team_names, key="add_team")
        team = next((t for t in teams if t["name"] == chosen_team_name), None)
        if team is None:
            st.error("Selected team not found.")
            return
        away = st.text_input("Away team", key="add_away")
        match_date = st.date_input("Match date", min_value=_date.today(), key="add_date")
        match_time_str = st.text_input(
            "Kickoff time, UTC (HH:MM, leave blank if unknown)", key="add_time"
        )
        sales_deadline = st.date_input(
            "Sales deadline (optional)", value=None, key="add_sales"
        )

        holidays_raw = _db.get_holidays()
        holidays = [_date.fromisoformat(h["date"]) for h in holidays_raw]
        approval = calc_approval_deadline(match_date, team["deadline_days"], holidays)
        wc = calc_wc_deadline(approval)
        st.caption(f"Approval deadline: **{approval}** | WC deadline: **{wc}**")

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("Save", key="add_save") and away.strip():
                import re as _re
                _t = match_time_str.strip()
                _match_time = _t if _re.match(r"^\d{2}:\d{2}$", _t) else None
                fixture = {
                    "team_id": team["id"],
                    "away_team": away.strip(),
                    "match_date": str(match_date),
                    "match_time": _match_time,
                    "approval_deadline": str(approval),
                    "wc_deadline": str(wc),
                    "sales_deadline": str(sales_deadline) if sales_deadline else None,
                    "season": team["season"],
                    "source": "manual",
                }
```

with:

```python
def _show_add_form(teams: list[dict], platforms: list[dict], statuses: list[dict]) -> None:
    from datetime import date as _date
    from deadline_calc import calc_all_deadlines
    import db as _db

    with st.sidebar:
        st.subheader("Add fixture")
        team_names = [t["name"] for t in teams]
        chosen_team_name = st.selectbox("Home team (client)", team_names, key="add_team")
        team = next((t for t in teams if t["name"] == chosen_team_name), None)
        if team is None:
            st.error("Selected team not found.")
            return
        away = st.text_input("Away team", key="add_away")
        match_date = st.date_input("Match date", min_value=_date.today(), key="add_date")
        match_time_str = st.text_input(
            "Kickoff time, UTC (HH:MM, leave blank if unknown)", key="add_time"
        )

        holidays_raw = _db.get_holidays()
        holidays = [_date.fromisoformat(h["date"]) for h in holidays_raw]
        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)
        st.caption(
            f"Approval deadline: **{deadlines['approval_deadline']}** | "
            f"WC deadline: **{deadlines['wc_deadline']}**"
        )

        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("Save", key="add_save") and away.strip():
                import re as _re
                _t = match_time_str.strip()
                _match_time = _t if _re.match(r"^\d{2}:\d{2}$", _t) else None
                fixture = {
                    "team_id": team["id"],
                    "away_team": away.strip(),
                    "match_date": str(match_date),
                    "match_time": _match_time,
                    "approval_deadline": str(deadlines["approval_deadline"]),
                    "wc_deadline": str(deadlines["wc_deadline"]),
                    "sales_deadline": str(deadlines["sales_deadline"]),
                    "partner_success_deadline": str(deadlines["partner_success_deadline"]),
                    "season": team["season"],
                    "source": "manual",
                }
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd DeadlinesTracker && python -m pytest tests/test_db.py tests/test_api_football_sync.py tests/test_ical_sync.py tests/test_opta_sync.py -v`
Expected: PASS (all tests, including the new ones)

- [ ] **Step 10: Run the full suite to confirm no regressions**

Run: `cd DeadlinesTracker && python -m pytest tests/ -q`
Expected: all tests pass

- [ ] **Step 11: Commit**

```bash
cd DeadlinesTracker
git add api_football_sync.py ical_sync.py opta_sync.py db.py app.py tests/test_db.py tests/test_api_football_sync.py tests/test_ical_sync.py tests/test_opta_sync.py
git commit -m "feat: compute sales/partner success deadlines everywhere, remove manual sales deadline entry"
```

---

### Task 4: Restricted query functions — `get_sales_fixtures`, `get_partner_success_fixtures`

**Files:**
- Modify: `db.py` (add two functions near `get_upcoming_fixtures`)
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `db.get_platforms() -> list[dict]` (existing), `db.get_team_platforms(team_id) -> list[str]` (existing, returns platform IDs).
- Produces: `get_sales_fixtures(days: int = 14, *, client: Client | None = None) -> list[dict]` (each dict: `id, away_team, match_date, sales_deadline, teams`). `get_partner_success_fixtures(days: int = 14, *, client: Client | None = None) -> list[dict]` (each dict: the above plus `platform_names: list[str]`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_db.py`:

```python
def test_get_sales_fixtures_selects_only_safe_columns(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.get_sales_fixtures(days=14, client=client)
    select_call = chain.select.call_args_list[0]
    selected = select_call.args[0]
    assert "approval_deadline" not in selected
    assert "wc_deadline" not in selected
    assert "sales_deadline" in selected

def test_get_sales_fixtures_returns_data(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"id": "f1", "away_team": "Wolves", "match_date": "2026-06-05",
         "sales_deadline": "2026-06-01", "teams": {"name": "Chelsea"}},
    ])
    result = db.get_sales_fixtures(client=client)
    assert result[0]["away_team"] == "Wolves"

def test_get_partner_success_fixtures_selects_only_safe_columns(mock_sb, monkeypatch):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    monkeypatch.setattr(db, "get_platforms", lambda client=None: [])
    monkeypatch.setattr(db, "get_team_platforms", lambda team_id, client=None: [])
    db.get_partner_success_fixtures(days=14, client=client)
    select_call = chain.select.call_args_list[0]
    selected = select_call.args[0]
    assert "approval_deadline" not in selected
    assert "wc_deadline" not in selected
    assert "partner_success_deadline" in selected

def test_get_partner_success_fixtures_attaches_platform_names(mock_sb, monkeypatch):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"id": "f1", "away_team": "Wolves", "match_date": "2026-06-05",
         "partner_success_deadline": "2026-06-04", "team_id": "t1", "teams": {"name": "Chelsea"}},
    ])
    monkeypatch.setattr(db, "get_platforms", lambda client=None: [
        {"id": "p1", "name": "Big Screen"}, {"id": "p2", "name": "Programme Page"},
    ])
    monkeypatch.setattr(db, "get_team_platforms", lambda team_id, client=None: ["p1"])
    result = db.get_partner_success_fixtures(client=client)
    assert result[0]["platform_names"] == ["Big Screen"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd DeadlinesTracker && python -m pytest tests/test_db.py -k "sales_fixtures or partner_success_fixtures" -v`
Expected: FAIL with `AttributeError: module 'db' has no attribute 'get_sales_fixtures'`

- [ ] **Step 3: Write minimal implementation**

Add to `db.py`, near `get_upcoming_fixtures`:

```python
def get_sales_fixtures(days: int = 14, *, client: Client | None = None) -> list[dict]:
    """Sales-facing fixtures. Deliberately selects only sales_deadline —
    never approval_deadline or wc_deadline, so the real deadline can never
    reach this view."""
    cl = client or _client()
    today = date.today()
    cutoff = today + timedelta(days=days)
    return (
        cl.table("fixtures")
        .select("id, away_team, match_date, sales_deadline, teams(name)")
        .gte("match_date", str(today))
        .lte("match_date", str(cutoff))
        .order("sales_deadline")
        .execute()
        .data
    )

def get_partner_success_fixtures(days: int = 14, *, client: Client | None = None) -> list[dict]:
    """Partner Success-facing fixtures. Deliberately selects only
    partner_success_deadline — never approval_deadline or wc_deadline.
    Attaches each fixture's active platform names (queried separately via
    the existing get_platforms/get_team_platforms, not a nested join, to
    avoid depending on an unverified multi-level Supabase relationship)."""
    cl = client or _client()
    today = date.today()
    cutoff = today + timedelta(days=days)
    fixtures = (
        cl.table("fixtures")
        .select("id, away_team, match_date, partner_success_deadline, team_id, teams(name)")
        .gte("match_date", str(today))
        .lte("match_date", str(cutoff))
        .order("partner_success_deadline")
        .execute()
        .data
    )
    platform_names_by_id = {p["id"]: p["name"] for p in get_platforms(client=cl)}
    team_platform_cache: dict[str, list[str]] = {}
    for f in fixtures:
        team_id = f["team_id"]
        if team_id not in team_platform_cache:
            platform_ids = get_team_platforms(team_id, client=cl)
            team_platform_cache[team_id] = [platform_names_by_id[pid] for pid in platform_ids if pid in platform_names_by_id]
        f["platform_names"] = team_platform_cache[team_id]
    return fixtures
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd DeadlinesTracker && python -m pytest tests/test_db.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
cd DeadlinesTracker
git add db.py tests/test_db.py
git commit -m "feat: add get_sales_fixtures/get_partner_success_fixtures, never selecting the real deadline"
```

---

### Task 5: `sales_view.py` standalone app

**Files:**
- Create: `sales_view.py`
- Test: `tests/test_sales_view.py`

**Interfaces:**
- Consumes: `db.get_sales_fixtures(days: int = 14) -> list[dict]` (Task 4).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sales_view.py
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

def test_sales_view_shows_only_team_date_and_sales_deadline():
    fake_fixtures = [
        {"id": "f1", "away_team": "Wolves", "match_date": "2026-06-05",
         "sales_deadline": "2026-06-01", "teams": {"name": "Chelsea"}},
    ]
    with patch("db.get_sales_fixtures", return_value=fake_fixtures):
        at = AppTest.from_file("sales_view.py")
        at.run()
    assert not at.exception
    page_text = " ".join(m.value for m in at.markdown) + " ".join(t.value for t in at.text) + " ".join(str(d.value) for d in at.dataframe)
    assert "Chelsea" in page_text
    assert "Wolves" in page_text
    assert "2026-06-01" in page_text

def test_sales_view_handles_zero_fixtures():
    with patch("db.get_sales_fixtures", return_value=[]):
        at = AppTest.from_file("sales_view.py")
        at.run()
    assert not at.exception
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd DeadlinesTracker && python -m pytest tests/test_sales_view.py -v`
Expected: FAIL — `FileNotFoundError` or similar, `sales_view.py` doesn't exist yet

- [ ] **Step 3: Write minimal implementation**

```python
# sales_view.py
import streamlit as st
import db

st.set_page_config(page_title="Sales — Deadlines", layout="wide")
st.title("Sales deadlines")

try:
    fixtures = db.get_sales_fixtures(days=14)
except Exception as e:
    st.error(f"Could not load fixtures: {e}")
    st.stop()

if not fixtures:
    st.info("No upcoming fixtures in the next 14 days.")
else:
    rows = [
        {
            "Team": f["teams"]["name"],
            "Away Team": f["away_team"],
            "Match Date": f["match_date"],
            "Sales Deadline": f["sales_deadline"] or "",
        }
        for f in fixtures
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd DeadlinesTracker && python -m pytest tests/test_sales_view.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd DeadlinesTracker
git add sales_view.py tests/test_sales_view.py
git commit -m "feat: add standalone sales_view app"
```

---

### Task 6: `partner_success_view.py` standalone app

**Files:**
- Create: `partner_success_view.py`
- Test: `tests/test_partner_success_view.py`

**Interfaces:**
- Consumes: `db.get_partner_success_fixtures(days: int = 14) -> list[dict]` (Task 4, each dict includes `platform_names: list[str]`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_partner_success_view.py
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

def test_partner_success_view_shows_fixture_and_platforms():
    fake_fixtures = [
        {"id": "f1", "away_team": "Wolves", "match_date": "2026-06-05",
         "partner_success_deadline": "2026-06-04", "teams": {"name": "Chelsea"},
         "platform_names": ["Big Screen", "Programme Page"]},
    ]
    with patch("db.get_partner_success_fixtures", return_value=fake_fixtures):
        at = AppTest.from_file("partner_success_view.py")
        at.run()
    assert not at.exception
    page_text = " ".join(m.value for m in at.markdown) + " ".join(t.value for t in at.text) + " ".join(str(d.value) for d in at.dataframe)
    assert "Chelsea" in page_text
    assert "2026-06-04" in page_text
    assert "Big Screen" in page_text
    assert "Programme Page" in page_text

def test_partner_success_view_handles_zero_fixtures():
    with patch("db.get_partner_success_fixtures", return_value=[]):
        at = AppTest.from_file("partner_success_view.py")
        at.run()
    assert not at.exception
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd DeadlinesTracker && python -m pytest tests/test_partner_success_view.py -v`
Expected: FAIL — `sales_view.py` pattern repeats, `partner_success_view.py` doesn't exist yet

- [ ] **Step 3: Write minimal implementation**

```python
# partner_success_view.py
import streamlit as st
import db

st.set_page_config(page_title="Partner Success — Deadlines", layout="wide")
st.title("Partner Success deadlines")

try:
    fixtures = db.get_partner_success_fixtures(days=14)
except Exception as e:
    st.error(f"Could not load fixtures: {e}")
    st.stop()

if not fixtures:
    st.info("No upcoming fixtures in the next 14 days.")
else:
    rows = [
        {
            "Team": f["teams"]["name"],
            "Away Team": f["away_team"],
            "Match Date": f["match_date"],
            "Partner Success Deadline": f["partner_success_deadline"] or "",
            "Platforms Needed": ", ".join(f["platform_names"]) if f["platform_names"] else "",
        }
        for f in fixtures
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd DeadlinesTracker && python -m pytest tests/test_partner_success_view.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `cd DeadlinesTracker && python -m pytest tests/ -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
cd DeadlinesTracker
git add partner_success_view.py tests/test_partner_success_view.py
git commit -m "feat: add standalone partner_success_view app"
```

---

## Manual verification (after all tasks)

- [ ] Run `alter table fixtures add column partner_success_deadline date;` against the live Supabase database (Task 2, Step 4) — do this before deploying, or every write in Tasks 3-4 will fail against production.
- [ ] Run `streamlit run app.py`, add a manual fixture, confirm the Sales Deadline date-picker is gone and the caption shows the computed approval/WC deadlines only.
- [ ] Run `streamlit run sales_view.py --server.port 8503`, confirm it shows only Team/Away Team/Match Date/Sales Deadline for real upcoming fixtures, with no way to navigate to the Delivery app or Admin page from it.
- [ ] Run `streamlit run partner_success_view.py --server.port 8504`, confirm it shows the platform list correctly for a real team with configured platforms.
- [ ] In the Admin page, update a team's `deadline_days` to one of the historically-derived values, then trigger `recalculate_future_deadlines` (via the existing holiday add/remove flow) and confirm that team's fixtures' `sales_deadline`/`partner_success_deadline` update accordingly.
