# Eleven Sports Media Brand Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the Eleven Sports Media dark brand theme to both DeadlinesTracker and DataCollector via `.streamlit/config.toml`, with no application code changes.

**Architecture:** Streamlit 1.56 reads theme colours from a `[theme]` table in `.streamlit/config.toml`. This is a config-only change — one identical `[theme]` block is written to each repo's `config.toml`, then verified with `streamlit config show` (confirms the TOML parses and the values are picked up) and a headless `AppTest` boot check (confirms neither app raises on startup with the new config in place). Visual colour correctness is verified manually per the spec, since that requires human judgement, not automation.

**Tech Stack:** Streamlit 1.56.0 (both repos), `streamlit.testing.v1.AppTest` for headless boot verification.

## Global Constraints

- Full spec: `docs/superpowers/specs/2026-08-10-eleven-brand-theme-design.md` (present in both repos, identical content).
- Exact `[theme]` values (from the spec) — copy verbatim, do not alter:
  ```toml
  [theme]
  base = "dark"
  primaryColor = "#2CCCD3"
  backgroundColor = "#101820"
  secondaryBackgroundColor = "#3B3F44"
  textColor = "#FFFFFF"
  linkColor = "#2CCCD3"
  borderColor = "#7C878E"
  dataframeBorderColor = "#7C878E"

  [theme.sidebar]
  backgroundColor = "#3B3F44"
  ```
