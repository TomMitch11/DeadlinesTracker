from streamlit.testing.v1 import AppTest

def test_app_boots_with_theme_config():
    at = AppTest.from_file("app.py")
    at.run(timeout=15)  # default 3s timeout is too short for first-run import overhead
    assert not at.exception
