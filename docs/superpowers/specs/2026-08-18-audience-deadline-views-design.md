# Audience-Specific Deadline Views Design

Date: 2026-08-18

## Problem

The deadline tracker has grown beyond its original single-audience use.
Three teams need it now, each with a different relationship to the real
deadline:

- **Delivery** (Tom's team): needs the actual, real `approval_deadline` —
  today's app, unchanged.
- **Partner Success**: communicates deadlines to external partners/clients,
  who need lead time to prepare artwork. Needs a deadline **1 day earlier**
  than the real one, plus which platforms/artwork types are needed for that
  fixture (they're telling partners *what* to prepare, not just *when*).
- **Sales**: needs their own, larger buffer — **4 days earlier** than the
  real deadline. Needs only minimal fixture info (team, match date, their
  deadline) — nothing else.

Sales must not be able to see the real `approval_deadline` at all. No login
system exists today and none is wanted for this — separation is achieved
architecturally (separate deployments that never fetch the real value), not
through authentication.

## Existing infrastructure this builds on

The app already computes deadlines correctly — this design extends that,
it doesn't replace it:

- `teams.deadline_days` (int, admin-editable via `pages/1_Admin.py`) — the
  real number of business days before match day, per team.
- `holidays` table — dates excluded when counting business days.
- `deadline_calc.calc_approval_deadline(match_date, deadline_days,
  holidays) -> date` — walks backward from match day, skipping weekends and
  holidays, until `deadline_days` business days are counted.
- `deadline_calc.calc_wc_deadline(approval_deadline) -> date` — Monday of
  the approval deadline's week.
- `fixtures` table already has an unused-for-this-purpose `sales_deadline
  date` column, currently a **manually-entered** date picker in `app.py`
  (both the "Add fixture" and "Edit fixture" forms) — populated by Delivery
  staff by hand, not computed. This design repurposes it to be
  auto-computed instead, per Tom's decision, and removes the manual entry
  UI.
- Five call sites independently call `calc_approval_deadline` +
  `calc_wc_deadline` together today: `api_football_sync.py`,
  `ical_sync.py`, `opta_sync.py`, `db.py`'s `recalculate_future_deadlines`,
  and `app.py` (twice — the add-fixture and edit-fixture forms). This
  existing duplication is a real problem this design's own changes make
  worse if left alone (each site would need the same two new computations
  added by hand); consolidating it is in scope, not a side quest.

`deadline_days` accuracy: separate real-world data task, out of scope for
this build. Tom has already derived reliable per-team values from a full
historical season for many teams (a fixed days-before-match-day offset,
confirmed by testing directly against real history, with UK bank holidays
and Christmas treated as known exceptions rather than noise) — updating
`teams.deadline_days` with those values is a data-entry step via the
existing Admin page, not new code.

## What's being built

### 1. Shared deadline calculation, consolidated

New `deadline_calc.calc_all_deadlines(match_date: date, deadline_days: int,
holidays: list[date]) -> dict` returning `{"approval_deadline": date,
"wc_deadline": date, "sales_deadline": date, "partner_success_deadline":
date}`. Internally: calls the existing `calc_approval_deadline` and
`calc_wc_deadline` unchanged, then `sales_deadline = approval_deadline -
timedelta(days=4)`, `partner_success_deadline = approval_deadline -
timedelta(days=1)` — plain calendar-day shifts off the already
holiday/weekend-aware real deadline, not a second business-day walk. (This
means a partner success or sales deadline can itself land on a weekend —
acceptable, since these are lead-time buffers for external parties, not
internal work-day deadlines for Eleven staff.)

All five existing call sites are updated to call this one function instead
of the two-function pair, and to write all four resulting dates back to the
fixture (adding `partner_success_deadline` to every `.update()`/`.insert()`
payload that currently writes `approval_deadline`/`wc_deadline`).

### 2. Schema change

New column: `fixtures.partner_success_deadline date` (nullable, matching
the existing `sales_deadline`/`wc_deadline` columns' shape). Added via a
migration in `supabase/schema.sql` plus a corresponding `alter table`
statement for the already-provisioned database.

### 3. Remove manual Sales Deadline entry

In `app.py`: delete the `st.date_input("Sales deadline (optional)", ...)`
widgets from both the "Add fixture" and "Edit fixture" forms, and stop
passing a manually-typed `sales_deadline` through `db.upsert_fixture`/
`db.update_fixture_manual` — it's now always the computed value, set
alongside `approval_deadline`/`wc_deadline` in the same call. Existing
fixtures with a manually-entered `sales_deadline` get overwritten the next
time `recalculate_future_deadlines` runs (already triggered today whenever
holidays are added/removed) — a one-time backfill covers the rest (see
Rollout below).

### 4. Two new restricted read queries in `db.py`

Two new functions, each with a `.select()` that structurally cannot return
`approval_deadline` or `wc_deadline` — the safety guarantee lives in the
query itself, not in page code remembering not to display a field:

- `get_sales_fixtures(days: int = 14) -> list[dict]`: selects only `id,
  away_team, match_date, sales_deadline, teams(name)`, upcoming fixtures
  only, ordered by `sales_deadline`.
- `get_partner_success_fixtures(days: int = 14) -> list[dict]`: selects
  `id, away_team, match_date, partner_success_deadline, teams(name),
  team_platforms(platforms(name))` (or equivalent join to list each team's
  active platforms) — same exclusion of the real deadline columns.

### 5. Two new standalone Streamlit apps

Not new pages under the existing `pages/` folder (that would put them in
the main app's sidebar navigation, discoverable from the Delivery app).
Two new top-level scripts in the same repo, each its own separate
`streamlit run` process on its own port, importing `db.py`/`config.py` as
shared library code the way `pages/*.py` already do, but never importing or
calling anything that touches `approval_deadline`/`wc_deadline`:

- `sales_view.py` — read-only. Table: Team, Away Team, Match Date, Sales
  Deadline. No edit controls, no notes, no platform/status detail.
- `partner_success_view.py` — read-only. Table: Team, Away Team, Match
  Date, Partner Success Deadline, Platforms needed. No edit controls, no
  notes, no internal delivery-status detail.

Both are genuinely separate deployments (own process, own URL/port) so
there's no shared navigation surface linking back to the Delivery app or
Admin page.

## Error handling

- If `db.get_holidays()` or the Supabase connection fails, the two new
  views show `st.error(...)` and stop — same pattern already used
  throughout `app.py`. No fixture data partially rendered without its
  deadline.
- If a fixture has no `sales_deadline`/`partner_success_deadline` yet
  (e.g., created before this change, not yet recalculated), show it with a
  blank/dash for that field rather than crashing — matches how the
  existing tracker already handles a blank `sales_deadline` today
  (`tracker.py:90`, `f.get("sales_deadline") or ""`).

## Rollout (manual steps, not code)

1. Run the migration to add `partner_success_deadline`.
2. Deploy the updated app/calc code.
3. Run `db.recalculate_future_deadlines()` once (already exposed via the
   Admin page's holiday-management flow, or callable directly) to backfill
   `sales_deadline`/`partner_success_deadline` on all existing future
   fixtures using the current `deadline_days` per team.
4. Update `teams.deadline_days` with the historically-derived values,
   team by team, via the existing Admin page — then re-run step 3 so the
   real deadlines reflect the corrected offsets.
5. Deploy `sales_view.py`/`partner_success_view.py` as their own processes,
   share their URLs with the relevant teams directly (not linked from
   anywhere in the main app).

## Testing

Same pattern as the existing `tests/` suite: `deadline_calc.py` gets pure
unit tests for `calc_all_deadlines` (given a match date/deadline_days/
holidays, asserts all four output dates); `db.py`'s two new query functions
get tests asserting the `.select()` string never contains
`approval_deadline`/`wc_deadline` as a substring (a cheap, durable
regression guard for the actual security property this design cares
about) plus that they return the right shape; the two new
`sales_view.py`/`partner_success_view.py` scripts get `AppTest`-based UI
tests confirming the rendered table only ever contains the intended
columns.
