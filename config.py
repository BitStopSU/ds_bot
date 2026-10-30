import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "bot.db"
GUILD_ID = int(os.getenv("GUILD_ID", 0))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Minsk")

ROLE_UNVERIFIED = 0
ROLE_VERIFIED = 0
ROLE_DENIED = 0
ROLE_MUTED = 0

CHANNEL_SUPPORT_LOG = 0
CHANNEL_MOD_LOG = 0
CHANNEL_EVENT_LOG = 0
CHANNEL_ADMIN_LOG = 0

VOICE_CATEGORIES = {
    "support_room": 0,
    "mod_room": 0,
    "event_room": 0,
}

WARN_TO_BAN = 3
BAN_DURATION_DAYS = 30
MUTE_MAX_HOURS = 72

GOOGLE_CREDS_FILE = "google_creds.json"
SHEET_ID = ""
SHEET_TABS = {"support": "Support", "mod": "Moderators", "event": "Eventers"}
