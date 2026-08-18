from pathlib import Path

def test_app_has_no_manual_sales_deadline_widget():
    app_source = (Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8")
    assert "Sales deadline" not in app_source
    assert "add_sales" not in app_source
    assert "esales_" not in app_source
