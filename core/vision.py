"""Describing a picture in words, by asking Google's Gemini with the user's own API key."""
import base64
import json
import logging
import os
import urllib.error
import urllib.request

from core.constants import (
    GEMINI_ENDPOINT_FORMAT, GEMINI_MODELS, GEMINI_MODELS_URL, GEMINI_TIMEOUT_SECONDS, GEMINI_MAX_IMAGE_BYTES, IMAGE_MIME_TYPES,
    ERR_VISION_KEY_KEY, ERR_VISION_QUOTA_KEY, ERR_VISION_BUSY_KEY, ERR_VISION_FAILED_KEY, ERR_VISION_NO_ANSWER_KEY,
    ERR_VISION_TOO_BIG_KEY, ERR_CONNECTION_KEY
)

logger = logging.getLogger(__name__)
HTTP_BAD_REQUEST, HTTP_UNAUTHORIZED, HTTP_FORBIDDEN, HTTP_NOT_FOUND, HTTP_TOO_MANY = 400, 401, 403, 404, 429
HTTP_SERVER_ERROR, HTTP_UNAVAILABLE = 500, 503
# Answers about one model only: gone, out of its own quota, or too busy just now. Another may still answer.
TRY_ANOTHER_MODEL = (HTTP_NOT_FOUND, HTTP_TOO_MANY, HTTP_SERVER_ERROR, HTTP_UNAVAILABLE)
# Enough of Google's answer to a failure for the log to tell why, never the key.
LOGGED_BODY_CHARACTERS = 300
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
    if status in (HTTP_SERVER_ERROR, HTTP_UNAVAILABLE):
        return ERR_VISION_BUSY_KEY
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
    data = json.dumps(build_request(image, mime_type, prompt)).encode("utf-8")
    error_key = ERR_VISION_FAILED_KEY
    for model in GEMINI_MODELS:
        request = urllib.request.Request(
            GEMINI_ENDPOINT_FORMAT.format(model=model), data=data,
            # In a header, not the address: addresses end up in logs and histories.
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key.strip()},
        )
        try:
            with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
                return read_answer(response.read())
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", "replace")
            logger.warning("Gemini answered %s for %s: %s", error.code, model, body[:LOGGED_BODY_CHARACTERS])
            if error.code in TRY_ANOTHER_MODEL:
                # Only this model is out of reach; if all of them are, the reason is the last one's.
                if error.code != HTTP_NOT_FOUND:
                    error_key = error_key_for(error.code, body)
                continue
            raise VisionError(error_key_for(error.code, body)) from error
        except (OSError, ValueError) as error:
            logger.warning("Could not reach Gemini: %s", error)
            raise VisionError(ERR_CONNECTION_KEY) from error
    raise VisionError(error_key)


def check_key(api_key):
    """Whether Gemini takes the key, asked without sending any picture. Blocks; raises VisionError if not."""
    request = urllib.request.Request(GEMINI_MODELS_URL, headers={"x-goog-api-key": api_key.strip()})
    try:
        with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
            response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        logger.warning("Gemini refused the key: %s %s", error.code, body[:LOGGED_BODY_CHARACTERS])
        raise VisionError(error_key_for(error.code, body)) from error
    except (OSError, ValueError) as error:
        raise VisionError(ERR_CONNECTION_KEY) from error
