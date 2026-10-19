from core.constants import INFO_MEMBER_ROLE_FORMAT_KEY, MEMBER_BOT_KEY


def member_row(window, i18n, member):
    """A member as the lists of a chat's members show them: the name, then the role if any, then
    whether they are online or when they were last seen, as Telegram allows it to be known."""
    text = i18n.get_string
    row = member["name"]
    details = []
    if member["role"]:
        details.append(text(member["role"]))
    if member.get("is_bot"):
        details.append(text(MEMBER_BOT_KEY))
    else:
        # The main window words statuses the way the settings ask for times.
        status_text = getattr(window.GetParent(), "status_text", None)
        status = status_text(member) if status_text and member.get("status") else ""
        if status:
            details.append(status)
    for detail in details:
        row = text(INFO_MEMBER_ROLE_FORMAT_KEY).format(name=row, role=detail)
    return row
