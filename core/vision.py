"""Describing a picture in words, by asking Google's Gemini with the user's own API key."""
import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request

from core.constants import (
    GEMINI_ENDPOINT_FORMAT, GEMINI_MODELS, GEMINI_MODELS_URL, GEMINI_TIMEOUT_SECONDS, GEMINI_MAX_IMAGE_BYTES, IMAGE_MIME_TYPES,
    ERR_VISION_KEY_KEY, ERR_VISION_QUOTA_KEY, ERR_VISION_BUSY_KEY, ERR_VISION_FAILED_KEY, ERR_VISION_NO_ANSWER_KEY,
    ERR_VISION_TOO_BIG_KEY, ERR_VISION_UNREACHABLE_KEY, GEMINI_BUSY_TRIES, GEMINI_BUSY_WAIT_SECONDS, GEMINI_MODEL_KIND
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


def describe_image(path, api_key, prompt, wait=None):
    """Gemini's description of the picture in a file. Blocks; raises VisionError with the reason.

    Each of GEMINI_MODELS is tried in turn, a busy one twice; if none answers, then the other
    models the key may use, as Google lists them, so a model Google retires is replaced by itself."""
    mime_type = image_mime_type(path)
    if mime_type is None:
        raise VisionError(ERR_VISION_FAILED_KEY)
    with open(path, "rb") as image_file:
        image = image_file.read(GEMINI_MAX_IMAGE_BYTES + 1)
    if len(image) > GEMINI_MAX_IMAGE_BYTES:
        raise VisionError(ERR_VISION_TOO_BIG_KEY)
    data = json.dumps(build_request(image, mime_type, prompt)).encode("utf-8")
    error_key = ERR_VISION_FAILED_KEY
    tried = []
    for models, tries in ((GEMINI_MODELS, GEMINI_BUSY_TRIES), (None, 1)):
        if models is None:
            models = [model for model in other_models(api_key) if model not in tried]
        for model in models:
            tried.append(model)
            for attempt in range(tries):
                if attempt:
                    (wait or time.sleep)(GEMINI_BUSY_WAIT_SECONDS)
                try:
                    return ask_model(model, data, api_key)
                except ModelUnavailable as unavailable:
                    # Only this model is out of reach; if all of them are, the reason is the last one's.
                    if unavailable.error_key is not None:
                        error_key = unavailable.error_key
                    if not unavailable.busy:
                        break
    raise VisionError(error_key)


class ModelUnavailable(Exception):
    """One model could not answer, though another may; `busy` if it may answer if asked again."""

    def __init__(self, error_key, busy):
        super().__init__(error_key)
        self.error_key = error_key
        self.busy = busy


def ask_model(model, data, api_key):
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
            # A model that is gone says nothing about the others, so it leaves the reason as it was.
            error_key = None if error.code == HTTP_NOT_FOUND else error_key_for(error.code, body)
            raise ModelUnavailable(error_key, busy=error.code in (HTTP_SERVER_ERROR, HTTP_UNAVAILABLE)) from error
        raise VisionError(error_key_for(error.code, body)) from error
    except (OSError, ValueError) as error:
        logger.warning("Could not reach Gemini with %s: %s", model, error)
        if is_timeout(error):
            # Google took the picture but kept it too long: busy, like a 503.
            raise ModelUnavailable(ERR_VISION_BUSY_KEY, busy=False) from error
        raise VisionError(ERR_VISION_UNREACHABLE_KEY) from error


def is_timeout(error):
    reason = getattr(error, "reason", error)
    return isinstance(reason, TimeoutError) or "timed out" in str(reason)


def other_models(api_key):
    """The names of the models the key may ask to describe a picture, quickest kinds first; [] if unknown."""
    request = urllib.request.Request(GEMINI_MODELS_URL, headers={"x-goog-api-key": api_key.strip()})
    try:
        with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
            listed = json.loads(response.read()).get("models", [])
    except (OSError, ValueError, AttributeError) as error:
        logger.warning("Could not list Gemini's models: %s", error)
        return []
    names = [
        model.get("name", "").split("/")[-1] for model in listed
        if "generateContent" in model.get("supportedGenerationMethods", [])
        and GEMINI_MODEL_KIND in model.get("name", "")
    ]
    return [name for name in names if name]


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
        raise VisionError(ERR_VISION_UNREACHABLE_KEY) from error
