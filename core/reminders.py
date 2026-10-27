"""Messages the user asked to be reminded of, kept in a small file beside the settings so that
they survive the program closing. A reminder whose time came while it was closed is given at the next start.

Each reminder is {"chat_id", "chat_title", "message_id", "text", "due"}, with "due" a moment
written as ISO text with its time zone.
"""
import datetime
import json
import logging
from core import files
from core.constants import REMINDERS_FILE, ENCODING_UTF8, REMIND_MORNING_HOUR

logger = logging.getLogger(__name__)
FIELDS = ("chat_id", "chat_title", "message_id", "text", "due")


def load():
    """The saved reminders, soonest first; an empty list if there are none or the file is damaged."""
    try:
        with open(REMINDERS_FILE, encoding=ENCODING_UTF8) as file:
            stored = json.load(file)
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        logger.warning("The reminders file could not be read", exc_info=True)
        return []
    if not isinstance(stored, list):
        logger.warning("The reminders file holds no list of reminders")
        return []
    # One reminder damaged, by hand or by a crash, must not keep the others, or the window, from opening.
    reminders = [item for item in stored if is_whole(item)]
    return sorted(reminders, key=due_of)


def is_whole(item):
    if not isinstance(item, dict) or not all(field in item for field in FIELDS):
        return False
    try:
        due = due_of(item)
    except (TypeError, ValueError):
        return False
    # Compared with the others once sorted: a moment with no time zone could not be.
    return due.tzinfo is not None


def save(reminders):
    files.write_json(REMINDERS_FILE, reminders, ensure_ascii=False, indent=4)


def due_of(reminder):
    return datetime.datetime.fromisoformat(reminder["due"])


def when(choice, now):
    """The moment a choice of REMIND_CHOICES stands for: minutes from now, or None for tomorrow morning."""
    if choice is None:
        tomorrow = now + datetime.timedelta(days=1)
        return tomorrow.replace(hour=REMIND_MORNING_HOUR, minute=0, second=0, microsecond=0)
    return now + datetime.timedelta(minutes=choice)


def take_due(reminders, now):
    """Split the reminders into those whose time has come and those still to wait."""
    due = [reminder for reminder in reminders if due_of(reminder) <= now]
    return due, [reminder for reminder in reminders if due_of(reminder) > now]
