from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

def test_view_apps_have_no_sibling_pages_dir():
    for script in ("sales_view.py", "partner_success_view.py"):
        matches = list(REPO_ROOT.rglob(script))
        assert matches, f"{script} not found in repo"
        for match in matches:
            assert not match.parent.joinpath("pages").exists(), (
                f"{match} has a sibling 'pages/' directory — Streamlit's multipage "
                f"auto-discovery will attach it, defeating this app's access separation"
            )
