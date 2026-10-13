"""Reaching Telegram through a proxy, for where it cannot be reached directly."""
import base64
from urllib.parse import parse_qs, urlsplit

from core.constants import (
    PROXY_NONE, PROXY_SOCKS5, PROXY_MTPROTO, ERR_PROXY_HOST_KEY, ERR_PROXY_PORT_KEY,
    ERR_PROXY_SECRET_KEY, ERR_PROXY_FAKE_TLS_KEY, EMPTY_STRING
)
from core.settings import (
    SETTING_PROXY_TYPE, SETTING_PROXY_HOST, SETTING_PROXY_PORT, SETTING_PROXY_USER,
    SETTING_PROXY_PASSWORD, SETTING_PROXY_SECRET
)

# The start of a secret that asks for the disguise as a web connection, which Telethon cannot do.
FAKE_TLS_PREFIX = "ee"
SECRET_BYTES = 16
# What a proxy link is called in each of its spellings: tg://proxy, https://t.me/socks ...
LINK_KINDS = {"proxy": PROXY_MTPROTO, "socks": PROXY_SOCKS5}


def no_proxy():
    return {"type": PROXY_NONE, "host": EMPTY_STRING, "port": EMPTY_STRING, "user": EMPTY_STRING,
            "password": EMPTY_STRING, "secret": EMPTY_STRING}


def from_settings(settings):
    """The proxy as the settings hold it: {"type", "host", "port", "user", "password", "secret"}, all text."""
    return {
        "type": settings.get(SETTING_PROXY_TYPE), "host": settings.get(SETTING_PROXY_HOST),
        "port": settings.get(SETTING_PROXY_PORT), "user": settings.get(SETTING_PROXY_USER),
        "password": settings.get(SETTING_PROXY_PASSWORD), "secret": settings.get(SETTING_PROXY_SECRET),
    }


def to_settings(settings, proxy):
    for setting, field in (
        (SETTING_PROXY_TYPE, "type"), (SETTING_PROXY_HOST, "host"), (SETTING_PROXY_PORT, "port"),
        (SETTING_PROXY_USER, "user"), (SETTING_PROXY_PASSWORD, "password"), (SETTING_PROXY_SECRET, "secret"),
    ):
        settings.set(setting, proxy[field])


def parse_link(text):
    """A proxy from one of Telegram's own links (tg://proxy?..., https://t.me/socks?...); None for anything else."""
    parts = urlsplit(text.strip())
    # tg://proxy keeps the kind where a web address keeps its host; t.me/proxy keeps it in the path.
    kind = parts.netloc if parts.scheme == "tg" else parts.path.strip("/")
    if kind not in LINK_KINDS or (parts.scheme != "tg" and parts.netloc.lower() not in ("t.me", "telegram.me")):
        return None
    values = {name: found[0] for name, found in parse_qs(parts.query).items()}
    if not values.get("server") or not values.get("port"):
        return None
    proxy = no_proxy()
    proxy.update(
        type=LINK_KINDS[kind], host=values["server"], port=values["port"],
        user=values.get("user", EMPTY_STRING), password=values.get("pass", EMPTY_STRING),
        secret=values.get("secret", EMPTY_STRING)
    )
    return proxy


def secret_bytes(secret):
    """The secret of an MTProto proxy as bytes, written in hex or in base64; b"" if it is neither."""
    try:
        return bytes.fromhex(secret)
    except ValueError:
        pass
    try:
        # Links carry it in the web-safe alphabet, often with the padding cut off.
        return base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4))
    except ValueError:
        return b""


def error_key(proxy):
    """What is wrong with a proxy as filled in, as a locale key; None if it can be tried."""
    if proxy["type"] == PROXY_NONE:
        return None
    if not proxy["host"].strip():
        return ERR_PROXY_HOST_KEY
    if not proxy["port"].isdigit() or not 0 < int(proxy["port"]) < 65536:
        return ERR_PROXY_PORT_KEY
    if proxy["type"] == PROXY_MTPROTO:
        secret = proxy["secret"].strip()
        if secret.lower().startswith(FAKE_TLS_PREFIX):
            return ERR_PROXY_FAKE_TLS_KEY
        if len(secret_bytes(secret)) < SECRET_BYTES:
            return ERR_PROXY_SECRET_KEY
    return None


def client_arguments(proxy):
    """What to hand Telethon's client so that it connects through the proxy; nothing for a direct connection."""
    if proxy is None or proxy["type"] == PROXY_NONE or error_key(proxy):
        return {}
    host, port = proxy["host"].strip(), int(proxy["port"])
    if proxy["type"] == PROXY_MTPROTO:
        from telethon.network import connection
        return {
            "connection": connection.ConnectionTcpMTProxyRandomizedIntermediate,
            "proxy": (host, port, proxy["secret"].strip()),
        }
    return {"proxy": {
        "proxy_type": "socks5", "addr": host, "port": port,
        "username": proxy["user"] or None, "password": proxy["password"] or None,
        # Names are looked up by the proxy: where Telegram is blocked, so may be its name.
        "rdns": True,
    }}
