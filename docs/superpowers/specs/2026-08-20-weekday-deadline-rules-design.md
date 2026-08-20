# Per-Team Weekday Deadline Rules Design

Date: 2026-08-20

## Problem

The app computes every fixture's deadline the same way: `deadline_days`
business days before match day, a single integer per team, currently `3`
for all 52 teams (never updated from its default). This is wrong — the
real rule, confirmed against a full season of historical data in
`Team Deadline Matrix.xlsx`, is **a fixed deadline weekday per match
weekday, per team** (e.g. Aston Villa: Saturday match → deadline Wed,
Tuesday match → deadline Thu), not a fixed day-count. Gaps between match
day and deadline range 2-21 days depending on team and match weekday — no
clean day-count formula fits.

544 fixtures already exist in the live `fixtures` table (all Opta-sourced
soccer teams), all carrying deadlines computed under the wrong flat-3-day
rule. This design fixes the calculation itself — both a one-time backfill
of those 544, and the shared logic every future sync (`opta_sync.py`,
`ical_sync.py`, `api_football_sync.py`, `app.py`, `db.py`) already funnels
through, so the fix doesn't regress on the next sync.

## Data reality (from `Team Deadline Matrix.xlsx` + gospel `MASTER_Deadline
Sheet_2026.xlsx`)

- **Confirmed rule available**: most Opta teams have a gospel-confirmed
  deadline weekday for most match weekdays.
- **West Ham — no data anywhere.** Zero rows in the gospel sheet, no row in
  the matrix, despite being the most active Opta team (24 fixtures). Same
  situation as the NBA teams before: there is nothing to derive a rule
  from. **Not guessing a number for this — West Ham stays on the old flat
  `deadline_days` fallback until Tom gets the real rule from whoever owns
  that account.**
- **Partial gaps**: some teams have confirmed data for most but not all 7
  match weekdays (e.g. Huddersfield Town has no Wednesday data). Those
  specific team+weekday combinations also stay on the flat fallback rather
  than interpolating.
- **Name aliases** between `teams.name` and the matrix's `Team` column
  (matrix name → app name): "Millwall FC" → Millwall, "Houston Dynamo" →
  Houston, "Atlanta United FC" → Atlanta United, "FC Copenhagen" → FCK.
  Resolved via an explicit alias map in the migration script, not fuzzy
  matching.
- **Expired teams**: Leyton Orient, Peterborough Utd, Sheffield United,
  Swansea City, Wycombe Wanderers, FC Dallas are flagged "no active deal"
  in the matrix (a decision Tom already made when building it). Their 123
  existing fixtures get their deadline fields **blanked**, not computed
  under either rule.

## What's being built

### 1. Schema: `team_deadline_weekdays`

```sql
create table team_deadline_weekdays (
    team_id uuid not null references teams(id) on delete cascade,
    match_weekday integer not null check (match_weekday between 0 and 6),
    deadline_weekday integer not null check (deadline_weekday between 0 and 6),
    primary key (team_id, match_weekday)
);
```

`0` = Monday .. `6` = Sunday (Python `date.weekday()` convention, matching
the rest of the codebase). One row per team per match weekday with
confirmed data. A missing row means "no confirmed rule" — the team+weekday
falls back to `teams.deadline_days`.

Also add `teams.deadline_active boolean not null default true` — set
`false` for the 6 expired teams. When false, `calc_all_deadlines` returns
all four deadline fields as `None` regardless of any weekday rule or
fallback.

### 2. Calculation logic (`deadline_calc.py`)

New function:

```python
def calc_approval_deadline_from_weekday(match_date: date, deadline_weekday: int) -> date:
    """Most recent occurrence of deadline_weekday strictly before match_date."""
    delta = (match_date.weekday() - deadline_weekday) % 7
    return match_date - timedelta(days=delta or 7)
