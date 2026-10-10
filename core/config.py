import json
import os
from core.constants import CONFIG_FILE, READ_MODE, ENCODING_UTF8, EMPTY_STRING

def load_credentials():
    """The Telegram API id and hash from the config file; (0, "") if not set up yet."""
    if not os.path.exists(CONFIG_FILE):
        return 0, EMPTY_STRING
    try:
        with open(CONFIG_FILE, READ_MODE, encoding=ENCODING_UTF8) as config_file:
            config_data = json.load(config_file)
    except (OSError, ValueError):
        # A damaged file is treated like a missing one: the app asks again.
        return 0, EMPTY_STRING
    return config_data.get("API_ID", 0), config_data.get("API_HASH", EMPTY_STRING)

def save_credentials(api_id, api_hash):
    with open(CONFIG_FILE, "w", encoding=ENCODING_UTF8) as config_file:
        json.dump({"API_ID": api_id, "API_HASH": api_hash}, config_file, indent=4)
