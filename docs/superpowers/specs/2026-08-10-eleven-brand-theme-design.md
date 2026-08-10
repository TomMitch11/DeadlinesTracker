# Eleven Sports Media brand theme — design

**Date:** 2026-08-10
**Repos affected:** DeadlinesTracker (this repo) and DataCollector (sibling repo)

## Goal

Apply the Eleven Sports Media brand palette to both internal Streamlit
tools so they're visually identifiable as company tools rather than
default Streamlit apps.

## Context

Both apps run on Streamlit 1.56.0, which supports a rich `[theme]` block
in `.streamlit/config.toml`. Neither app currently has a `[theme]`
section configured, so both render with Streamlit's stock light theme.
This is a config-only change — no application code changes are required
to achieve it.

DeadlinesTracker has no `.streamlit/config.toml` yet (only a
`secrets.toml.example`). DataCollector has a `.streamlit/config.toml`
with a `[browser]` section only; it gains a `[theme]` section alongside
the existing one.

## Brand palette

| Name | Hex |
|---|---|
| Slate Grey | `#3B3F44` |
| Digital Blue | `#2CCCD3` |
| Pulse Purple | `#8A69D4` |
| Locally Yellow | `#EDFF00` |
| Off Black | `#101820` |
| Mid Grey | `#7C878E` |
| Light Grey | `#D0D3D4` |
| White | `#FFFFFF` |

## Approach

Dark theme. Digital Blue was the initial choice for primary accent
(confirmed with the user over Pulse Purple and Locally Yellow), but
after seeing it live the user found it didn't work and asked to
switch to Mid Grey instead — the theme now uses Mid Grey as the
primary accent throughout.

Identical `[theme]` block applied to both repos:

```toml
[theme]
base = "dark"
primaryColor = "#7C878E"             # Mid Grey — buttons, active widgets, sliders
backgroundColor = "#101820"          # Off Black — main content background
secondaryBackgroundColor = "#3B3F44" # Slate Grey — widget backgrounds (inputs, expanders)
textColor = "#FFFFFF"                # White
linkColor = "#7C878E"                # Mid Grey
borderColor = "#7C878E"              # Mid Grey
dataframeBorderColor = "#7C878E"     # Mid Grey

[theme.sidebar]
backgroundColor = "#3B3F44"          # Slate Grey — visually distinct from the Off Black main content
```

### Scope: chrome only

Only the Streamlit UI shell is themed: page/sidebar background, widget
background, text, links, primary accent, and borders. Explicitly out of
scope, left at their existing values:

- **Streamlit's built-in semantic colours** (`redColor`, `greenColor`,
  `yellowColor`, `blueColor` and their `*BackgroundColor`/`*TextColor`
  variants) that drive `st.error`/`st.success`/`st.warning`/`st.info`.
  Overriding these away from the red=error/green=success convention
  would hurt usability for no branding benefit.
- **DeadlinesTracker's amber overdue-row highlight**
  (`tracker.py::style_tracker_df`) and the DB-configurable status-pill
  colours (`statuses.colour`, editable in Admin) — these encode meaning,
  not brand.
- **DataCollector's custom HTML**: W/L/D result colours, the
  possession-bar red/green split, and the dark (`#111`) pitch/stat-card
  backgrounds — same reasoning.

### Known cosmetic side effect (not fixed here)

DataCollector's stat cards render via raw HTML/CSS outside Streamlit's
theme system. Some card backgrounds are light/white and will now sit
as light boxes against the new dark page background — visible but not
broken. Flagged for a possible follow-up pass; not fixed as part of
this change, since it falls outside the agreed "chrome only" scope.

## Testing / verification

No new logic is introduced, so no unit tests apply. Verification is
manual and visual:

1. Launch each app locally with the new `config.toml`.
2. Click through every page (DeadlinesTracker: home, Admin, Technical
   Plan; DataCollector: explorer and stat views) confirming text stays
   legible against the new backgrounds, including inside expanders,
   forms, and the sidebar.
3. Confirm the DeadlinesTracker dataframe's status-pill and overdue-row
   highlight colours are still readable against the new chrome.
4. Confirm button text on Mid Grey buttons is legible (Streamlit
   auto-computes button text colour from `primaryColor`'s luminance;
   verify it didn't pick something illegible).

## Out of scope

- Restyling DataCollector's custom HTML stat cards/possession bars to
  fit the dark theme (flagged above, not fixed here).
- Recolouring any semantic/status colours in either app.
- Font changes — the brand reference doesn't specify a typeface.
- Light/dark toggle support — dark is the only theme shipped.
