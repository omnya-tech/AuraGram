"""The program's workings, apart from its windows.

Before anything here brings in Telethon: a cryptg that is there but cannot work is set aside.
Telethon encrypts with cryptg whenever `import cryptg` succeeds, and only finds out it cannot when
it encrypts its first message, which ends its sending and with it the whole connection. A folder
left by an older build (1.0.0 shipped cryptg for Python 3.11) imports as an empty namespace that
way. Without it Telethon uses the OpenSSL bundled beside the program, which is just as fast.
"""
import sys

# True when a cryptg was found broken and set aside; the client says so in the log once it starts.
CRYPTG_SET_ASIDE = False


def _set_aside_broken_cryptg():
    global CRYPTG_SET_ASIDE
    try:
        import cryptg
    except Exception:
        return
    if not (hasattr(cryptg, "encrypt_ige") and hasattr(cryptg, "decrypt_ige")):
        # None in sys.modules makes every later `import cryptg` fail, so Telethon goes on without it.
        sys.modules["cryptg"] = None
        CRYPTG_SET_ASIDE = True


_set_aside_broken_cryptg()
