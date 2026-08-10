import os
from dotenv import load_dotenv

def get_db_config() -> dict[str, str]:
    load_dotenv(override=True)
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return {"url": url, "key": key}

def get_opta_config() -> dict[str, str]:
    load_dotenv(override=True)
    username = os.getenv("OMO_USERNAME")
    password = os.getenv("OMO_PASSWORD")
    base_url = os.getenv("OMO_BASE_URL", "http://omo.akamai.opta.net")
    if not username or not password:
        raise EnvironmentError("OMO_USERNAME and OMO_PASSWORD must be set")
    return {"username": username, "password": password, "base_url": base_url}

def get_email_config() -> dict:
    load_dotenv(override=True)
    return {
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_user": os.getenv("SMTP_USER", ""),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "from_addr": os.getenv("NOTIFICATION_FROM", os.getenv("SMTP_USER", "")),
        "to_addr": os.getenv("NOTIFICATION_TO", ""),
    }

def get_api_football_config() -> dict[str, str]:
    load_dotenv(override=True)
    api_key = os.getenv("API_FOOTBALL_KEY")
    if not api_key:
        raise EnvironmentError("API_FOOTBALL_KEY must be set")
    return {"api_key": api_key}
