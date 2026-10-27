"""Several Telegram accounts on one computer: one is signed in and running at a time, each kept in a
session file of its own. The first account keeps the session file the app always had."""
import os

from core.constants import SESSION_NAME

FIRST_ACCOUNT = 0


def session_path(account_id):
    """Where an account's session lives: the usual file for the first, a numbered one for the others."""
    return SESSION_NAME if account_id == FIRST_ACCOUNT else "%s_%d" % (SESSION_NAME, account_id)


def is_signed_in_here(accounts, account_id, session_suffix=".session"):
    """Whether this computer has the account signed in: it was named here after signing in, and is
    forgotten on signing out, and its session file is still there."""
    return any(account["id"] == account_id for account in accounts) \
        and os.path.exists(session_path(account_id) + session_suffix)


def next_id(accounts, current):
    """A number no account has yet, for one about to be added."""
    return max([account["id"] for account in accounts] + [current]) + 1


def remember(accounts, account_id, name, phone):
    """The list with this account's name and number as Telegram gives them now, added if it was not there."""
    others = [account for account in accounts if account["id"] != account_id]
    return sorted(others + [{"id": account_id, "name": name, "phone": phone}], key=lambda account: account["id"])


def forget(accounts, account_id):
    return [account for account in accounts if account["id"] != account_id]
