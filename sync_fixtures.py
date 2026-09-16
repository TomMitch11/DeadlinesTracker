"""Runs all four fixture-sync sources and exits non-zero if any team's
sync reported an error. Intended to run headless from a scheduled job
(see .github/workflows/sync-fixtures.yml) rather than from the app UI."""
from __future__ import annotations
import sys

from api_football_sync import sync_all_api_football_teams
from ical_sync import sync_all_ical_teams
from opta_sync import sync_all_opta_teams
from stats_perform_sync import sync_all_stats_perform_teams

_SOURCES = [
    ("iCal", "sync_all_ical_teams"),
    ("Opta", "sync_all_opta_teams"),
    ("Stats Perform", "sync_all_stats_perform_teams"),
    ("API-Football", "sync_all_api_football_teams"),
]


def run_all_syncs() -> bool:
    """Runs every source's sync_all_*_teams(), printing a per-team summary
    to stdout. Always attempts all four sources, even if an earlier one
    contains team-level errors. Returns True if every team's result was
    error-free, False if any team's result dict contains an "error" key
    (a source with zero configured teams contributes no errors)."""
    all_clean = True
    for source_name, func_name in _SOURCES:
        sync_fn = globals()[func_name]
        print(f"=== {source_name} ===")
        results = sync_fn()
        if not results:
            print("  (no teams configured for this source)")
            continue
        for team_name, stats in results.items():
            if "error" in stats:
                all_clean = False
                print(f"  FAILED {team_name}: {stats['error']}")
            else:
                print(f"  OK {team_name}: {stats}")
    return all_clean


if __name__ == "__main__":
    success = run_all_syncs()
    sys.exit(0 if success else 1)
