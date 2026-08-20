# Per-Team Weekday Deadline Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat, wrong `deadline_days`-for-every-team deadline calculation with the real per-team, per-match-weekday rule derived from `Team Deadline Matrix.xlsx`, backfill the 544 existing fixtures under it, and add a manual per-fixture override for the cases (holidays, one-offs) the rule doesn't cover.

**Architecture:** A new `team_deadline_weekdays` table (one row per team per match weekday with a confirmed rule) sits alongside the existing `teams.deadline_days` flat fallback. A new `calc_fixture_deadlines()` picks between them per fixture. A new `fixtures.deadline_override` flag protects hand-corrected fixtures from ever being recomputed by a sync or by `recalculate_future_deadlines`. A one-off script imports the matrix data once; the Admin page lets Tom maintain it afterwards.

**Tech Stack:** Python, Streamlit, Supabase (Postgres via `supabase-py`), pytest, openpyxl.

## Global Constraints

- `0` = Monday .. `6` = Sunday for all weekday integers (Python `date.weekday()` convention) — matches the rest of the codebase.
- No holiday-shifting on the weekday-rule calculation path — only the flat `deadline_days` path (unchanged, pre-existing) is holiday-aware. This is deliberate (see design spec's Problem section) — do not add holiday logic to `calc_approval_deadline_from_weekday`.
- `sales_deadline` is always `approval_deadline - 4 days`; `partner_success_deadline` is always `approval_deadline - 1 day` — calendar-day offsets, never business-day walks, matching the existing `calc_all_deadlines` behavior.
- Every function that talks to Supabase takes an optional `*, client: Client | None = None` keyword-only parameter, matching every existing function in `db.py` — this is how tests inject a mock client.
- Full design context: `docs/superpowers/specs/2026-08-20-weekday-deadline-rules-design.md`.

---

### Task 1: Schema — `team_deadline_weekdays`, `teams.deadline_active`, `fixtures.deadline_override`

**Files:**
- Modify: `supabase/schema.sql`

**Interfaces:**
- Produces: `team_deadline_weekdays(team_id, match_weekday, deadline_weekday)` table, `teams.deadline_active` column (default `true`), `fixtures.deadline_override` column (default `false`) — consumed by Tasks 2-6.

- [ ] **Step 1: Add `deadline_active` to the `teams` table**

In `supabase/schema.sql`, find:

```sql
create table teams (
    id uuid primary key default uuid_generate_v4(),
    name text not null unique,
    deadline_days integer not null default 3,
    feed_source text not null default 'manual',
    feed_competition_id text,
    feed_team_id text,
    season text not null default '2025-26',
    competition text,
    default_venue text
);
```

Replace with:

```sql
create table teams (
    id uuid primary key default uuid_generate_v4(),
    name text not null unique,
    deadline_days integer not null default 3,
    deadline_active boolean not null default true,
    feed_source text not null default 'manual',
    feed_competition_id text,
    feed_team_id text,
    season text not null default '2025-26',
    competition text,
    default_venue text
);
```

- [ ] **Step 2: Add `deadline_override` to the `fixtures` table**

Find:

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

Replace with:

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
    deadline_override boolean not null default false,
    notes text not null default '',
```

- [ ] **Step 3: Add the `team_deadline_weekdays` table**

Find the `create index on fixtures(team_id);` line (just after the `fixtures` table and its `fixtures_set_updated_at` trigger) and add the new table immediately after it:

```sql
create index on fixtures(team_id);

-- Per-team, per-match-weekday deadline rule (0=Mon..6=Sun). Missing row for a
-- given team+weekday means "no confirmed rule" — falls back to teams.deadline_days.
create table team_deadline_weekdays (
    team_id uuid not null references teams(id) on delete cascade,
    match_weekday integer not null check (match_weekday between 0 and 6),
    deadline_weekday integer not null check (deadline_weekday between 0 and 6),
    primary key (team_id, match_weekday)
);
```

- [ ] **Step 4: Verify the changes**

Run: `grep -n "deadline_active\|deadline_override\|team_deadline_weekdays" supabase/schema.sql`
Expected: shows `deadline_active boolean not null default true,` in `teams`, `deadline_override boolean not null default false,` in `fixtures`, and the full `team_deadline_weekdays` table definition.

- [ ] **Step 5: Commit**

```bash
cd DeadlinesTracker
git add supabase/schema.sql
git commit -m "feat: add team_deadline_weekdays table, teams.deadline_active, fixtures.deadline_override"
```

- [ ] **Step 6: Manual step — apply to the live database (not automated, do this once)**

Run this against the live Supabase database via its SQL editor (one-time manual step, not part of the app's automated deployment — confirm with Tom before running, since this touches the live production schema):

```sql
alter table teams add column deadline_active boolean not null default true;
alter table fixtures add column deadline_override boolean not null default false;
create table team_deadline_weekdays (
    team_id uuid not null references teams(id) on delete cascade,
    match_weekday integer not null check (match_weekday between 0 and 6),
    deadline_weekday integer not null check (deadline_weekday between 0 and 6),
    primary key (team_id, match_weekday)
);
```

---

### Task 2: `deadline_calc.py` — weekday-rule calculation

**Files:**
- Modify: `deadline_calc.py`
- Test: `tests/test_deadline_calc.py`

**Interfaces:**
- Consumes: nothing new (pure functions).
- Produces: `calc_approval_deadline_from_weekday(match_date: date, deadline_weekday: int) -> date`, `calc_fixture_deadlines(match_date: date, team: dict, weekday_rules: dict[int, int], holidays: list[date]) -> dict` (same four-key shape as `calc_all_deadlines`, values may be `None`), `deadlines_to_str(deadlines: dict) -> dict` (converts `date`/`None` values to `str`/`None`) — all consumed by Task 3 and Task 4.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_deadline_calc.py`:

```python
from deadline_calc import calc_approval_deadline_from_weekday, calc_fixture_deadlines, deadlines_to_str

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd DeadlinesTracker && python -m pytest tests/test_deadline_calc.py -v`
Expected: FAIL — `ImportError: cannot import name 'calc_approval_deadline_from_weekday'`

- [ ] **Step 3: Write the implementation**

Replace the full contents of `deadline_calc.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd DeadlinesTracker && python -m pytest tests/test_deadline_calc.py -v`
Expected: all PASS (existing tests unaffected — `calc_all_deadlines`/`calc_approval_deadline`/`calc_wc_deadline` are unchanged)

- [ ] **Step 5: Commit**

```bash
cd DeadlinesTracker
git add deadline_calc.py tests/test_deadline_calc.py
git commit -m "feat: add weekday-based deadline calculation"
```

---

### Task 3: `db.py` — weekday-rule and override read/write functions

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `deadline_calc.calc_fixture_deadlines`, `deadline_calc.calc_wc_deadline`, `deadline_calc.deadlines_to_str` (Task 2).
- Produces: `get_deadline_weekdays_by_team() -> dict[str, dict[int, int]]`, `get_team_deadline_weekdays(team_id: str) -> dict[int, int]`, `set_team_deadline_weekdays(team_id: str, rules: dict[int, int]) -> None`, `set_team_deadline_active(team_id: str, active: bool) -> None`, `get_overridden_feed_event_ids() -> set[str]`, `set_fixture_deadline_override(fixture_id: str, approval_deadline: date) -> None`, `clear_fixture_deadline_override(fixture_id: str) -> None` — all consumed by Task 4, 5, 6. Updated `recalculate_future_deadlines()` (same signature, same return type).

- [ ] **Step 1: Write the failing tests**

Add `from datetime import date` to the top of `tests/test_db.py` (it currently has no top-level import — `import pytest` and `from unittest.mock import MagicMock, patch` are the only imports at the top; add the `date` import as a new line before them). Then append:

```python
from datetime import date

def test_get_deadline_weekdays_by_team_groups_by_team(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"team_id": "t1", "match_weekday": 5, "deadline_weekday": 2},
        {"team_id": "t1", "match_weekday": 1, "deadline_weekday": 3},
        {"team_id": "t2", "match_weekday": 0, "deadline_weekday": 2},
    ])
    result = db.get_deadline_weekdays_by_team(client=client)
    assert result == {"t1": {5: 2, 1: 3}, "t2": {0: 2}}

def test_get_team_deadline_weekdays_returns_map_for_one_team(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[{"match_weekday": 5, "deadline_weekday": 2}])
    result = db.get_team_deadline_weekdays("t1", client=client)
    assert result == {5: 2}

def test_set_team_deadline_weekdays_deletes_then_inserts(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.set_team_deadline_weekdays("t1", {5: 2, 1: 3}, client=client)
    chain.delete.assert_called_once()
    inserted = chain.insert.call_args[0][0]
    assert {"team_id": "t1", "match_weekday": 5, "deadline_weekday": 2} in inserted
    assert {"team_id": "t1", "match_weekday": 1, "deadline_weekday": 3} in inserted

def test_set_team_deadline_weekdays_empty_rules_skips_insert(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.set_team_deadline_weekdays("t1", {}, client=client)
    chain.delete.assert_called_once()
    chain.insert.assert_not_called()

def test_set_team_deadline_active_updates_flag(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.set_team_deadline_active("t1", False, client=client)
    payload = chain.update.call_args[0][0]
    assert payload == {"deadline_active": False}

def test_get_overridden_feed_event_ids_filters_null(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[
        {"feed_event_id": "evt1"}, {"feed_event_id": None},
    ])
    result = db.get_overridden_feed_event_ids(client=client)
    assert result == {"evt1"}

def test_set_fixture_deadline_override_writes_derived_fields(mock_sb):
    client, chain = mock_sb
    chain.execute.return_value = MagicMock(data=[])
    db.set_fixture_deadline_override("fix-1", date(2026, 6, 3), client=client)
    payload = chain.update.call_args[0][0]
    assert payload["approval_deadline"] == "2026-06-03"
    assert payload["wc_deadline"] == "2026-06-01"
    assert payload["sales_deadline"] == "2026-05-30"
    assert payload["partner_success_deadline"] == "2026-06-02"
    assert payload["deadline_override"] is True

def test_clear_fixture_deadline_override_recomputes_and_clears_flag(mock_sb):
    client, chain = mock_sb
    chain.execute.side_effect = [
        MagicMock(data={"id": "fix-1", "team_id": "t1", "match_date": "2026-06-05"}),  # fixture select
        MagicMock(data={"id": "t1", "deadline_days": 3, "deadline_active": True}),  # get_team
        MagicMock(data=[]),  # get_team_deadline_weekdays
        MagicMock(data=[]),  # get_holidays
        MagicMock(data=[]),  # the update
    ]
    db.clear_fixture_deadline_override("fix-1", client=client)
    payload = chain.update.call_args[0][0]
    assert payload["deadline_override"] is False
    # Friday 2026-06-05, flat 3-day fallback (no weekday rule configured) -> 2026-06-02
    assert payload["approval_deadline"] == "2026-06-02"

def test_recalculate_future_deadlines_skips_overridden_fixtures(mock_sb):
    client, chain = mock_sb
    chain.execute.side_effect = [
        MagicMock(data=[]),  # get_holidays
        MagicMock(data=[{"id": "t1", "name": "Chelsea", "deadline_days": 3, "deadline_active": True, "season": "2026"}]),  # get_teams
        MagicMock(data=[]),  # get_deadline_weekdays_by_team
        MagicMock(data=[{"id": "f1", "team_id": "t1", "match_date": "2026-06-05", "deadline_override": True}]),  # future fixtures
    ]
    count = db.recalculate_future_deadlines(client=client)
    assert count == 0
    chain.update.assert_not_called()

def test_recalculate_future_deadlines_inactive_team_writes_none(mock_sb):
    client, chain = mock_sb
    chain.execute.side_effect = [
        MagicMock(data=[]),  # get_holidays
        MagicMock(data=[{"id": "t1", "name": "Chelsea", "deadline_days": 3, "deadline_active": False, "season": "2026"}]),  # get_teams
        MagicMock(data=[]),  # get_deadline_weekdays_by_team
        MagicMock(data=[{"id": "f1", "team_id": "t1", "match_date": "2026-06-05", "deadline_override": False}]),  # future fixtures
        MagicMock(data=[]),  # update
    ]
    db.recalculate_future_deadlines(client=client)
    update_payload = chain.update.call_args[0][0]
    assert update_payload["approval_deadline"] is None
    assert update_payload["wc_deadline"] is None
    assert update_payload["sales_deadline"] is None
    assert update_payload["partner_success_deadline"] is None
```

Now update the existing `test_recalculate_future_deadlines_writes_all_four_fields` test (it needs the new `get_deadline_weekdays_by_team` call and the `deadline_override` field added to its mocked data, in call order). Replace its current body:

```python
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

with:

```python
def test_recalculate_future_deadlines_writes_all_four_fields(mock_sb):
    client, chain = mock_sb
    chain.execute.side_effect = [
        MagicMock(data=[]),  # get_holidays
        MagicMock(data=[{"id": "t1", "name": "Chelsea", "deadline_days": 3, "deadline_active": True, "season": "2026"}]),  # get_teams
        MagicMock(data=[]),  # get_deadline_weekdays_by_team
        MagicMock(data=[{"id": "f1", "team_id": "t1", "match_date": "2026-06-05", "deadline_override": False}]),  # future fixtures
        MagicMock(data=[]),  # the .update().execute() call
    ]
    db.recalculate_future_deadlines(client=client)
    update_payload = chain.update.call_args[0][0]
    assert update_payload["sales_deadline"] == "2026-05-29"
    assert update_payload["partner_success_deadline"] == "2026-06-01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd DeadlinesTracker && python -m pytest tests/test_db.py -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'get_deadline_weekdays_by_team'` (and the updated `test_recalculate_future_deadlines_writes_all_four_fields` fails on an `IndexError`/wrong-payload assertion since the current implementation doesn't call `get_deadline_weekdays_by_team`)

- [ ] **Step 3: Add the new functions to `db.py`**

Add these functions in a new `── Team deadline weekdays ──` section, placed after `get_team_platforms` (around line 117) and before the `── Platforms ──` section:

```python
# ── Team deadline weekdays ──────────────────────────────────────────────────

def get_deadline_weekdays_by_team(*, client: Client | None = None) -> dict[str, dict[int, int]]:
    cl = client or _client()
    rows = cl.table("team_deadline_weekdays").select("team_id, match_weekday, deadline_weekday").execute().data
    result: dict[str, dict[int, int]] = {}
    for r in rows:
        result.setdefault(r["team_id"], {})[r["match_weekday"]] = r["deadline_weekday"]
    return result

def get_team_deadline_weekdays(team_id: str, *, client: Client | None = None) -> dict[int, int]:
    cl = client or _client()
    rows = (
        cl.table("team_deadline_weekdays")
        .select("match_weekday, deadline_weekday")
        .eq("team_id", team_id)
        .execute()
        .data
    )
    return {r["match_weekday"]: r["deadline_weekday"] for r in rows}

def set_team_deadline_weekdays(team_id: str, rules: dict[int, int], *, client: Client | None = None) -> None:
    cl = client or _client()
    cl.table("team_deadline_weekdays").delete().eq("team_id", team_id).execute()
    if rules:
        cl.table("team_deadline_weekdays").insert([
            {"team_id": team_id, "match_weekday": mw, "deadline_weekday": dw}
            for mw, dw in rules.items()
        ]).execute()

def set_team_deadline_active(team_id: str, active: bool, *, client: Client | None = None) -> None:
    cl = client or _client()
    cl.table("teams").update({"deadline_active": active}).eq("id", team_id).execute()
```

Add these functions in a new `── Fixture deadline overrides ──` section, placed right after `update_fixture_manual` (around line 215) and before the `── Upload status writes ──` section:

```python
# ── Fixture deadline overrides ───────────────────────────────────────────────

def get_overridden_feed_event_ids(*, client: Client | None = None) -> set[str]:
    cl = client or _client()
    rows = cl.table("fixtures").select("feed_event_id").eq("deadline_override", True).execute().data
    return {r["feed_event_id"] for r in rows if r["feed_event_id"]}

def set_fixture_deadline_override(fixture_id: str, approval_deadline: date, *, client: Client | None = None) -> None:
    from deadline_calc import calc_wc_deadline
    cl = client or _client()
    cl.table("fixtures").update({
        "approval_deadline": str(approval_deadline),
        "wc_deadline": str(calc_wc_deadline(approval_deadline)),
        "sales_deadline": str(approval_deadline - timedelta(days=4)),
        "partner_success_deadline": str(approval_deadline - timedelta(days=1)),
        "deadline_override": True,
    }).eq("id", fixture_id).execute()

def clear_fixture_deadline_override(fixture_id: str, *, client: Client | None = None) -> None:
    from deadline_calc import calc_fixture_deadlines, deadlines_to_str
    cl = client or _client()
    fixture = cl.table("fixtures").select("id, team_id, match_date").eq("id", fixture_id).single().execute().data
    team = get_team(fixture["team_id"], client=cl)
    weekday_rules = get_team_deadline_weekdays(fixture["team_id"], client=cl)
    holidays_raw = get_holidays(client=cl)
    holiday_dates = [date.fromisoformat(h["date"]) for h in holidays_raw]
    match_date = date.fromisoformat(fixture["match_date"])
    deadlines = deadlines_to_str(calc_fixture_deadlines(match_date, team, weekday_rules, holiday_dates))
    cl.table("fixtures").update({**deadlines, "deadline_override": False}).eq("id", fixture_id).execute()
```

- [ ] **Step 4: Update `get_fixture_by_feed_event_id` to also return `approval_deadline`**

In `db.py`, find:

```python
def get_fixture_by_feed_event_id(feed_event_id: str, *, client: Client | None = None) -> dict | None:
    cl = client or _client()
    result = (
        cl.table("fixtures")
        .select("id, match_date, match_time, away_team")
        .eq("feed_event_id", feed_event_id)
        .execute()
    )
    return result.data[0] if result.data else None
```

Replace with:

```python
def get_fixture_by_feed_event_id(feed_event_id: str, *, client: Client | None = None) -> dict | None:
    cl = client or _client()
    result = (
        cl.table("fixtures")
        .select("id, match_date, match_time, away_team, approval_deadline")
        .eq("feed_event_id", feed_event_id)
        .execute()
    )
    return result.data[0] if result.data else None
```

- [ ] **Step 5: Rewrite `recalculate_future_deadlines`**

Find:

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

Replace with:

```python
def recalculate_future_deadlines(*, client: Client | None = None) -> int:
    """Recalculate approval/wc/sales/partner-success deadlines for all future fixtures
    that aren't manually overridden. Called after holidays are added or removed, or
    after the one-off weekday-rule import. Returns count of updated fixtures."""
    from deadline_calc import calc_fixture_deadlines, deadlines_to_str
    import datetime
    cl = client or _client()
    today = str(datetime.date.today())
    holidays_raw = get_holidays(client=cl)
    holiday_dates = [datetime.date.fromisoformat(h["date"]) for h in holidays_raw]
    teams = get_teams(client=cl)
    team_by_id = {t["id"]: t for t in teams}
    weekday_map = get_deadline_weekdays_by_team(client=cl)
    future = (
        cl.table("fixtures")
        .select("id, team_id, match_date, deadline_override")
        .gte("match_date", today)
        .execute()
        .data
    )
    count = 0
    for f in future:
        if f.get("deadline_override"):
            continue
        team = team_by_id.get(f["team_id"], {"deadline_days": 3, "deadline_active": True})
        weekday_rules = weekday_map.get(f["team_id"], {})
        match_date = datetime.date.fromisoformat(f["match_date"])
        deadlines = deadlines_to_str(calc_fixture_deadlines(match_date, team, weekday_rules, holiday_dates))
        cl.table("fixtures").update(deadlines).eq("id", f["id"]).execute()
        count += 1
    return count
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd DeadlinesTracker && python -m pytest tests/test_db.py -v`
Expected: all PASS

- [ ] **Step 7: Run the full suite to confirm no regressions**

Run: `cd DeadlinesTracker && python -m pytest tests/ -q`
Expected: all pass (Task 4 hasn't touched the sync modules yet, so their existing tests are unaffected by this task)

- [ ] **Step 8: Commit**

```bash
cd DeadlinesTracker
git add db.py tests/test_db.py
git commit -m "feat: add weekday-rule and deadline-override read/write functions"
```

---

### Task 4: Wire the new calculation into all sync modules and `app.py`

**Files:**
- Modify: `opta_sync.py`, `ical_sync.py`, `api_football_sync.py`, `app.py`
- Test: `tests/test_opta_sync.py`, `tests/test_ical_sync.py`, `tests/test_api_football_sync.py`

**Interfaces:**
- Consumes: `deadline_calc.calc_fixture_deadlines`, `deadline_calc.deadlines_to_str` (Task 2); `db.get_deadline_weekdays_by_team`, `db.get_overridden_feed_event_ids`, `db.get_team_deadline_weekdays`, `db.set_fixture_deadline_override`, `db.clear_fixture_deadline_override` (Task 3).
- Produces: `sync_team(team, holidays, weekday_rules=None, overridden_ids=None)` in all three sync modules (new optional params, default `{}`/`set()` so existing 2-arg calls are unaffected).

- [ ] **Step 1: Update `opta_sync.py`**

Change the import at the top:

```python
from deadline_calc import calc_all_deadlines
```

to:

```python
from deadline_calc import calc_fixture_deadlines, deadlines_to_str
```

Change the `sync_team` signature:

```python
def sync_team(team: dict, holidays: list[date]) -> dict:
```

to:

```python
def sync_team(
    team: dict,
    holidays: list[date],
    weekday_rules: dict[int, int] | None = None,
    overridden_ids: set[str] | None = None,
) -> dict:
```

Right after the `if not team.get("feed_team_id"):` guard (still inside `sync_team`, before the Opta config lookup), add:

```python
    weekday_rules = weekday_rules or {}
    overridden_ids = overridden_ids or set()
```

Inside the loop, find:

```python
        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)

        raw_date = m["date"]
        match_time_utc = raw_date[11:16] if len(raw_date) > 10 and raw_date[10] == " " else None
        utc_offset = m.get("utc_offset") or None

        fixture = {
            "team_id": team["id"],
            "away_team": away_name,
            "match_date": str(match_date),
            "match_time": match_time_utc,
            "match_utc_offset": utc_offset,
            "approval_deadline": str(deadlines["approval_deadline"]),
            "wc_deadline": str(deadlines["wc_deadline"]),
            "sales_deadline": str(deadlines["sales_deadline"]),
            "partner_success_deadline": str(deadlines["partner_success_deadline"]),
            "season": team["season"],
            "source": "opta",
            "feed_event_id": m["game_id"],
        }
```

Replace with:

```python
        if m["game_id"] in overridden_ids:
            deadline_fields = {}
        else:
            deadlines = calc_fixture_deadlines(match_date, team, weekday_rules, holidays)
            deadline_fields = deadlines_to_str(deadlines)

        raw_date = m["date"]
        match_time_utc = raw_date[11:16] if len(raw_date) > 10 and raw_date[10] == " " else None
        utc_offset = m.get("utc_offset") or None

        fixture = {
            "team_id": team["id"],
            "away_team": away_name,
            "match_date": str(match_date),
            "match_time": match_time_utc,
            "match_utc_offset": utc_offset,
            **deadline_fields,
            "season": team["season"],
            "source": "opta",
            "feed_event_id": m["game_id"],
        }
```

Change `sync_all_opta_teams`:

```python
def sync_all_opta_teams() -> dict[str, dict]:
    """Sync all teams with feed_source='opta'. Returns {team_name: stats_dict}."""
    holidays_raw = db.get_holidays()
    holidays = [date.fromisoformat(h["date"]) for h in holidays_raw]
    teams = [t for t in db.get_teams() if t.get("feed_source") == "opta"]
    results: dict[str, dict] = {}
    for team in teams:
        try:
            results[team["name"]] = sync_team(team, holidays)
        except (ConnectionError, PermissionError, ValueError) as e:
            results[team["name"]] = {"error": str(e)}
    return results
```

to:

```python
def sync_all_opta_teams() -> dict[str, dict]:
    """Sync all teams with feed_source='opta'. Returns {team_name: stats_dict}."""
    holidays_raw = db.get_holidays()
    holidays = [date.fromisoformat(h["date"]) for h in holidays_raw]
    weekday_map = db.get_deadline_weekdays_by_team()
    overridden_ids = db.get_overridden_feed_event_ids()
    teams = [t for t in db.get_teams() if t.get("feed_source") == "opta"]
    results: dict[str, dict] = {}
    for team in teams:
        try:
            results[team["name"]] = sync_team(team, holidays, weekday_map.get(team["id"], {}), overridden_ids)
        except (ConnectionError, PermissionError, ValueError) as e:
            results[team["name"]] = {"error": str(e)}
    return results
```

- [ ] **Step 2: Update `ical_sync.py`**

Change the import:

```python
from deadline_calc import calc_all_deadlines
```

to:

```python
from deadline_calc import calc_fixture_deadlines, deadlines_to_str
```

Change the `sync_team` signature:

```python
def sync_team(team: dict, holidays: list[date]) -> tuple[dict, list[dict], list[dict]]:
```

to:

```python
def sync_team(
    team: dict,
    holidays: list[date],
    weekday_rules: dict[int, int] | None = None,
    overridden_ids: set[str] | None = None,
) -> tuple[dict, list[dict], list[dict]]:
```

Right after the `if not slug:` guard (still inside `sync_team`, before `events = _fetch_events(...)`), add:

```python
    weekday_rules = weekday_rules or {}
    overridden_ids = overridden_ids or set()
```

Find:

```python
        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)

        # Check for existing fixture to detect reschedules
        existing = db.get_fixture_by_feed_event_id(game_id) if game_id else None
        is_new = existing is None
        is_rescheduled = (
            not is_new and
            (str(existing["match_date"]) != str(match_date) or
             (existing.get("match_time") or "") != (match_time or ""))
        )

        fixture = {
            "team_id": team["id"],
            "away_team": away_name,
            "match_date": str(match_date),
            "match_time": match_time,
            "match_utc_offset": "+00:00" if match_time else None,
            "approval_deadline": str(deadlines["approval_deadline"]),
            "wc_deadline": str(deadlines["wc_deadline"]),
            "sales_deadline": str(deadlines["sales_deadline"]),
            "partner_success_deadline": str(deadlines["partner_success_deadline"]),
            "season": team["season"],
            "source": "ical",
            "feed_event_id": game_id,
            "venue": team.get("default_venue") if is_new else existing.get("venue"),
        }
        fid = db.upsert_fixture(fixture)
        if is_new:
            db.create_upload_statuses_for_fixture(fid, team["id"])

        notification_data = {
            "home_team": team["name"],
            "away_team": away_name,
            "match_date": str(match_date),
            "competition": team.get("competition") or "",
            "venue": team.get("default_venue") or "",
            "approval_deadline": str(deadlines["approval_deadline"]),
            "cup_warning": cup_warning,
        }
```

Replace with:

```python
        # Check for existing fixture to detect reschedules
        existing = db.get_fixture_by_feed_event_id(game_id) if game_id else None
        is_new = existing is None
        is_rescheduled = (
            not is_new and
            (str(existing["match_date"]) != str(match_date) or
             (existing.get("match_time") or "") != (match_time or ""))
        )

        if game_id in overridden_ids:
            deadline_fields = {}
            display_approval_deadline = existing.get("approval_deadline") if existing else None
        else:
            deadlines = calc_fixture_deadlines(match_date, team, weekday_rules, holidays)
            deadline_fields = deadlines_to_str(deadlines)
            display_approval_deadline = deadline_fields["approval_deadline"]

        fixture = {
            "team_id": team["id"],
            "away_team": away_name,
            "match_date": str(match_date),
            "match_time": match_time,
            "match_utc_offset": "+00:00" if match_time else None,
            **deadline_fields,
            "season": team["season"],
            "source": "ical",
            "feed_event_id": game_id,
            "venue": team.get("default_venue") if is_new else existing.get("venue"),
        }
        fid = db.upsert_fixture(fixture)
        if is_new:
            db.create_upload_statuses_for_fixture(fid, team["id"])

        notification_data = {
            "home_team": team["name"],
            "away_team": away_name,
            "match_date": str(match_date),
            "competition": team.get("competition") or "",
            "venue": team.get("default_venue") or "",
            "approval_deadline": display_approval_deadline,
            "cup_warning": cup_warning,
        }
```

Change `sync_all_ical_teams`:

```python
def sync_all_ical_teams() -> dict[str, dict]:
    """Sync all iCal teams and send email notification if anything changed."""
    holidays_raw = db.get_holidays()
    holidays = [date.fromisoformat(h["date"]) for h in holidays_raw]
    teams = [t for t in db.get_teams() if t.get("feed_source") == "ical"]

    all_new: list[dict] = []
    all_rescheduled: list[dict] = []
    results: dict[str, dict] = {}

    for team in teams:
        try:
            stats, new_f, resched_f = sync_team(team, holidays)
        except (ConnectionError, PermissionError, ValueError) as e:
            results[team["name"]] = {"error": str(e)}
            continue
        results[team["name"]] = stats
        all_new.extend(new_f)
        all_rescheduled.extend(resched_f)

    if all_new or all_rescheduled:
        from notifications import send_sync_summary
        send_sync_summary(all_new, all_rescheduled)

    return results
```

to:

```python
def sync_all_ical_teams() -> dict[str, dict]:
    """Sync all iCal teams and send email notification if anything changed."""
    holidays_raw = db.get_holidays()
    holidays = [date.fromisoformat(h["date"]) for h in holidays_raw]
    weekday_map = db.get_deadline_weekdays_by_team()
    overridden_ids = db.get_overridden_feed_event_ids()
    teams = [t for t in db.get_teams() if t.get("feed_source") == "ical"]

    all_new: list[dict] = []
    all_rescheduled: list[dict] = []
    results: dict[str, dict] = {}

    for team in teams:
        try:
            stats, new_f, resched_f = sync_team(team, holidays, weekday_map.get(team["id"], {}), overridden_ids)
        except (ConnectionError, PermissionError, ValueError) as e:
            results[team["name"]] = {"error": str(e)}
            continue
        results[team["name"]] = stats
        all_new.extend(new_f)
        all_rescheduled.extend(resched_f)

    if all_new or all_rescheduled:
        from notifications import send_sync_summary
        send_sync_summary(all_new, all_rescheduled)

    return results
```

- [ ] **Step 3: Update `api_football_sync.py`**

Change the import:

```python
from deadline_calc import calc_all_deadlines
```

to:

```python
from deadline_calc import calc_fixture_deadlines, deadlines_to_str
```

Change the `sync_team` signature:

```python
def sync_team(team: dict, holidays: list[date]) -> dict:
```

to:

```python
def sync_team(
    team: dict,
    holidays: list[date],
    weekday_rules: dict[int, int] | None = None,
    overridden_ids: set[str] | None = None,
) -> dict:
```

Right after the `if not team.get("feed_team_id"):` guard (still inside `sync_team`, before the API-Football config lookup), add:

```python
    weekday_rules = weekday_rules or {}
    overridden_ids = overridden_ids or set()
```

Find:

```python
        away_name = item["teams"]["away"]["name"]
        game_id = f"apif_{item['fixture']['id']}"

        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)

        fixture = {
            "team_id": team["id"],
            "away_team": away_name,
            "match_date": str(match_date),
            "match_time": match_time,
            "match_utc_offset": utc_offset,
            "approval_deadline": str(deadlines["approval_deadline"]),
            "wc_deadline": str(deadlines["wc_deadline"]),
            "sales_deadline": str(deadlines["sales_deadline"]),
            "partner_success_deadline": str(deadlines["partner_success_deadline"]),
            "season": team["season"],
            "source": "api_football",
            "feed_event_id": game_id,
        }
```

Replace with:

```python
        away_name = item["teams"]["away"]["name"]
        game_id = f"apif_{item['fixture']['id']}"

        if game_id in overridden_ids:
            deadline_fields = {}
        else:
            deadlines = calc_fixture_deadlines(match_date, team, weekday_rules, holidays)
            deadline_fields = deadlines_to_str(deadlines)

        fixture = {
            "team_id": team["id"],
            "away_team": away_name,
            "match_date": str(match_date),
            "match_time": match_time,
            "match_utc_offset": utc_offset,
            **deadline_fields,
            "season": team["season"],
            "source": "api_football",
            "feed_event_id": game_id,
        }
```

Change `sync_all_api_football_teams`:

```python
def sync_all_api_football_teams() -> dict[str, dict]:
    holidays_raw = db.get_holidays()
    holidays = [date.fromisoformat(h["date"]) for h in holidays_raw]
    teams = [t for t in db.get_teams() if t.get("feed_source") == "api_football"]
    results: dict[str, dict] = {}
    for team in teams:
        try:
            results[team["name"]] = sync_team(team, holidays)
        except (ConnectionError, PermissionError, ValueError) as e:
            results[team["name"]] = {"error": str(e)}
    return results
```

to:

```python
def sync_all_api_football_teams() -> dict[str, dict]:
    holidays_raw = db.get_holidays()
    holidays = [date.fromisoformat(h["date"]) for h in holidays_raw]
    weekday_map = db.get_deadline_weekdays_by_team()
    overridden_ids = db.get_overridden_feed_event_ids()
    teams = [t for t in db.get_teams() if t.get("feed_source") == "api_football"]
    results: dict[str, dict] = {}
    for team in teams:
        try:
            results[team["name"]] = sync_team(team, holidays, weekday_map.get(team["id"], {}), overridden_ids)
        except (ConnectionError, PermissionError, ValueError) as e:
            results[team["name"]] = {"error": str(e)}
    return results
```

- [ ] **Step 4: Fix the existing `sync_all_*` tests that break from the new calls**

These three sync modules' `sync_all_*` functions now also call `db.get_deadline_weekdays_by_team()` and `db.get_overridden_feed_event_ids()`, which aren't mocked in some existing tests, and one local `side_effect` helper per file has a fixed 2-argument signature that breaks when called with the two new arguments.

In `tests/test_opta_sync.py`, replace `test_sync_all_opta_teams_isolates_per_team_errors`:

```python
def test_sync_all_opta_teams_isolates_per_team_errors():
    good_team = {**TEAM, "name": "Good Team"}
    bad_team = {**TEAM, "name": "Bad Team", "feed_team_id": ""}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[good_team, bad_team]), \
         patch("opta_sync.sync_team") as mock_sync:
        def side_effect(team, holidays):
            if team["name"] == "Good Team":
                return {"upserted": 1}
            raise ValueError("No feed_team_id set")
        mock_sync.side_effect = side_effect

        results = sync_all_opta_teams()

    assert results["Good Team"] == {"upserted": 1}
    assert "error" in results["Bad Team"]
```

with:

```python
def test_sync_all_opta_teams_isolates_per_team_errors():
    good_team = {**TEAM, "name": "Good Team"}
    bad_team = {**TEAM, "name": "Bad Team", "feed_team_id": ""}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[good_team, bad_team]), \
         patch("opta_sync.sync_team") as mock_sync:
        def side_effect(team, holidays, weekday_rules=None, overridden_ids=None):
            if team["name"] == "Good Team":
                return {"upserted": 1}
            raise ValueError("No feed_team_id set")
        mock_sync.side_effect = side_effect

        results = sync_all_opta_teams()

    assert results["Good Team"] == {"upserted": 1}
    assert "error" in results["Bad Team"]
```

And replace `test_sync_all_opta_teams_filters_by_feed_source`:

```python
def test_sync_all_opta_teams_filters_by_feed_source():
    opta_team = {**TEAM, "feed_source": "opta"}
    other_team = {**TEAM, "name": "Other", "feed_source": "ical"}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[opta_team, other_team]), \
         patch("opta_sync.sync_team", return_value={"upserted": 0}) as mock_sync:
        sync_all_opta_teams()

    assert mock_sync.call_count == 1
```

with:

```python
def test_sync_all_opta_teams_filters_by_feed_source():
    opta_team = {**TEAM, "feed_source": "opta"}
    other_team = {**TEAM, "name": "Other", "feed_source": "ical"}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[opta_team, other_team]), \
         patch("opta_sync.sync_team", return_value={"upserted": 0}) as mock_sync:
        sync_all_opta_teams()

    assert mock_sync.call_count == 1
```

Then append two new tests to `tests/test_opta_sync.py`:

```python
def test_sync_team_skips_deadline_fields_for_overridden_fixture():
    future = str(date.today() + timedelta(days=10))
    matches = [{"game_id": "77", "date": f"{future} 19:00:00", "home_team_id": "tHOME", "away_team_id": "tAWAY", "utc_offset": ""}]

    with patch("opta_sync.get_opta_config", return_value=FAKE_CFG), \
         patch("opta_sync._fetch_and_parse", return_value=(matches, {}, "")), \
         patch("db.upsert_fixture", return_value="fid-1") as mock_upsert, \
         patch("db.create_upload_statuses_for_fixture"):
        sync_team(TEAM, [], {}, {"77"})

    fixture = mock_upsert.call_args[0][0]
    assert "approval_deadline" not in fixture
    assert "wc_deadline" not in fixture
    assert "sales_deadline" not in fixture
    assert "partner_success_deadline" not in fixture


def test_sync_all_opta_teams_passes_weekday_map_and_overridden_ids():
    team = {**TEAM}
    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={"team-1": {5: 2}}), \
         patch("db.get_overridden_feed_event_ids", return_value={"evt-x"}), \
         patch("db.get_teams", return_value=[team]), \
         patch("opta_sync.sync_team", return_value={"upserted": 0}) as mock_sync:
        sync_all_opta_teams()

    mock_sync.assert_called_once_with(team, [], {5: 2}, {"evt-x"})
```

In `tests/test_ical_sync.py`, replace `test_sync_all_ical_teams_isolates_per_team_errors`:

```python
def test_sync_all_ical_teams_isolates_per_team_errors():
    good_team = {**TEAM, "name": "Good Team"}
    bad_team = {**TEAM, "name": "Bad Team", "feed_team_id": ""}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[good_team, bad_team]), \
         patch("ical_sync.sync_team") as mock_sync:
        def side_effect(team, holidays):
            if team["name"] == "Good Team":
                return {"upserted": 1}, [{"away_team": "X"}], []
            raise ValueError("No feed_team_id set")
        mock_sync.side_effect = side_effect

        with patch("notifications.send_sync_summary") as mock_notify:
            results = sync_all_ical_teams()

    assert results["Good Team"] == {"upserted": 1}
    assert "error" in results["Bad Team"]
    mock_notify.assert_called_once_with([{"away_team": "X"}], [])
```

with:

```python
def test_sync_all_ical_teams_isolates_per_team_errors():
    good_team = {**TEAM, "name": "Good Team"}
    bad_team = {**TEAM, "name": "Bad Team", "feed_team_id": ""}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[good_team, bad_team]), \
         patch("ical_sync.sync_team") as mock_sync:
        def side_effect(team, holidays, weekday_rules=None, overridden_ids=None):
            if team["name"] == "Good Team":
                return {"upserted": 1}, [{"away_team": "X"}], []
            raise ValueError("No feed_team_id set")
        mock_sync.side_effect = side_effect

        with patch("notifications.send_sync_summary") as mock_notify:
            results = sync_all_ical_teams()

    assert results["Good Team"] == {"upserted": 1}
    assert "error" in results["Bad Team"]
    mock_notify.assert_called_once_with([{"away_team": "X"}], [])
```

And replace `test_sync_all_ical_teams_filters_by_feed_source` and `test_sync_all_ical_teams_skips_notification_when_nothing_changed`:

```python
def test_sync_all_ical_teams_filters_by_feed_source():
    ical_team = {**TEAM, "feed_source": "ical"}
    other_team = {**TEAM, "name": "Other", "feed_source": "opta"}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[ical_team, other_team]), \
         patch("ical_sync.sync_team", return_value=({"upserted": 0}, [], [])) as mock_sync:
        sync_all_ical_teams()

    assert mock_sync.call_count == 1


def test_sync_all_ical_teams_skips_notification_when_nothing_changed():
    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[TEAM]), \
         patch("ical_sync.sync_team", return_value=({"upserted": 0}, [], [])), \
         patch("notifications.send_sync_summary") as mock_notify:
        sync_all_ical_teams()

    mock_notify.assert_not_called()
```

with:

```python
def test_sync_all_ical_teams_filters_by_feed_source():
    ical_team = {**TEAM, "feed_source": "ical"}
    other_team = {**TEAM, "name": "Other", "feed_source": "opta"}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[ical_team, other_team]), \
         patch("ical_sync.sync_team", return_value=({"upserted": 0}, [], [])) as mock_sync:
        sync_all_ical_teams()

    assert mock_sync.call_count == 1


def test_sync_all_ical_teams_skips_notification_when_nothing_changed():
    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[TEAM]), \
         patch("ical_sync.sync_team", return_value=({"upserted": 0}, [], [])), \
         patch("notifications.send_sync_summary") as mock_notify:
        sync_all_ical_teams()

    mock_notify.assert_not_called()
```

Then append a new test to `tests/test_ical_sync.py`:

```python
def test_sync_team_skips_deadline_fields_for_overridden_fixture():
    future = datetime.now(tz.utc) + timedelta(days=10)
    content = _ics([{"summary": "LA Galaxy - Portland", "dtstart": future, "uid": "evt-1"}])
    existing = {"id": "fid-1", "match_date": "2020-01-01", "match_time": None, "away_team": "Portland",
                "venue": "", "approval_deadline": "2020-01-05"}
    with patch("ical_sync.requests.get", return_value=_fake_response(content)), \
         patch("db.get_fixture_by_feed_event_id", return_value=existing), \
         patch("db.upsert_fixture", return_value="fid-1") as mock_upsert, \
         patch("db.create_upload_statuses_for_fixture"):
        sync_team(TEAM, [], {}, {"ical_evt-1"})

    fixture = mock_upsert.call_args[0][0]
    assert "approval_deadline" not in fixture
    assert "wc_deadline" not in fixture
```

In `tests/test_api_football_sync.py`, replace `test_sync_all_api_football_teams_isolates_per_team_errors`:

```python
def test_sync_all_api_football_teams_isolates_per_team_errors():
    good_team = {**TEAM, "name": "Good Team"}
    bad_team = {**TEAM, "name": "Bad Team", "feed_team_id": ""}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[good_team, bad_team]), \
         patch("api_football_sync.sync_team") as mock_sync:
        def side_effect(team, holidays):
            if team["name"] == "Good Team":
                return {"upserted": 1}
            raise ValueError("No feed_team_id set")
        mock_sync.side_effect = side_effect

        results = sync_all_api_football_teams()

    assert results["Good Team"] == {"upserted": 1}
    assert "error" in results["Bad Team"]
```

with:

```python
def test_sync_all_api_football_teams_isolates_per_team_errors():
    good_team = {**TEAM, "name": "Good Team"}
    bad_team = {**TEAM, "name": "Bad Team", "feed_team_id": ""}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[good_team, bad_team]), \
         patch("api_football_sync.sync_team") as mock_sync:
        def side_effect(team, holidays, weekday_rules=None, overridden_ids=None):
            if team["name"] == "Good Team":
                return {"upserted": 1}
            raise ValueError("No feed_team_id set")
        mock_sync.side_effect = side_effect

        results = sync_all_api_football_teams()

    assert results["Good Team"] == {"upserted": 1}
    assert "error" in results["Bad Team"]
```

And replace `test_sync_all_api_football_teams_filters_by_feed_source`:

```python
def test_sync_all_api_football_teams_filters_by_feed_source():
    apif_team = {**TEAM, "feed_source": "api_football"}
    other_team = {**TEAM, "name": "Other", "feed_source": "ical"}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_teams", return_value=[apif_team, other_team]), \
         patch("api_football_sync.sync_team", return_value={"upserted": 0}) as mock_sync:
        sync_all_api_football_teams()

    assert mock_sync.call_count == 1
```

with:

```python
def test_sync_all_api_football_teams_filters_by_feed_source():
    apif_team = {**TEAM, "feed_source": "api_football"}
    other_team = {**TEAM, "name": "Other", "feed_source": "ical"}

    with patch("db.get_holidays", return_value=[]), \
         patch("db.get_deadline_weekdays_by_team", return_value={}), \
         patch("db.get_overridden_feed_event_ids", return_value=set()), \
         patch("db.get_teams", return_value=[apif_team, other_team]), \
         patch("api_football_sync.sync_team", return_value={"upserted": 0}) as mock_sync:
        sync_all_api_football_teams()

    assert mock_sync.call_count == 1
```

- [ ] **Step 5: Run the three sync test files to verify everything passes**

Run: `cd DeadlinesTracker && python -m pytest tests/test_opta_sync.py tests/test_ical_sync.py tests/test_api_football_sync.py -v`
Expected: all PASS

- [ ] **Step 6: Update `app.py`'s add-fixture and manual-edit forms**

In `_show_add_form`, find:

```python
    from datetime import date as _date
    from deadline_calc import calc_all_deadlines
    import db as _db
```

Replace with:

```python
    from datetime import date as _date
    from deadline_calc import calc_fixture_deadlines, deadlines_to_str
    import db as _db
```

Find:

```python
        holidays_raw = _db.get_holidays()
        holidays = [_date.fromisoformat(h["date"]) for h in holidays_raw]
        deadlines = calc_all_deadlines(match_date, team["deadline_days"], holidays)
        st.caption(
            f"Approval deadline: **{deadlines['approval_deadline']}** | "
            f"WC deadline: **{deadlines['wc_deadline']}**"
        )
```

Replace with:

```python
        holidays_raw = _db.get_holidays()
        holidays = [_date.fromisoformat(h["date"]) for h in holidays_raw]
        weekday_rules = _db.get_team_deadline_weekdays(team["id"])
        deadlines = deadlines_to_str(calc_fixture_deadlines(match_date, team, weekday_rules, holidays))
        st.caption(
            f"Approval deadline: **{deadlines['approval_deadline']}** | "
            f"WC deadline: **{deadlines['wc_deadline']}**"
        )
```

Find the fixture dict built a few lines below in the same function:

```python
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

Replace with (deadlines are already strings from `deadlines_to_str`, so drop the redundant `str()` calls):

```python
                fixture = {
                    "team_id": team["id"],
                    "away_team": away.strip(),
                    "match_date": str(match_date),
                    "match_time": _match_time,
                    "approval_deadline": deadlines["approval_deadline"],
                    "wc_deadline": deadlines["wc_deadline"],
                    "sales_deadline": deadlines["sales_deadline"],
                    "partner_success_deadline": deadlines["partner_success_deadline"],
                    "season": team["season"],
                    "source": "manual",
                }
```

In `_show_detail`'s "✏️ Edit fixture" expander, find:

```python
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

Replace with:

```python
                from datetime import date as _date
                from deadline_calc import calc_fixture_deadlines, deadlines_to_str
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
                weekday_rules = db.get_team_deadline_weekdays(fixture["team_id"])
                new_deadlines = deadlines_to_str(calc_fixture_deadlines(new_date, team_data, weekday_rules, holidays))
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
                        new_deadlines["approval_deadline"], new_deadlines["wc_deadline"],
                        new_deadlines["sales_deadline"], new_deadlines["partner_success_deadline"],
                        match_time,
                    )
                    st.cache_data.clear()
                    st.rerun()
```

- [ ] **Step 7: Add the "Deadline override" control to `_show_detail`**

In `_show_detail`, find the end of the notes section (right before the `if fixture.get("source") == "manual":` block):

```python
        notes = st.text_area(
            "Notes",
            value=fixture.get("notes", ""),
            key=f"notes_{fixture['id']}",
            height=120,
        )
        if st.button("Save notes", key=f"save_notes_{fixture['id']}"):
            db.update_fixture_notes(fixture["id"], notes)
            st.cache_data.clear()
            st.rerun()

        st.divider()

        st.markdown("**Upload statuses**")
```

Insert the new control between the notes section and the "Upload statuses" section:

```python
        notes = st.text_area(
            "Notes",
            value=fixture.get("notes", ""),
            key=f"notes_{fixture['id']}",
            height=120,
        )
        if st.button("Save notes", key=f"save_notes_{fixture['id']}"):
            db.update_fixture_notes(fixture["id"], notes)
            st.cache_data.clear()
            st.rerun()

        st.divider()

        st.markdown("**📅 Deadline override**")
        current_approval = fixture.get("approval_deadline")
        if fixture.get("deadline_override"):
            st.caption(f"Manually overridden. Approval deadline: **{current_approval}**")
        else:
            st.caption(f"Computed. Approval deadline: **{current_approval}**")
        override_date = st.date_input(
            "Approval deadline" if fixture.get("deadline_override") else "Override approval deadline",
            value=_date.fromisoformat(current_approval) if current_approval else _date.today(),
            key=f"override_{fixture['id']}",
        )
        col_set, col_clear = st.columns(2)
        with col_set:
            if st.button("Set override", key=f"override_set_{fixture['id']}"):
                db.set_fixture_deadline_override(fixture["id"], override_date)
                st.cache_data.clear()
                st.rerun()
        with col_clear:
            if fixture.get("deadline_override") and st.button("Clear override", key=f"override_clear_{fixture['id']}"):
                db.clear_fixture_deadline_override(fixture["id"])
                st.cache_data.clear()
                st.rerun()

        st.divider()

        st.markdown("**Upload statuses**")
```

`_show_detail` already has `from datetime import date as _date` at the top of the module (`app.py`'s first line) — no new import needed for `_date` here.

- [ ] **Step 8: Run the full suite to confirm no regressions**

Run: `cd DeadlinesTracker && python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
cd DeadlinesTracker
git add opta_sync.py ical_sync.py api_football_sync.py app.py tests/test_opta_sync.py tests/test_ical_sync.py tests/test_api_football_sync.py
git commit -m "feat: wire weekday-rule deadline calc and manual override into sync and UI"
```

---

### Task 5: Admin UI — weekday grid and active-deal checkbox

**Files:**
- Modify: `pages/1_Admin.py`

**Interfaces:**
- Consumes: `db.get_team_deadline_weekdays`, `db.set_team_deadline_weekdays` (Task 3). `teams.deadline_active` is read/written through the existing `db.upsert_team`/`db.get_teams` (Task 1's schema column, no new db.py function needed for the flag itself since it's just another key in the team payload dict).

No automated test for this task — `pages/1_Admin.py` has no existing test coverage (matching the app's own precedent: the Admin page's `deadline_days` editor introduced in the original build was never covered by an AppTest either). Verified manually in the Manual Verification section below.

- [ ] **Step 1: Replace the `deadline_days` input with the weekday grid and active checkbox**

In `pages/1_Admin.py`, find:

```python
    with st.form("team_form"):
        name = st.text_input("Team name", value=editing.get("name", ""))
        deadline_days = st.number_input(
            "Deadline days (working days before match)", min_value=1, max_value=14,
            value=editing.get("deadline_days", 3)
        )
        _feed_sources = ["manual", "opta", "statsperform", "api_football", "ical"]
```

Replace with:

```python
    with st.form("team_form"):
        name = st.text_input("Team name", value=editing.get("name", ""))
        deadline_active = st.checkbox("Active deal", value=editing.get("deadline_active", True))
        deadline_days = st.number_input(
            "Fallback (days before match, used when no weekday rule is set below)",
            min_value=1, max_value=21,
            value=editing.get("deadline_days", 3)
        )
        st.markdown("**Deadline weekday by match weekday** (leave 'No rule' to use the fallback above)")
        _WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        _weekday_options = ["No rule"] + _WEEKDAY_LABELS
        existing_rules = db.get_team_deadline_weekdays(editing["id"]) if editing.get("id") else {}
        weekday_cols = st.columns(7)
        selected_rules: dict[int, int] = {}
        for i, wd_label in enumerate(_WEEKDAY_LABELS):
            with weekday_cols[i]:
                current_rule = existing_rules.get(i)
                default_label = _WEEKDAY_LABELS[current_rule] if current_rule is not None else "No rule"
                choice = st.selectbox(
                    wd_label, _weekday_options,
                    index=_weekday_options.index(default_label),
                    key=f"wd_{i}",
                )
                if choice != "No rule":
                    selected_rules[i] = _WEEKDAY_LABELS.index(choice)
        _feed_sources = ["manual", "opta", "statsperform", "api_football", "ical"]
```

- [ ] **Step 2: Save the new fields on submit**

Find:

```python
    if submitted and name.strip():
        payload = {
            "name": name.strip(),
            "competition": competition.strip() or None,
            "deadline_days": int(deadline_days),
            "feed_source": feed_source,
            "feed_competition_id": feed_competition_id.strip() or None,
            "feed_team_id": feed_team_id.strip() or None,
            "season": season.strip(),
            "default_venue": default_venue.strip() or None,
        }
        if editing.get("id"):
            payload["id"] = editing["id"]
        team_id = db.upsert_team(payload)
        db.set_team_platforms(team_id, selected_platforms)
```

Replace with:

```python
    if submitted and name.strip():
        payload = {
            "name": name.strip(),
            "competition": competition.strip() or None,
            "deadline_days": int(deadline_days),
            "deadline_active": deadline_active,
            "feed_source": feed_source,
            "feed_competition_id": feed_competition_id.strip() or None,
            "feed_team_id": feed_team_id.strip() or None,
            "season": season.strip(),
            "default_venue": default_venue.strip() or None,
        }
        if editing.get("id"):
            payload["id"] = editing["id"]
        team_id = db.upsert_team(payload)
        db.set_team_deadline_weekdays(team_id, selected_rules)
        db.set_team_platforms(team_id, selected_platforms)
```

- [ ] **Step 3: Run the full suite to confirm no regressions**

Run: `cd DeadlinesTracker && python -m pytest tests/ -q`
Expected: all pass (this task adds no new test file, so this just confirms the edit didn't break an import elsewhere)

- [ ] **Step 4: Commit**

```bash
cd DeadlinesTracker
git add pages/1_Admin.py
git commit -m "feat: add weekday-rule grid and active-deal checkbox to Admin team editor"
```

---

### Task 6: One-off import script — `Team Deadline Matrix.xlsx` → `team_deadline_weekdays`

**Files:**
- Create: `_import_deadline_weekdays.py`
- Test: `tests/test_import_deadline_weekdays.py`

**Interfaces:**
- Consumes: `db.get_teams`, `db.set_team_deadline_weekdays`, `db.set_team_deadline_active` (Task 3).
- Produces: `parse_deadline_matrix(rows: list[tuple]) -> tuple[dict[str, dict[int, int]], set[str]]` (pure, tested) and a `main()` that performs the real import (not unit-tested — same as the existing untested one-off scripts `_import_teams.py`/`_setup_ical_teams.py`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_import_deadline_weekdays.py`:

```python
from _import_deadline_weekdays import parse_deadline_matrix, ALIASES


def test_parse_deadline_matrix_extracts_weekday_rules():
    # Column order in the sheet: Team, Source, Sat, Sun, Mon, Tue, Wed, Thu, Fri
    rows = [
        ("Aston Villa", "2026-27 fixtures (gospel)", "Wed (n=14/14)", "Wed", "Wed", "Thu", "Fri (n=3/3)", "Mon", "Tue"),
    ]
    rules, expired = parse_deadline_matrix(rows)
    # Sat(5)->Wed(2), Sun(6)->Wed(2), Mon(0)->Wed(2), Tue(1)->Thu(3), Wed(2)->Fri(4), Thu(3)->Mon(0), Fri(4)->Tue(1)
    assert rules["Aston Villa"] == {5: 2, 6: 2, 0: 2, 1: 3, 2: 4, 3: 0, 4: 1}
    assert expired == set()


def test_parse_deadline_matrix_skips_unparseable_cells():
    rows = [
        ("Some Team", "source", "–", "", None, "Tue (n=2/2)", "–", "–", "–"),
    ]
    rules, expired = parse_deadline_matrix(rows)
    assert rules["Some Team"] == {1: 1}


def test_parse_deadline_matrix_marks_expired_teams_and_skips_rules():
    rows = [
        ("Leyton Orient", "Expired — no active deal", "Expired", "Expired", "Expired",
         "Expired", "Expired", "Expired", "Expired"),
    ]
    rules, expired = parse_deadline_matrix(rows)
    assert expired == {"Leyton Orient"}
    assert "Leyton Orient" not in rules


def test_parse_deadline_matrix_resolves_aliases():
    rows = [
        ("London Stadium", "2026-27 fixtures (gospel)", "Wed (n=15/16)", None, None, "Thu (n=4/4)", None, None, None),
    ]
    rules, expired = parse_deadline_matrix(rows)
    assert rules["West Ham"] == {5: 2, 1: 3}


def test_parse_deadline_matrix_skips_blank_team_name_row():
    rows = [(None, None, None, None, None, None, None, None, None)]
    rules, expired = parse_deadline_matrix(rows)
    assert rules == {}
    assert expired == set()


def test_aliases_cover_known_name_mismatches():
    assert ALIASES == {
        "Millwall FC": "Millwall",
        "Houston Dynamo": "Houston",
        "Atlanta United FC": "Atlanta United",
        "FC Copenhagen": "FCK",
        "London Stadium": "West Ham",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd DeadlinesTracker && python -m pytest tests/test_import_deadline_weekdays.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '_import_deadline_weekdays'`

- [ ] **Step 3: Write the script**

Create `_import_deadline_weekdays.py`:

```python
"""One-off script to import Team Deadline Matrix.xlsx into team_deadline_weekdays
and mark expired teams inactive. Run once: python _import_deadline_weekdays.py"""

WEEKDAY_NAMES = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

# (column index in the raw row tuple, Python weekday it represents).
# Sheet column order is Team, Source, Sat, Sun, Mon, Tue, Wed, Thu, Fri.
_MATRIX_COLUMNS = [(2, 5), (3, 6), (4, 0), (5, 1), (6, 2), (7, 3), (8, 4)]

ALIASES = {
    "Millwall FC": "Millwall",
    "Houston Dynamo": "Houston",
    "Atlanta United FC": "Atlanta United",
    "FC Copenhagen": "FCK",
    "London Stadium": "West Ham",
}


def _parse_weekday_cell(value) -> int | None:
    """Extract the leading weekday name from a cell like 'Wed (n=14/14)'.
    Returns None if the cell is empty or doesn't start with a recognized weekday name."""
    if not value:
        return None
    token = str(value).split(" ", 1)[0].strip()
    return WEEKDAY_NAMES.get(token)


def parse_deadline_matrix(rows: list[tuple]) -> tuple[dict[str, dict[int, int]], set[str]]:
    """Parse Team Deadline Matrix rows (as yielded by
    ws.iter_rows(min_row=5, values_only=True)) into (rules_by_team_name,
    expired_team_names). Team names are resolved through ALIASES. Cells that
    don't parse to a recognized weekday name are skipped, not guessed."""
    rules: dict[str, dict[int, int]] = {}
    expired: set[str] = set()
    for row in rows:
        matrix_name = row[0]
        if not matrix_name:
            continue
        team_name = ALIASES.get(matrix_name, matrix_name)
        source = str(row[1] or "")
        if source.startswith("Expired"):
            expired.add(team_name)
            continue
        for col_idx, match_weekday in _MATRIX_COLUMNS:
            deadline_weekday = _parse_weekday_cell(row[col_idx])
            if deadline_weekday is not None:
                rules.setdefault(team_name, {})[match_weekday] = deadline_weekday
    return rules, expired


def main() -> None:
    import openpyxl
    import db

    wb = openpyxl.load_workbook("Team Deadline Matrix.xlsx", data_only=True)
    ws = wb["Deadline Matrix"]
    rows = list(ws.iter_rows(min_row=5, values_only=True))
    rules, expired = parse_deadline_matrix(rows)

    teams_by_name = {t["name"]: t["id"] for t in db.get_teams()}

    applied = skipped_no_team = 0

    for team_name in expired:
        team_id = teams_by_name.get(team_name)
        if team_id is None:
            print(f"  SKIP (expired, no matching team) {team_name}")
            skipped_no_team += 1
            continue
        db.set_team_deadline_active(team_id, False)
        print(f"  INACTIVE {team_name}")

    for team_name, weekday_rules in rules.items():
        team_id = teams_by_name.get(team_name)
        if team_id is None:
            print(f"  SKIP (no matching team) {team_name}: {weekday_rules}")
            skipped_no_team += 1
            continue
        db.set_team_deadline_weekdays(team_id, weekday_rules)
        print(f"  SET {team_name}: {len(weekday_rules)} weekday rule(s)")
        applied += 1

    print(
        f"\n{applied} team(s) given weekday rules, {len(expired)} marked inactive, "
        f"{skipped_no_team} skipped (no matching team in the app)."
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd DeadlinesTracker && python -m pytest tests/test_import_deadline_weekdays.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `cd DeadlinesTracker && python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd DeadlinesTracker
git add _import_deadline_weekdays.py tests/test_import_deadline_weekdays.py
git commit -m "feat: add one-off Team Deadline Matrix import script"
```

---

### Task 7: One-off script — import per-fixture gospel deadlines as overrides for the current season

**Added after the final whole-branch review** (2026-08-20): a real cross-check of every confirmed `team_deadline_weekdays` rule against the actual per-fixture gaps in the gospel sheet found that 49 of 114 checked team+weekday combos (43%) have a real historical gap **over 7 days** — often a highly consistent one (e.g. Bristol City's Sat→Fri deadline is always 8 days, not 1; Denver Broncos' Mon→Mon is always 14 days). `calc_approval_deadline_from_weekday` always picks the *nearest* prior occurrence of the deadline weekday (max 7 days back), so for these combos it computes a deadline exactly one extra week too **late** — the dangerous direction. This is a real flaw in the weekday-only rule (a weekday alone can't distinguish "last Friday" from "the Friday a week earlier"), not a theoretical concern.

Tom's decision: "The app should match the spreadsheet for this year." Rather than redesigning the weekday-rule schema/calc (Tasks 1-3/5/6, already reviewed and approved) to add a day-count/weeks-back dimension, this task uses the already-built, already-tested manual override mechanism (Task 3's `db.set_fixture_deadline_override`) as the delivery vehicle: for every fixture the app already has that also appears in the gospel sheet (`MASTER_Deadline Sheet_2026.xlsx`, `2026-27` sheet — matched by team name, resolved through the same `ALIASES` map as Task 6, and match date), set that fixture's real, human-verified approval deadline as an override. This makes every current-season fixture's deadline exactly match the spreadsheet regardless of whether its weekday-rule combo happens to be one of the 49 wrong ones — and since it's a real override, it's permanently protected from being recomputed by any future sync or by `recalculate_future_deadlines`.

The weekday-rule feature (Tasks 1-6) is not being removed or reworked — it remains the best-available fallback for any fixture the gospel sheet doesn't cover (a new fixture added after this import runs, a fixture for a future season, etc.). It is still known to be wrong for ~43% of confirmed combos in that fallback role; this is a documented, accepted limitation for now, not a resolved one — flagged again in Manual Verification below.

**Files:**
- Create: `_import_gospel_deadlines.py`
- Test: `tests/test_import_gospel_deadlines.py`

**Interfaces:**
- Consumes: `db.get_teams`, `db.get_upcoming_fixtures(days=None)`, `db.set_fixture_deadline_override` (Task 3); `_import_deadline_weekdays.ALIASES` (Task 6, reused rather than duplicated).
- Produces: `match_gospel_rows(gospel_rows, app_fixtures) -> list[tuple[str, date]]` (pure, tested — returns `(fixture_id, approval_deadline)` pairs) and a `main()` that performs the real import (not unit-tested, same convention as `_import_teams.py`/`_import_deadline_weekdays.py`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_import_gospel_deadlines.py`:

```python
from datetime import date
from _import_gospel_deadlines import match_gospel_rows


def test_match_gospel_rows_matches_by_resolved_team_name_and_date():
    gospel_rows = [
        (date(2026, 8, 22), "London Stadium", "Arsenal", date(2026, 8, 14)),
    ]
    app_fixtures = [
        {"id": "fix-1", "team_id": "t1", "match_date": "2026-08-22"},
    ]
    teams_by_id = {"t1": "West Ham"}
    result = match_gospel_rows(gospel_rows, app_fixtures, teams_by_id)
    assert result == [("fix-1", date(2026, 8, 14))]


def test_match_gospel_rows_skips_when_no_fixture_matches_date():
    gospel_rows = [
        (date(2026, 8, 22), "Aston Villa", "Arsenal", date(2026, 8, 19)),
    ]
    app_fixtures = [
        {"id": "fix-1", "team_id": "t1", "match_date": "2026-08-29"},
    ]
    teams_by_id = {"t1": "Aston Villa"}
    result = match_gospel_rows(gospel_rows, app_fixtures, teams_by_id)
    assert result == []


def test_match_gospel_rows_skips_when_team_not_in_app():
    gospel_rows = [
        (date(2026, 8, 22), "Some Untracked Team", "Arsenal", date(2026, 8, 19)),
    ]
    app_fixtures = [
        {"id": "fix-1", "team_id": "t1", "match_date": "2026-08-22"},
    ]
    teams_by_id = {"t1": "Aston Villa"}
    result = match_gospel_rows(gospel_rows, app_fixtures, teams_by_id)
    assert result == []


def test_match_gospel_rows_skips_row_with_no_approval_deadline():
    gospel_rows = [
        (date(2026, 8, 22), "Aston Villa", "Arsenal", None),
    ]
    app_fixtures = [
        {"id": "fix-1", "team_id": "t1", "match_date": "2026-08-22"},
    ]
    teams_by_id = {"t1": "Aston Villa"}
    result = match_gospel_rows(gospel_rows, app_fixtures, teams_by_id)
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd DeadlinesTracker && python3 -m pytest tests/test_import_gospel_deadlines.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '_import_gospel_deadlines'`

- [ ] **Step 3: Write the script**

Create `_import_gospel_deadlines.py`:

```python
"""One-off script to make every current-season fixture's deadline match the
real, human-verified value in MASTER_Deadline Sheet_2026.xlsx, via the
manual-override mechanism, rather than trusting the weekday-rule calc (which
is known wrong for ~43% of confirmed team+weekday combos — see Task 7 in
docs/superpowers/plans/2026-08-20-weekday-deadline-rules.md).
Run once: python _import_gospel_deadlines.py"""
from datetime import date, datetime

from _import_deadline_weekdays import ALIASES


def _to_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def match_gospel_rows(
    gospel_rows: list[tuple],
    app_fixtures: list[dict],
    teams_by_id: dict[str, str],
) -> list[tuple[str, date]]:
    """gospel_rows: (match_date, team_home, team_away, approval_deadline) tuples
    from the gospel sheet. app_fixtures: {id, team_id, match_date} dicts already
    in the app. teams_by_id: {team_id: team_name} for every app team. Returns
    (fixture_id, approval_deadline) pairs for every gospel row that resolves to
    a real app team (through ALIASES) and matches an app fixture on the same
    match date."""
    fixtures_by_key: dict[tuple[str, date], str] = {}
    for f in app_fixtures:
        match_date = _to_date(f["match_date"])
        if match_date is None:
            continue
        team_name = teams_by_id.get(f["team_id"])
        if team_name is None:
            continue
        fixtures_by_key[(team_name, match_date)] = f["id"]

    results: list[tuple[str, date]] = []
    for match_date, team_home, _team_away, approval_deadline in gospel_rows:
        md = _to_date(match_date)
        ad = _to_date(approval_deadline)
        if md is None or ad is None:
            continue
        team_name = ALIASES.get(team_home, team_home)
        fixture_id = fixtures_by_key.get((team_name, md))
        if fixture_id is not None:
            results.append((fixture_id, ad))
    return results


def main() -> None:
    import openpyxl
    import db

    wb = openpyxl.load_workbook("MASTER_Deadline Sheet_2026.xlsx", data_only=True)
    ws = wb["2026-27"]
    gospel_rows = [
        (row[0], row[1], row[2], row[3])
        for row in ws.iter_rows(min_row=2, values_only=True)
        if row[0] and row[1]
    ]

    teams = db.get_teams()
    teams_by_id = {t["id"]: t["name"] for t in teams}
    app_fixtures = db.get_upcoming_fixtures(days=None)

    matches = match_gospel_rows(gospel_rows, app_fixtures, teams_by_id)
    for fixture_id, approval_deadline in matches:
        db.set_fixture_deadline_override(fixture_id, approval_deadline)

    print(
        f"\n{len(matches)} fixture(s) overridden to match the gospel sheet "
        f"out of {len(gospel_rows)} gospel row(s) and {len(app_fixtures)} app fixture(s)."
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd DeadlinesTracker && python3 -m pytest tests/test_import_gospel_deadlines.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `cd DeadlinesTracker && python3 -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd DeadlinesTracker
git add _import_gospel_deadlines.py tests/test_import_gospel_deadlines.py
git commit -m "feat: add one-off script to override fixtures with gospel-sheet deadlines"
```

---

## Manual verification (after all tasks, and after Task 1 Step 6 has been applied to the live database)

- [ ] Confirm the live database migration from Task 1 Step 6 has been applied (query `select deadline_active from teams limit 1;` and `select deadline_override from fixtures limit 1;` in the Supabase SQL editor — both should succeed with no error).
- [ ] Run `python _import_deadline_weekdays.py` from the `DeadlinesTracker` directory (with `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` set, as usual) against the live database. Confirm the printed summary shows Aston Villa, West Ham, and the other Opta teams getting weekday rules. **Correction from the plan's original draft:** the real spreadsheet has 9 expired/no-active-deal teams, not 6 — FC Dallas, Houston Dynamo, Leeds United, Leyton Orient, Peterborough Utd, Reading FC, Sheffield United, Swansea City, Wycombe Wanderers (confirmed with Tom on 2026-08-20 that all 9 are genuinely expired). Confirm all 9 are marked inactive.
- [ ] Run `python _import_gospel_deadlines.py` from the `DeadlinesTracker` directory against the live database (after the weekday-rule import above, so the override correctly takes precedence). Confirm the printed summary's overridden count is close to the ~544 existing fixtures (allowing for any gospel rows that don't resolve to a tracked team, or app fixtures the gospel sheet doesn't cover — read the printed count, don't assume it's exactly 544).
- [ ] In the Supabase SQL editor, spot-check a Bristol City or Denver Broncos fixture (two of the teams confirmed to have a >7-day real gap that the weekday-rule calc alone would get wrong) and confirm `deadline_override = true` and `approval_deadline` matches the gospel sheet exactly, not the weekday-rule-computed value.
- [ ] **Known accepted limitation, not yet resolved:** the weekday-rule fallback (Tasks 1-6) is still wrong for ~43% of confirmed team+weekday combos when it's the only data available (any fixture the gospel-sheet import in this task doesn't cover — e.g. one added after this import runs, or next season's fixtures once this year's gospel sheet is out of date). Revisit with Tom whether that needs the "weeks back"/day-offset redesign discussed during this review before relying on the weekday-rule fallback again for a new season.
- [ ] In the Supabase SQL editor, spot-check one row: `select match_weekday, deadline_weekday from team_deadline_weekdays td join teams t on t.id = td.team_id where t.name = 'West Ham';` — expect `5 -> 2` (Sat match -> Wed deadline) and `1 -> 3` (Tue match -> Thu deadline) among the results.
- [ ] Run `db.recalculate_future_deadlines()` once (via a one-off `python -c "import db; print(db.recalculate_future_deadlines())"` from the `DeadlinesTracker` directory, or by adding/removing a holiday in the Admin page's Holidays tab, which already triggers it) to backfill all 544 existing fixtures under the new logic. Note the returned count.
- [ ] In the Supabase SQL editor, confirm the 6 expired teams' fixtures now have `approval_deadline is null`: `select count(*) from fixtures f join teams t on t.id = f.team_id where t.deadline_active = false and f.approval_deadline is not null;` — expect `0`.
- [ ] Run `streamlit run app.py`, open a West Ham fixture's detail panel, and confirm the Approval Deadline shown matches the weekday rule (e.g. a Saturday fixture should show a Wednesday deadline 3 days earlier).
- [ ] In the same detail panel, use the new "📅 Deadline override" control to set a different approval deadline, save, and confirm: the fixture's WC/Sales/Partner Success deadlines update to match the new date, the tracker table reflects the change, and re-running `db.recalculate_future_deadlines()` does **not** revert it. Then click "Clear override" and confirm it snaps back to the weekday-rule-computed value.
- [ ] Click "🔄 Sync from iCal" (or trigger an Opta/API-Football sync for a team that has one) and confirm a previously-overridden fixture's deadline is unchanged after the sync completes (check the same fixture in the tracker before and after).
- [ ] In the Admin page's Teams tab, open a team with partial weekday coverage (e.g. Huddersfield Town AFC) and confirm the grid shows "No rule" for Wednesday and a real weekday for the others; change one weekday's rule, save, and confirm `db.get_team_deadline_weekdays` reflects the change (spot-check via the Supabase SQL editor or by reopening the team in Admin).
- [ ] Report back to Tom which teams/weekdays are still on the flat fallback after the import (any partial gaps, e.g. Huddersfield's Wednesday) so he knows what's still unresolved.
