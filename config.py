import os
from dotenv import load_dotenv

def get_db_config() -> dict[str, str]:
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return {"url": url, "key": key}
