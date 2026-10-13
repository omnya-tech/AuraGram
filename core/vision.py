"""Describing a picture in words, by asking Google's Gemini with the user's own API key."""
import base64
import json
import os
import urllib.error
import urllib.request

from core.constants import (
    GEMINI_ENDPOINT_FORMAT, GEMINI_MODEL, GEMINI_TIMEOUT_SECONDS, GEMINI_MAX_IMAGE_BYTES, IMAGE_MIME_TYPES,
    ERR_VISION_KEY_KEY, ERR_VISION_QUOTA_KEY, ERR_VISION_FAILED_KEY, ERR_VISION_NO_ANSWER_KEY,
    ERR_VISION_TOO_BIG_KEY, ERR_CONNECTION_KEY
)

HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED, HTTP_FORBIDDEN, HTTP_TOO_MANY = 400, 401, 403, 429
# How Google words a key it does not know, in the middle of an otherwise ordinary "bad request".
INVALID_KEY_MARK = "API_KEY_INVALID"


class VisionError(Exception):
    """Describing failed; `error_key` is the locale key of what to tell the user."""

    def __init__(self, error_key):
        super().__init__(error_key)
        self.error_key = error_key


def image_mime_type(path):
    """The kind of picture a file is, going by its name; None for what Gemini is not given."""
    return IMAGE_MIME_TYPES.get(os.path.splitext(path)[1].lower())


def build_request(image, mime_type, prompt):
    return {"contents": [{"parts": [
        {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image).decode("ascii")}},
        {"text": prompt},
    ]}]}


def read_answer(data):
    """The text of Gemini's answer; raises VisionError if it gave none (it may decline a picture)."""
    try:
        parts = json.loads(data)["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts).strip()
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        text = ""
    if not text:
        raise VisionError(ERR_VISION_NO_ANSWER_KEY)
    return text


def error_key_for(status, body):
    if status in (HTTP_UNAUTHORIZED, HTTP_FORBIDDEN) or (status == HTTP_BAD_REQUEST and INVALID_KEY_MARK in body):
        return ERR_VISION_KEY_KEY
    if status == HTTP_TOO_MANY:
        return ERR_VISION_QUOTA_KEY
    return ERR_VISION_FAILED_KEY


def describe_image(path, api_key, prompt):
    """Gemini's description of the picture in a file. Blocks; raises VisionError with the reason."""
    mime_type = image_mime_type(path)
    if mime_type is None:
        raise VisionError(ERR_VISION_FAILED_KEY)
    with open(path, "rb") as image_file:
        image = image_file.read(GEMINI_MAX_IMAGE_BYTES + 1)
    if len(image) > GEMINI_MAX_IMAGE_BYTES:
        raise VisionError(ERR_VISION_TOO_BIG_KEY)
    request = urllib.request.Request(
        GEMINI_ENDPOINT_FORMAT.format(model=GEMINI_MODEL),
        data=json.dumps(build_request(image, mime_type, prompt)).encode("utf-8"),
        # In a header, not the address: addresses end up in logs and histories.
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key.strip()},
    )
    try:
        with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
            return read_answer(response.read())
    except urllib.error.HTTPError as error:
        raise VisionError(error_key_for(error.code, error.read().decode("utf-8", "replace"))) from error
    except (OSError, ValueError) as error:
        raise VisionError(ERR_CONNECTION_KEY) from error
