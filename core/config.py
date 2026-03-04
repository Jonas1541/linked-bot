import os
import yaml
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
USER_DATA_DIR = BASE_DIR / "browser_data"

# Config settings
LINKEDIN_USERNAME = os.getenv("LINKEDIN_USERNAME")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")
LINKEDIN_2FA_SECRET = os.getenv("LINKEDIN_2FA_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

HEADLESS_MODE = os.getenv("HEADLESS_MODE", "False").lower() in ("true", "1", "t")
MAX_DAILY_APPLICATIONS = int(os.getenv("MAX_DAILY_APPLICATIONS", 50))

# Proxy config (optional)
PROXY_SERVER = os.getenv("PROXY_SERVER")
PROXY_USERNAME = os.getenv("PROXY_USERNAME")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

def load_profile() -> dict:
    """Loads the user profile from perfil.yaml"""
    profile_path = BASE_DIR / "perfil.yaml"
    with open(profile_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)

USER_PROFILE = load_profile()
