"""Looking through all of Telegram for people, groups and channels, more loosely than Telegram does.

Telegram finds a name only when what is typed matches the start of it, written the same way.
So the search asks it several times, each time a little looser: as typed, without marks and
with the other forms of alef, then word by word, then with only the start of each word.
Everything found is put together once, and the nearest to what was typed comes first.
"""
import difflib
import unicodedata

# Each round of searching is looser than the one before; "show more" asks for the next.
ROUNDS = 3
# The shortest piece of a word worth asking for on its own.
SHORTEST_PART = 2
ALEF_FORMS = "اأإ"
SAME_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"})


def fold(text):
    """Text as names are compared: no case, no marks, one form for each letter, single spaces."""
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char) and char != "ـ")
    return " ".join(text.translate(SAME_LETTERS).split())


def alef_forms(word):
    """A word with each form of alef it may begin with, for a name Telegram keeps written one way."""
    if word and word[0] in ALEF_FORMS:
        return [form + word[1:] for form in ALEF_FORMS]
    return [word]


def queries(text, round_number):
    """What to ask Telegram in one round of searching, nothing already asked in an earlier round."""
    text = " ".join(text.split())
    if not text:
        return []
    words = text.split()
    if round_number == 0:
        wanted = [text, fold(text)] + [" ".join([form] + words[1:]) for form in alef_forms(words[0])]
    elif round_number == 1:
        wanted = [form for word in words if len(word) >= SHORTEST_PART for form in alef_forms(word)]
        wanted += [fold(word) for word in words if len(word) >= SHORTEST_PART]
    elif round_number == 2:
        # The start of each word only: it finds a name written a little differently further on.
        wanted = []
        for word in words:
            for length in (4, 3):
                if len(word) > length:
                    wanted.append(word[:length])
        if len(text) > SHORTEST_PART + 1:
            wanted.append(text[:-1])
    else:
        return []
    earlier = {query for previous in range(round_number) for query in queries(text, previous)}
    seen, result = set(), []
    for query in wanted:
        if query and len(query) >= SHORTEST_PART and query not in seen and query not in earlier:
            seen.add(query)
            result.append(query)
    return result


def nearness(chat, text):
    """How near a found chat is to what was typed, from 0 to 1; its name and its username both count."""
    wanted = fold(text)
    best = 0.0
    for name in (chat.get("title") or "", chat.get("username") or ""):
        name = fold(name)
        if not name:
            continue
        if name == wanted:
            score = 1.0
        elif name.startswith(wanted):
            score = 0.9
        elif wanted in name:
            score = 0.8
        else:
            words = set(wanted.split())
            shared = len(words & set(name.split())) / len(words) if words else 0
            score = max(0.7 * shared, 0.7 * difflib.SequenceMatcher(None, wanted, name).ratio())
        best = max(best, score)
    return best


def ranked(chats, text):
    """The chats found, nearest first; among those as near, the bigger first."""
    return sorted(chats, key=lambda chat: (-nearness(chat, text), -(chat.get("members") or 0)))
