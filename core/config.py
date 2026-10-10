import json
import os
import re
import unicodedata
from core.constants import BUNDLED_CONFIG_FILE, CONFIG_FILE, READ_MODE, ENCODING_UTF8, EMPTY_STRING

API_HASH_PATTERN = re.compile(r"^[0-9a-f]{32}$")
# What tends to come along when the hash is copied out of a file or a web page.
STRAY_CHARACTERS = "\"'`,;:«»“”‘’"

def clean_api_hash(text):
    """An API hash as typed or pasted, reduced to its 32 hex digits; "" if that is not what it is.

    Pasting often drags along a space, a quote or an invisible character, and
    Telegram rejects the hash for a single extra character.
    """
    cleaned = "".join(
        character for character in str(text).lower()
        # Drop only what cannot be part of any hash: spaces, quotes, commas and
        # invisible characters. A wrong letter is left in, so it fails the check.
        if character not in STRAY_CHARACTERS and unicodedata.category(character)[0] not in "CZ"
    )
    return cleaned if API_HASH_PATTERN.match(cleaned) else EMPTY_STRING

def read_credentials(path):
    """The API id and hash from one config file; (0, "") if it is missing, damaged or not valid."""
    if not os.path.exists(path):
        return 0, EMPTY_STRING
    try:
        with open(path, READ_MODE, encoding=ENCODING_UTF8) as config_file:
            config_data = json.load(config_file)
    except (OSError, ValueError):
        return 0, EMPTY_STRING
    api_id = config_data.get("API_ID", 0)
    api_hash = clean_api_hash(config_data.get("API_HASH", EMPTY_STRING))
    if not isinstance(api_id, int) or api_id <= 0 or not api_hash:
        # Treated like a missing file, so a bad value never reaches Telegram.
        return 0, EMPTY_STRING
    return api_id, api_hash

def load_credentials():
    """The Telegram API id and hash to sign in with; (0, "") if the app has to ask for them.

    The pair shipped inside the built program comes first, so an installed copy
    never asks. Without one (running from source, or a build made without a
    config file) the user's own file is used.
    """
    for path in (BUNDLED_CONFIG_FILE, CONFIG_FILE):
        api_id, api_hash = read_credentials(path)
        if api_id:
            return api_id, api_hash
    return 0, EMPTY_STRING

def save_credentials(api_id, api_hash):
    with open(CONFIG_FILE, "w", encoding=ENCODING_UTF8) as config_file:
        json.dump({"API_ID": api_id, "API_HASH": api_hash}, config_file, indent=4)
