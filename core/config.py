import hashlib
import hmac
import json
import os
import re
import unicodedata
from core.constants import BUNDLED_CONFIG_FILE, CONFIG_FILE, READ_MODE, ENCODING_UTF8, EMPTY_STRING, APP_NAME

SEAL_SALT_BYTES = 16
SEAL_CHECK_BYTES = 12

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

def _build_secret():
    """What build.py made up for one build and packed into that program; empty when running from source.

    The code is published, and with it the way the pair is sealed. This is the part that
    is not: it is in no repository, only inside a built program, and new for every build.
    """
    try:
        from core._seal import SECRET
    except ImportError:
        return b""
    return SECRET

def _seal_key(salt, secret=None):
    # Made at run time from pieces, so that neither the key nor the values it guards
    # sit anywhere in the program as text for a search to find. This keeps the pair
    # out of sight; it cannot keep it from someone who takes the program apart,
    # because the program itself has to be able to read it.
    material = (APP_NAME[::-1] + "%d" % (len(APP_NAME) * 7919)).encode(ENCODING_UTF8)
    material += _build_secret() if secret is None else secret
    return hashlib.sha256(salt + hashlib.sha256(material).digest() + salt[::-1]).digest()

def _seal_stream(key, length):
    blocks, counter = b"", 0
    while len(blocks) < length:
        blocks += hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
        counter += 1
    return blocks[:length]

def seal_credentials(api_id, api_hash, secret=None):
    """The API id and hash as unreadable bytes for packing into the program; different every time it is made.

    `secret` is the build's own (see _build_secret); left out, the one this program carries is used.
    """
    plain = json.dumps([api_id, api_hash]).encode(ENCODING_UTF8)
    salt = os.urandom(SEAL_SALT_BYTES)
    key = _seal_key(salt, secret)
    sealed = bytes(a ^ b for a, b in zip(plain, _seal_stream(key, len(plain))))
    check = hmac.new(key, sealed, hashlib.sha256).digest()[:SEAL_CHECK_BYTES]
    return salt + check + sealed

def read_sealed(path):
    """The API id and hash from a file made by seal_credentials; (0, "") if it is missing or not intact."""
    try:
        with open(path, "rb") as sealed_file:
            data = sealed_file.read()
    except OSError:
        return 0, EMPTY_STRING
    salt, check = data[:SEAL_SALT_BYTES], data[SEAL_SALT_BYTES:SEAL_SALT_BYTES + SEAL_CHECK_BYTES]
    sealed = data[SEAL_SALT_BYTES + SEAL_CHECK_BYTES:]
    key = _seal_key(salt)
    if len(salt) < SEAL_SALT_BYTES or not hmac.compare_digest(
        check, hmac.new(key, sealed, hashlib.sha256).digest()[:SEAL_CHECK_BYTES]
    ):
        # Damaged, cut short, or some other file under this name.
        return 0, EMPTY_STRING
    try:
        api_id, api_hash = json.loads(bytes(a ^ b for a, b in zip(sealed, _seal_stream(key, len(sealed)))))
    except (ValueError, TypeError):
        return 0, EMPTY_STRING
    api_hash = clean_api_hash(api_hash)
    if not isinstance(api_id, int) or api_id <= 0 or not api_hash:
        return 0, EMPTY_STRING
    return api_id, api_hash

def load_credentials():
    """The Telegram API id and hash to sign in with; (0, "") if the app has to ask for them.

    The pair shipped inside the built program comes first, so an installed copy
    never asks. Without one (running from source, or a build made without a
    config file) the user's own file is used.
    """
    api_id, api_hash = read_sealed(BUNDLED_CONFIG_FILE)
    if api_id:
        return api_id, api_hash
    return read_credentials(CONFIG_FILE)

def save_credentials(api_id, api_hash):
    with open(CONFIG_FILE, "w", encoding=ENCODING_UTF8) as config_file:
        json.dump({"API_ID": api_id, "API_HASH": api_hash}, config_file, indent=4)
