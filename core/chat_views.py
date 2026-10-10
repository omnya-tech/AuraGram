from core.constants import VIEW_ALL_KEY, VIEW_UNREAD_KEY, VIEW_ARCHIVE_KEY, VIEW_FOLDER_FORMAT_KEY

class ChatView:
    """One way of narrowing the chat list: a name and a test for which chats belong."""

    def __init__(self, label, matches):
        self.label = label
        self.matches = matches

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
    ]
    for folder in folders:
        views.append(ChatView(
            i18n.get_string(VIEW_FOLDER_FORMAT_KEY).format(title=folder["title"]),
            lambda chat, folder=folder: matches_folder(chat, folder)
        ))
    return views
