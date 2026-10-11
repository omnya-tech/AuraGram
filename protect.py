"""protect — one standalone file that makes a Python program resist tampering. Free, no dependencies.

Copy this single file into any project (that is all you copy) and either import it or run it.
It needs only the Python standard library, and imports nothing from the project around it, so
it is the same file everywhere. Change PASSPHRASE below, or pass your own, per project.

It does two things:

  * A sealed MANIFEST of file fingerprints, and `verify`, to tell whether the program's files
    are exactly as shipped. Refuse to run, or log, when something was changed.

  * `lock_to_files` / `unlock_to_files`, which lock a secret (an API key, a config, a licence)
    under a key DERIVED FROM those same files. Alter a file and the secret comes back as
    rubbish, not as an error — there is no yes/no check for a cracker to patch out, so a
    tampered copy breaks itself instead of merely being "detected".

What it cannot do: stop someone who fully takes the program apart. The program must be able to
read its own secrets to run, so nothing on the user's machine can. The point is to make tampering
not pay off, and the code not worth reading. Pair it with a compiler such as Nuitka
(`pip install nuitka`, then `python -m nuitka --standalone ...`): this file makes a changed copy
misbehave, Nuitka makes the code hard to read in the first place.

Use as a library:

    import protect
    blob = protect.lock_to_files(api_key, "a phrase inside your code", root, ["main.pyc", "data.bin"])
    key  = protect.unlock_to_files(blob, "a phrase inside your code", root, ["main.pyc", "data.bin"], strict=False)

Use from the command line:

    python protect.py seal <passphrase> <manifest-out> <root> <file>...   # seal a manifest at build time
    python protect.py verify <passphrase> <manifest> <root>              # check the files against it
    python protect.py demo                                               # show "tamper -> broken" in a temp folder
"""
import hashlib
import hmac
import json
import os
import sys

# Change this per project, and keep it inside your (compiled) code. Passed explicitly to the
# functions below; this is only the default the command line uses when none is given.
PASSPHRASE = "change-this-phrase-per-project"

_SALT = 16            # bytes of random salt, so the same secret never looks the same twice
_TAG = 16             # bytes of authentication tag
_READ_BLOCK = 65536
_SCHEME = b"protect-v1"   # bumped if the sealing ever changes, so an old blob is seen as foreign


def _digest_file(path):
    """A file's SHA-256, or a fixed stand-in for one that is missing or unreadable
    (its absence is itself part of the fingerprint)."""
    sha = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_READ_BLOCK), b""):
                sha.update(chunk)
    except OSError:
        return b"\x00" * 32
    return sha.digest()


def fingerprint(root, paths):
    """One digest over the named files and their names, in the order given. `paths` are relative
    to `root`. Changing, adding (to the list), removing or renaming any of them changes the result."""
    overall = hashlib.sha256()
    for relative in paths:
        overall.update(relative.encode("utf-8") + b"\x00")
        overall.update(_digest_file(os.path.join(root, relative)))
        overall.update(b"\x00")
    return overall.digest()


def _stream(key, length):
    """A keystream as long as needed, from a key, using only hashing."""
    blocks, counter = b"", 0
    while len(blocks) < length:
        blocks += hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
        counter += 1
    return blocks[:length]


def _xor(data, key):
    return bytes(byte ^ pad for byte, pad in zip(data, _stream(key, len(data))))


def _key(passphrase, binding, salt):
    """The sealing key: the passphrase, whatever the secret is bound to, and the salt, folded
    together so none of the three can be recovered from the blob alone."""
    material = _SCHEME + passphrase.encode("utf-8") + binding
    return hashlib.sha256(salt + hashlib.sha256(material).digest() + salt[::-1]).digest()


def lock(secret, passphrase=PASSPHRASE, binding=b""):
    """Seal `secret` (bytes or str) into an opaque blob. A fresh salt each time. `binding` ties
    it to extra bytes (e.g. a file fingerprint) that must match again to get the secret back."""
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    salt = os.urandom(_SALT)
    key = _key(passphrase, binding, salt)
    body = _xor(secret, key)
    tag = hmac.new(key, body, hashlib.sha256).digest()[:_TAG]
    return salt + tag + body


