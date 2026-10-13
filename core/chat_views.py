from core.constants import (
    VIEW_ALL_KEY, VIEW_UNREAD_KEY, VIEW_ARCHIVE_KEY, VIEW_FOLDER_FORMAT_KEY, VIEW_CONTACTS_KEY, STATUS_ONLINE_KEY
)

class ChatView:
    """One way of narrowing the chat list: a name and a test for which chats belong."""

    def __init__(self, label, matches, is_contacts=False):
        self.label = label
        self.matches = matches
        # The one view that lists people rather than chats: the account's contacts,
        # whether or not anything was ever written to them.
        self.is_contacts = is_contacts

def is_online(chat):
    return chat["status"] is not None and chat["status"][0] == STATUS_ONLINE_KEY

def contacts_first_online(contacts):
    """Contacts in the order given, but with those who are around right now ahead of the rest."""
    return sorted(contacts, key=lambda chat: not is_online(chat))

def matches_folder(chat, folder):
    """Applies a Telegram folder's rules the way the official apps do."""
    if chat["id"] in folder["exclude_ids"]:
        return False
    # Chats added by hand belong regardless of the folder's general rules.
    if chat["id"] in folder["include_ids"]:
        return True
    if chat["category"] not in folder["categories"]:
        return False
    if folder["exclude_muted"] and chat["muted"]:
        return False
    if folder["exclude_read"] and not chat["unread"]:
        return False
    if folder["exclude_archived"] and chat["archived"]:
        return False
    return True

def build_views(i18n, folders):
    """The built-in views followed by one per Telegram folder."""
    views = [
        ChatView(i18n.get_string(VIEW_ALL_KEY), lambda chat: not chat["archived"]),
        ChatView(i18n.get_string(VIEW_UNREAD_KEY), lambda chat: bool(chat["unread"]) and not chat["archived"]),
        ChatView(i18n.get_string(VIEW_ARCHIVE_KEY), lambda chat: chat["archived"]),
        # No chat belongs to it by any rule: its rows come from the contact list.
        ChatView(i18n.get_string(VIEW_CONTACTS_KEY), lambda chat: False, is_contacts=True),
    ]
    for folder in folders:
        views.append(ChatView(
            i18n.get_string(VIEW_FOLDER_FORMAT_KEY).format(title=folder["title"]),
            lambda chat, folder=folder: matches_folder(chat, folder)
        ))
    return views
