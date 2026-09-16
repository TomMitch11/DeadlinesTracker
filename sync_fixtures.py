"""Runs all four fixture-sync sources and exits non-zero if any team's
sync reported an error. Intended to run headless from a scheduled job
(see .github/workflows/sync-fixtures.yml) rather than from the app UI."""
from __future__ import annotations
import re
import sys

from api_football_sync import sync_all_api_football_teams
from config import get_db_config, get_opta_config, get_sp_config
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
    to stdout. Preflights required credentials (Supabase, Opta, Stats
    Perform -- not API-Football, which has none configured today) before
    attempting any source, so a genuine misconfiguration (a missing env
    var) fails fast and deterministically with a clear EnvironmentError,
    regardless of source order. Once past that check, any other exception
    during a source's sync (a transient network error, a malformed row) is
    caught, logged, and the run continues to the next source -- one broken
    source never prevents the others from being attempted. Returns True
    only if every team's result was error-free and at least one team was
    synced somewhere; returns False if any team errored, any source raised
    an exception, or zero teams were synced across all sources (a silent,
    empty-but-"successful" run)."""
    get_db_config()
    get_opta_config()
    get_sp_config()

    sources = [
        ("iCal", sync_all_ical_teams),
        ("Opta", sync_all_opta_teams),
        ("Stats Perform", sync_all_stats_perform_teams),
        # API-Football last: no credential provisioned for this source
        # today, so it's deliberately NOT preflighted above -- if a team is
        # ever configured for it, its own get_api_football_config() call
        # raises EnvironmentError from inside sync_team(), which is caught
        # below by the broad except and reported as an ordinary source
        # failure, not a script-crashing misconfiguration (that treatment
        # is reserved for the three sources preflighted above).
        ("API-Football", sync_all_api_football_teams),
    ]
    all_clean = True
    total_teams = 0
    for source_name, sync_fn in sources:
        print(f"=== {source_name} ===")
        try:
            results = sync_fn()
        except Exception as e:
            all_clean = False
            print(f"  SOURCE FAILED {source_name}: {type(e).__name__}: {_scrub_credentials(str(e))}")
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
