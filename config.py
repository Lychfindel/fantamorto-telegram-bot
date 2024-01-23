import os
from dotenv import load_dotenv

load_dotenv()

# Global variables
TOKEN = os.getenv("TOKEN", "")
SUPERUSER = os.getenv("SUPERUSER", "")
CHAT_DATA_KEY = "game"
CHAT_ARCHIVE_KEY = "archive"
BAN_LIST_FILE = "ban_list.yaml"

# Constants
DEFAULT_FANTAMORTO_TEAM_SIZE = 10