```

`delta or 7` handles the case where the deadline weekday equals the match
weekday — that must mean "the same weekday, previous week" (7 days back),
not zero days back, since a deadline can't fall on match day itself.

No holiday-shifting is applied on this path. The matrix data was derived
purely from observed weekday patterns with no holiday adjustment visible
in the historical sample (confirmed in an earlier session — no holiday
fell within the sampled date range either way). Adding a holiday shift now
would be introducing a rule that was never actually observed, not encoding
one. `wc_deadline` continues to be `calc_wc_deadline(approval_deadline)`
unchanged (Monday of the approval deadline's week) — this still applies
cleanly to a weekday-derived date.

`calc_all_deadlines` gets a new required parameter — the team's full
row (or at least `deadline_days`, `deadline_active`, and its
`team_deadline_weekdays` rows) instead of a bare `deadline_days` int — and
picks per-fixture:

1. If `deadline_active` is `False`: all four fields → `None`.
2. Else if a `team_deadline_weekdays` row exists for this match's weekday:
   use `calc_approval_deadline_from_weekday`.
3. Else: fall back to the existing `calc_approval_deadline` (flat
   `deadline_days`, business-day walk, holiday-aware) — today's behavior,
   unchanged, for West Ham and any partial-gap weekday.

`sales_deadline`/`partner_success_deadline` stay calendar-day offsets off
whichever `approval_deadline` resulted (`-4`/`-1` days), same as today —
except when step 1 applies, in which case they're also `None`.

### 3. Update the 5 call sites

`opta_sync.py`, `ical_sync.py`, `api_football_sync.py`, `app.py` (both
add/edit forms), and `db.py`'s `recalculate_future_deadlines` all currently
call `calc_all_deadlines(match_date, team["deadline_days"], holidays)`.
Each needs its `team` dict to also carry `deadline_active` and a lookup of
that team's `team_deadline_weekdays` rows (fetched once per sync run
alongside `db.get_teams()`, same pattern already used for `holidays`).

### 4. Admin UI (`pages/1_Admin.py`)

Replace the single `st.number_input("Deadline days", ...)` with a 7-column
grid (Mon-Sun), each a dropdown of weekday names plus a "no data" option,
pre-filled from `team_deadline_weekdays`. Saving writes/deletes rows in
that table for the edited team. The old `deadline_days` number input stays
alongside as the explicit fallback value, relabelled "Fallback (days
before match, used when no weekday rule is set)" — still needed for West
Ham and partial gaps. Add an "Active deal" checkbox bound to
`teams.deadline_active`.

### 5. Migration + one-time backfill (manual steps, not app code)

1. `alter table` for `team_deadline_weekdays` and `teams.deadline_active`.
2. One-off script (not part of the app, run once): parses
   `Team Deadline Matrix.xlsx`, resolves the 4 known aliases, skips
   "Expired" rows and cells with no data (`'�'`/empty), inserts the
   remaining team+weekday→weekday rows. Sets `deadline_active = false` for
   the 6 expired teams.
3. Deploy the updated `deadline_calc.py`/5 call sites/Admin page.
4. Run `db.recalculate_future_deadlines()` (already exists, extended per
   above) once to backfill all 544 existing fixtures under the new logic.
5. Report back which teams/weekdays are still on the flat fallback (West
   Ham entirely, plus any partial gaps) so Tom knows what's still
   unresolved — not silently indistinguishable from a confirmed rule.

## Error handling

- Migration script: if a matrix row's weekday cell text doesn't parse to a
  recognized weekday name (typo, unexpected format), skip that cell and
  log it rather than guessing — same "don't guess" stance as the West Ham
  gap.
- `calc_all_deadlines`: if `team_deadline_weekdays` lookup is missing
  entirely for a team (e.g. brand new team added after migration, no
  weekday data yet), that's just case 3 (flat fallback) — no special
  handling needed, it's the existing default path.

## Testing

Extends the existing `tests/test_deadline_calc.py` pattern:
`calc_approval_deadline_from_weekday` gets unit tests covering same-weekday
wrap-to-7-days, a mid-week gap, and a case identical to a known matrix row
(e.g. Aston Villa Sat→Wed) as a regression anchor. `calc_all_deadlines`
gets tests for all three branches (inactive team → all `None`; weekday
rule present; weekday rule absent → flat fallback unchanged from today's
behavior). The migration script gets a test asserting it never inserts a
row for an "Expired" team or an unparseable cell. `db.recalculate_future_deadlines`'s
existing test (`test_recalculate_future_deadlines_writes_all_four_fields`)
gets extended to cover an inactive team producing `None`s.
