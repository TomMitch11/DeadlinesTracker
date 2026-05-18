import os
from dotenv import load_dotenv

load_dotenv()

def get_db_config() -> dict:
    url = os.getenv("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return {"url": url, "key": key}
