import json
import os
from core.constants import LOCALES_DIR, JSON_EXT, READ_MODE, ENCODING_UTF8

class I18NManager:
    def __init__(self, lang_code):
        self.lang_code = lang_code
        self.strings = {}
        self.load_language()

    def load_language(self):
        file_path = os.path.join(LOCALES_DIR, self.lang_code + JSON_EXT)
        if os.path.exists(file_path):
            with open(file_path, READ_MODE, encoding=ENCODING_UTF8) as file:
                self.strings = json.load(file)

    def get_string(self, key):
        # Fall back to the key itself so a missing translation is visible.
        return self.strings.get(key, key)
