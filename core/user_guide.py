"""The user guide: a web page about every part of the app, in the interface language, with the
app's own shortcuts written in where the guide names a command.

The guide is written once per language in locales/guide_<language>.html, with {{COMMAND}} wherever
a command's shortcut goes and {{VERSION}} for the version; opening it fills those in. The guide says
the shortcuts can be changed, and that the shortcuts guide lists them as the user has them.
"""
import html
import os
import re

from core.constants import (
    LOCALES_DIR, DATA_DIR, GUIDE_TEMPLATE_FORMAT, GUIDE_FILE_FORMAT, APP_VERSION, DEFAULT_LANG, ENCODING_UTF8
)

PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
VERSION = "VERSION"


def template_path(language):
    """The guide written for a language, or the default language's where there is none."""
    path = os.path.join(LOCALES_DIR, GUIDE_TEMPLATE_FORMAT.format(language=language))
    return path if os.path.exists(path) else os.path.join(LOCALES_DIR, GUIDE_TEMPLATE_FORMAT.format(language=DEFAULT_LANG))


def fill(template, table, no_shortcut):
    """The guide with every {{COMMAND}} replaced by its shortcut in `table`, or by `no_shortcut`."""
    def shortcut(match):
        name = match.group(1)
        if name == VERSION:
            return html.escape(APP_VERSION)
        keys = table.get(name)
        if keys:
            return "<kbd>%s</kbd>" % html.escape(keys)
        return '<span class="none">(%s)</span>' % html.escape(no_shortcut)
    return PLACEHOLDER.sub(shortcut, template)


def placeholders(template):
    return set(PLACEHOLDER.findall(template)) - {VERSION}


def write(language, table, no_shortcut, folder=DATA_DIR):
    """Make the guide for `language` with these shortcuts; the result is where it was written."""
    with open(template_path(language), encoding=ENCODING_UTF8) as file:
        page = fill(file.read(), table, no_shortcut)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, GUIDE_FILE_FORMAT.format(language=language))
    with open(path, "w", encoding=ENCODING_UTF8) as file:
        file.write(page)
    return path