def unlock(blob, passphrase=PASSPHRASE, binding=b""):
    """The bytes sealed by `lock`, or None if the blob is damaged, foreign, or the passphrase or
    binding do not match. Use this where a clean yes/no is wanted."""
    if len(blob) < _SALT + _TAG:
        return None
    salt, tag, body = blob[:_SALT], blob[_SALT:_SALT + _TAG], blob[_SALT + _TAG:]
    key = _key(passphrase, binding, salt)
    if not hmac.compare_digest(tag, hmac.new(key, body, hashlib.sha256).digest()[:_TAG]):
        return None
    return _xor(body, key)


def lock_to_files(secret, passphrase, root, paths):
    """Seal `secret` so it can only be recovered while `paths` are unchanged."""
    return lock(secret, passphrase, binding=fingerprint(root, paths))


def unlock_to_files(blob, passphrase, root, paths, strict=True):
    """The secret sealed by `lock_to_files`.

    `strict` True (the default) returns None if any of the files was changed — a clean check,
    good for a program that should refuse to run tampered.

    `strict` False always returns bytes: the real secret if the files are intact, and unusable
    rubbish if they are not, with no way to tell which from the call. Bind a secret the program
    genuinely needs this way, and a cracked copy breaks itself."""
    if strict:
        return unlock(blob, passphrase, binding=fingerprint(root, paths))
    if len(blob) < _SALT + _TAG:
        return b""
    salt, body = blob[:_SALT], blob[_SALT + _TAG:]
    return _xor(body, _key(passphrase, fingerprint(root, paths), salt))


def seal_manifest(root, paths, passphrase=PASSPHRASE):
    """A sealed list of the files' fingerprints, to write beside the program at build time.
    `verify` reads it back. Editing it without the passphrase is detected."""
    entries = {relative: _digest_file(os.path.join(root, relative)).hex() for relative in paths}
    plain = json.dumps(entries, sort_keys=True).encode("utf-8")
    return lock(plain, passphrase)


def verify(manifest_blob, root, passphrase=PASSPHRASE):
    """Check the program's files against a sealed manifest. Returns (ok, changed), where `changed`
    lists the files that differ, or ["<manifest>"] if the manifest itself was tampered with."""
    plain = unlock(manifest_blob, passphrase)
    if plain is None:
        return False, ["<manifest>"]
    try:
        entries = json.loads(plain)
    except ValueError:
        return False, ["<manifest>"]
    changed = [
        relative for relative, expected in entries.items()
        if _digest_file(os.path.join(root, relative)).hex() != expected
    ]
    return not changed, sorted(changed)


# ---------------------------------------------------------------------------- command line

def _cli_seal(passphrase, out, root, files):
    with open(out, "wb") as handle:
        handle.write(seal_manifest(root, files, passphrase))
    print("Sealed %d files into %s" % (len(files), out))
    return 0


def _cli_verify(passphrase, manifest, root):
    with open(manifest, "rb") as handle:
        ok, changed = verify(handle.read(), root, passphrase)
    if ok:
        print("Intact: every file matches the manifest.")
        return 0
    print("CHANGED:", ", ".join(changed))
    return 1


def _cli_demo():
    import tempfile
    root = tempfile.mkdtemp()
    name = "program.bin"
    path = os.path.join(root, name)
    with open(path, "wb") as handle:
        handle.write(b"the compiled program")
    secret = b"the-real-api-key"
    blob = lock_to_files(secret, "demo-phrase", root, [name])
    print("sealed a secret against", name)
    print("  intact  -> strict:", unlock_to_files(blob, "demo-phrase", root, [name]))
    with open(path, "ab") as handle:
        handle.write(b" patched")
    print("changed the file (as a cracker would)")
    spoiled = unlock_to_files(blob, "demo-phrase", root, [name], strict=False)
    print("  tampered -> strict:", unlock_to_files(blob, "demo-phrase", root, [name]), "(refused)")
    print("  tampered -> loose :", spoiled.hex(), "(rubbish, not the secret:", spoiled != secret, ")")
    return 0


def main(argv):
    if len(argv) >= 5 and argv[1] == "seal":
        return _cli_seal(argv[2], argv[3], argv[4], argv[5:])
    if len(argv) == 5 and argv[1] == "verify":
        return _cli_verify(argv[2], argv[3], argv[4])
    if len(argv) == 2 and argv[1] == "demo":
        return _cli_demo()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
