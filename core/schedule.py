import datetime
import re

# Latin and Arabic-Indic digits, with any single separator between hours and minutes.
TIME_PATTERN = re.compile(r"^\s*(\d{1,2})\s*[:.٫،\-\s]\s*(\d{1,2})\s*$")

def parse_send_time(text, now):
    """Turn "21:30" into the next moment the clock shows that time; None if it is not a time."""
    match = TIME_PATTERN.match(text)
    if not match:
        return None
    # int() understands Arabic-Indic digits as well.
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if when <= now:
        when += datetime.timedelta(days=1)
    return when
