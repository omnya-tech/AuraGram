"""Signing the release file (update.json), and checking a signature, so a copy of the program takes an
update only from whoever holds the release key.

The size and SHA-256 of each installer are in update.json; the file itself is signed, so whoever could
change the file where it is published (the GitHub account, the way to it) could not make it point to
an installer of their own without the key, which never leaves the computer the releases are built on.

The signature is RSA (PKCS#1 v1.5, SHA-256), with the `rsa` library Telethon itself depends on, over the
file's content written out one fixed way (canonical), and kept in the file under SIGNATURE_FIELD.
Copies too old to know of it read the rest as ever.
"""
import base64
import json
import os

import rsa

from core.constants import RESOURCE_DIR

SIGNATURE_FIELD = "signature"
HASH_METHOD = "SHA-256"
KEY_BITS = 3072
# The public keys the program trusts, one after another in one file; more than one while a key is
# being replaced. Shipped with the program; none (no file) leaves releases unsigned, as in a copy built
# from the published code by someone else.
TRUSTED_KEYS_FILE = os.path.join(RESOURCE_DIR, "assets", "update_keys.pem")
PEM_END = b"-----END RSA PUBLIC KEY-----"


def canonical(info):
    """The release file's content, without its signature, as the bytes that are signed."""
    unsigned = {key: value for key, value in info.items() if key != SIGNATURE_FIELD}
    return json.dumps(unsigned, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sign(info, private_key):
    """`info` with its signature added, by a private key (rsa.PrivateKey)."""
    signature = rsa.sign(canonical(info), private_key, HASH_METHOD)
    return dict(info, **{SIGNATURE_FIELD: base64.b64encode(signature).decode("ascii")})


def is_signed_by(info, public_keys):
    """Whether `info` carries a signature that one of `public_keys` (rsa.PublicKey) made."""
    signature = info.get(SIGNATURE_FIELD)
    if not isinstance(signature, str):
        return False
    try:
        signature = base64.b64decode(signature, validate=True)
    except ValueError:
        return False
    message = canonical(info)
    for key in public_keys:
        try:
            rsa.verify(message, signature, key)
            return True
        except rsa.VerificationError:
            continue
    return False


def load_public_keys(path=TRUSTED_KEYS_FILE):
    """The trusted public keys; () if there is no file of them."""
    try:
        with open(path, "rb") as keys_file:
            data = keys_file.read()
    except OSError:
        return ()
    blocks = [block + PEM_END for block in data.split(PEM_END) if block.strip()]
    return tuple(rsa.PublicKey.load_pkcs1(block) for block in blocks)


def make_keys(bits=KEY_BITS):
    """A new (public, private) pair. Pure Python: a key of 3072 bits takes a minute or so."""
    return rsa.newkeys(bits, poolsize=max(1, min(8, os.cpu_count() or 1)))