- Chrome only: do not modify any application code, do not touch `redColor`/`greenColor`/`yellowColor`/`blueColor` (Streamlit's built-in alert colours), do not touch any hardcoded colours in `tracker.py`, `notifications.py`, or DataCollector's `app.py` (stat cards, possession bars, W/L/D colours, pitch backgrounds). Those are semantic/status colours, explicitly out of scope per the spec.
- DataCollector's existing `.streamlit/config.toml` has a `[browser]` section (`gatherUsageStats = false`) that must be preserved, not replaced.
- DeadlinesTracker has no `.streamlit/config.toml` yet — only `.streamlit/secrets.toml.example` — so this creates a new file.

---

### Task 1: DeadlinesTracker theme config

**Files:**
- Create: `.streamlit/config.toml` (repo root: `C:\Users\TomMitchell\OneDrive - Eleven Sports Media Limited\PC\Documents 1\ClaudeCode\DeadlinesTracker\.streamlit\config.toml`)

**Interfaces:**
- Consumes: nothing (first task, no dependencies).
- Produces: nothing consumed by later tasks — Task 3's boot check reads this file indirectly by launching the app, but doesn't import anything from it.

- [ ] **Step 1: Create the config file**

Create `.streamlit/config.toml` with exactly this content:

```toml
[theme]
base = "dark"
primaryColor = "#2CCCD3"
backgroundColor = "#101820"
secondaryBackgroundColor = "#3B3F44"
textColor = "#FFFFFF"
linkColor = "#2CCCD3"
borderColor = "#7C878E"
dataframeBorderColor = "#7C878E"

[theme.sidebar]
backgroundColor = "#3B3F44"
```

- [ ] **Step 2: Verify Streamlit picks up the theme**

Run (from the DeadlinesTracker repo root):
```bash
python -m streamlit config show | grep -E "^(base|primaryColor|backgroundColor|secondaryBackgroundColor|textColor|linkColor|borderColor|dataframeBorderColor)\s*="
```

Expected output (9 lines — the 8 top-level `[theme]` keys plus `[theme.sidebar]`'s `backgroundColor` repeating the key name at the end):
```
base = "dark"
primaryColor = "#2CCCD3"
backgroundColor = "#101820"
secondaryBackgroundColor = "#3B3F44"
textColor = "#FFFFFF"
linkColor = "#2CCCD3"
borderColor = "#7C878E"
dataframeBorderColor = "#7C878E"
backgroundColor = "#3B3F44"
```

If any line is missing or shows a default/commented value instead, the TOML failed to parse — check for typos (missing quotes, wrong section header) before proceeding.

- [ ] **Step 3: Commit**

```bash
git add .streamlit/config.toml
git commit -m "feat: add Eleven Sports Media dark theme"
```

---

### Task 2: DataCollector theme config

**Files:**
- Modify: `.streamlit/config.toml` (repo root: `C:\Users\TomMitchell\OneDrive - Eleven Sports Media Limited\PC\Documents 1\ClaudeCode\DataCollector\.streamlit\config.toml`)

**Interfaces:**
- Consumes: nothing (independent of Task 1 — different repo).
- Produces: nothing consumed by later tasks except Task 3's boot check, which launches the app and reads this file indirectly.

**Current file content (must be preserved, not replaced):**
```toml
[browser]
gatherUsageStats = false
```

- [ ] **Step 1: Add the theme section**

Edit `.streamlit/config.toml` so the full file reads exactly:

```toml
[browser]
gatherUsageStats = false

[theme]
base = "dark"
primaryColor = "#2CCCD3"
backgroundColor = "#101820"
secondaryBackgroundColor = "#3B3F44"
textColor = "#FFFFFF"
linkColor = "#2CCCD3"
borderColor = "#7C878E"
dataframeBorderColor = "#7C878E"

[theme.sidebar]
backgroundColor = "#3B3F44"
```

- [ ] **Step 2: Verify Streamlit picks up the theme**

Run (from the DataCollector repo root):
```bash
python -m streamlit config show | grep -E "^(base|primaryColor|backgroundColor|secondaryBackgroundColor|textColor|linkColor|borderColor|dataframeBorderColor|gatherUsageStats)\s*="
```

Expected output (10 lines — the `[browser]` key, the 8 top-level `[theme]` keys, and `[theme.sidebar]`'s `backgroundColor` repeating the key name at the end):
```
gatherUsageStats = false
base = "dark"
primaryColor = "#2CCCD3"
backgroundColor = "#101820"
secondaryBackgroundColor = "#3B3F44"
textColor = "#FFFFFF"
linkColor = "#2CCCD3"
borderColor = "#7C878E"
dataframeBorderColor = "#7C878E"
backgroundColor = "#3B3F44"
```

If `gatherUsageStats = false` is missing, the `[browser]` section was accidentally dropped — restore it.

- [ ] **Step 3: Commit**

```bash
git add .streamlit/config.toml
git commit -m "feat: add Eleven Sports Media dark theme"
```

---

### Task 3: Headless boot verification for both apps

**Files:**
- Create: `tests/test_theme_config.py` (DeadlinesTracker repo)
- No new file in DataCollector — its existing test suite doesn't use `AppTest`, and adding that pattern there is out of scope for a theme change. Task 3's DataCollector check (Step 3 below) is a one-off manual command, not a committed test.

**Interfaces:**
- Consumes: Task 1's `.streamlit/config.toml` (DeadlinesTracker) and Task 2's `.streamlit/config.toml` (DataCollector) — both must exist on disk for this task's checks to be meaningful.
- Produces: nothing — this is the last task.

A malformed `[theme]` table (bad TOML syntax, wrong nesting) can make Streamlit fail at startup. `AppTest` boots the app in-process and exposes any exception raised during the run, which is a fast, automatable way to confirm the new config didn't break app startup. It does not check colours — that needs a real browser, covered by the manual checklist in Step 4.

- [ ] **Step 1: Write the DeadlinesTracker boot-check test**

Create `tests/test_theme_config.py`:

```python
from streamlit.testing.v1 import AppTest

def test_app_boots_with_theme_config():
    at = AppTest.from_file("app.py")
    at.run(timeout=15)  # default 3s timeout is too short for first-run import overhead
    assert not at.exception
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/test_theme_config.py -v`

Expected: `PASSED` — if `at.exception` is truthy, print `at.exception` to see the actual error and fix the config (most likely cause: invalid TOML syntax from Task 1).

Note: this test needs `user_name` session state to get past DeadlinesTracker's name-prompt gate to reach the themed page content. If the assertion fails with the app stuck on the name prompt rather than an exception, that's expected behaviour, not a bug — the test only asserts "no crash," which still holds.

- [ ] **Step 3: Run the equivalent one-off check for DataCollector**

DataCollector's test suite doesn't use `AppTest`, so run this as a one-off command rather than adding a new test file:

```bash
cd "C:\Users\TomMitchell\OneDrive - Eleven Sports Media Limited\PC\Documents 1\ClaudeCode\DataCollector"
python -c "
from streamlit.testing.v1 import AppTest
at = AppTest.from_file('app.py')
at.run(timeout=15)
assert not at.exception, at.exception
print('DataCollector app.py booted cleanly with new theme config')
"
```

Expected output: `DataCollector app.py booted cleanly with new theme config`

- [ ] **Step 4: Manual visual checklist (human judgement required — not automatable)**

Launch each app locally and click through it, confirming text stays legible against the new dark backgrounds (including inside expanders, forms, and the sidebar), and that button text on Digital Blue buttons is readable:

**DeadlinesTracker** (`python -m streamlit run app.py`):
- Home page (fixture table, sidebar filters, Add Fixture form)
- Admin page (Teams/Platforms/Statuses/Holidays tabs) — confirm the DB-configurable status-pill colours are still readable against the new dark chrome
- Archive page
- Technical Plan page
- Confirm the overdue-row amber highlight in the fixture table is still readable

**DataCollector** (`python -m streamlit run app.py`):
- Main explorer page
- Stats Perform page
- College Season page
- Note (expected, not a bug): stat cards render via custom HTML/CSS outside the Streamlit theme system, so some card backgrounds may show as light boxes against the new dark page — this was flagged as an accepted, out-of-scope cosmetic side effect in the design spec, not something to fix here.

- [ ] **Step 5: Commit**

```bash
git add tests/test_theme_config.py
git commit -m "test: add headless boot check for the new theme config"
```

(Commit from DeadlinesTracker only — Step 3's DataCollector check wasn't saved as a file, so there's nothing to commit there.)
