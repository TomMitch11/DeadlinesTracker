import pytest
from unittest.mock import patch
from config import get_db_config

# get_db_config() calls load_dotenv(override=True), which would otherwise
# overwrite these tests' patched os.environ with whatever is in the real
# .env file on disk. Patch load_dotenv to a no-op so tests stay isolated.

def test_get_db_config_returns_values():
    with patch("config.load_dotenv"), \
         patch.dict("os.environ", {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_KEY": "key123"}):
        cfg = get_db_config()
    assert cfg["url"] == "https://x.supabase.co"
    assert cfg["key"] == "key123"

def test_get_db_config_raises_if_missing():
    with patch("config.load_dotenv"), \
         patch.dict("os.environ", {}, clear=True):
        with pytest.raises(EnvironmentError):
            get_db_config()
