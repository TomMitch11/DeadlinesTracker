"""Runs all four fixture-sync sources and exits non-zero if any team's
sync reported an error. Intended to run headless from a scheduled job
(see .github/workflows/sync-fixtures.yml) rather than from the app UI."""
from __future__ import annotations
import re
import sys

from api_football_sync import sync_all_api_football_teams
from ical_sync import sync_all_ical_teams
from opta_sync import sync_all_opta_teams
from stats_perform_sync import sync_all_stats_perform_teams

_CREDENTIAL_PARAM = re.compile(r"(psw|user|api_key|sig|key)=[^&\s]*", re.IGNORECASE)


def _scrub_credentials(text: str) -> str:
    """Redacts credential-bearing query-string params (psw=, user=, api_key=,
    sig=, key=) from error text before it's printed to a log. Defense against
    GitHub's secret-masking being defeated by an encoded/transformed secret
    value (e.g. a password containing a reserved character gets
    percent-encoded by urllib3 before it reaches the exception message, so
    it no longer matches the registered secret verbatim)."""
    return _CREDENTIAL_PARAM.sub(r"\1=[redacted]", text)


def run_all_syncs() -> bool:
    """Runs every source's sync_all_*_teams(), printing a per-team summary
    to stdout. Always attempts all four sources, even if an earlier one
    contains team-level errors or raises an unexpected exception (any
    EnvironmentError, e.g. a missing credential, still propagates and
    crashes the script immediately — that's a real misconfiguration, not a
    flaky feed). Returns True only if every source contributed at least one
    team and every team's result was error-free; returns False if any team
    errored, any source raised an unexpected exception, or zero teams were
    synced across all sources (a silent, empty-but-"successful" run)."""
    sources = [
        ("iCal", sync_all_ical_teams),
        ("Opta", sync_all_opta_teams),
        # API-Football last: no credential provisioned for this source today,
        # so any future team configured for it fails fastest at the end of
        # the run rather than blocking an earlier, currently-working source.
        ("Stats Perform", sync_all_stats_perform_teams),
        ("API-Football", sync_all_api_football_teams),
    ]
    all_clean = True
    total_teams = 0
    for source_name, sync_fn in sources:
        print(f"=== {source_name} ===")
        try:
            results = sync_fn()
        except EnvironmentError:
            raise
        except Exception as e:
            all_clean = False
            print(f"  SOURCE FAILED {source_name}: {type(e).__name__}: {e}")
            continue
        if not results:
            print("  (no teams configured for this source)")
            continue
        for team_name, stats in results.items():
            total_teams += 1
            if "error" in stats:
                all_clean = False
                print(f"  FAILED {team_name}: {_scrub_credentials(str(stats['error']))}")
            else:
                print(f"  OK {team_name}: {stats}")
    if total_teams == 0:
        all_clean = False
        print("ZERO TEAMS SYNCED ACROSS ALL SOURCES — treating as failure")
    else:
        print(f"TOTAL: {total_teams} team(s) synced across sources with configured teams")
    return all_clean


if __name__ == "__main__":
    success = run_all_syncs()
    sys.exit(0 if success else 1)
