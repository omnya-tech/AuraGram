"""The reusable tamper-resistance module: sealing, revealing, binding to files, and the manifest."""
import os
import tempfile
import unittest

import protect as integrity


class SealingTest(unittest.TestCase):
    def test_a_secret_comes_back_only_with_the_right_passphrase(self):
        blob = integrity.lock("api-key-12345", "my passphrase")
        self.assertEqual(integrity.unlock(blob, "my passphrase"), b"api-key-12345")
        self.assertIsNone(integrity.unlock(blob, "wrong passphrase"))

    def test_the_blob_shows_neither_the_secret_nor_itself_twice(self):
        blob = integrity.lock("0123456789abcdef0123456789abcdef", "pass")
        self.assertNotIn(b"0123456789abcdef", blob)
        self.assertNotIn(b"pass", blob)
        self.assertNotEqual(blob, integrity.lock("0123456789abcdef0123456789abcdef", "pass"))

    def test_a_touched_or_foreign_blob_unlocks_to_nothing(self):
        blob = bytearray(integrity.lock("secret", "pass"))
        for position in (0, len(blob) // 2, len(blob) - 1):
            damaged = bytearray(blob)
            damaged[position] ^= 1
            self.assertIsNone(integrity.unlock(bytes(damaged), "pass"))
        self.assertIsNone(integrity.unlock(b"not a real blob at all", "pass"))
        self.assertIsNone(integrity.unlock(b"", "pass"))


class FileBindingTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.paths = ["app.pyc", "data/thing.bin"]
        for relative, content in zip(self.paths, (b"program code", b"the data")):
            full = os.path.join(self.root, relative)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as handle:
                handle.write(content)

    def touch(self, relative):
        with open(os.path.join(self.root, relative), "ab") as handle:
            handle.write(b"x")

    def test_fingerprint_changes_with_any_file_and_is_steady_otherwise(self):
        before = integrity.fingerprint(self.root, self.paths)
        self.assertEqual(before, integrity.fingerprint(self.root, self.paths))
        self.touch("app.pyc")
        self.assertNotEqual(before, integrity.fingerprint(self.root, self.paths))

    def test_secret_bound_to_files_returns_only_while_they_are_intact(self):
        blob = integrity.lock_to_files("live-api-key", "pass", self.root, self.paths)
        self.assertEqual(integrity.unlock_to_files(blob, "pass", self.root, self.paths), b"live-api-key")
        self.touch("data/thing.bin")
        # Strict: a clean refusal.
        self.assertIsNone(integrity.unlock_to_files(blob, "pass", self.root, self.paths))

    def test_loose_mode_hands_back_rubbish_instead_of_refusing(self):
        secret = b"this is the real secret value"
        blob = integrity.lock_to_files(secret, "pass", self.root, self.paths)
        intact = integrity.unlock_to_files(blob, "pass", self.root, self.paths, strict=False)
        self.assertEqual(intact, secret)
        self.touch("app.pyc")
        spoiled = integrity.unlock_to_files(blob, "pass", self.root, self.paths, strict=False)
        # Same length, no error, but not the secret: nothing to branch on, nothing to use.
        self.assertEqual(len(spoiled), len(secret))
        self.assertNotEqual(spoiled, secret)

    def test_a_missing_file_is_as_much_tampering_as_a_changed_one(self):
        blob = integrity.lock_to_files("key", "pass", self.root, self.paths)
        os.remove(os.path.join(self.root, "app.pyc"))
        self.assertIsNone(integrity.unlock_to_files(blob, "pass", self.root, self.paths))


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.paths = ["one.txt", "two.txt"]
        for relative in self.paths:
            with open(os.path.join(self.root, relative), "wb") as handle:
                handle.write(relative.encode())

    def test_an_intact_program_verifies_and_a_changed_file_is_named(self):
        manifest = integrity.seal_manifest(self.root, self.paths, "pass")
        ok, changed = integrity.verify(manifest, self.root, "pass")
        self.assertTrue(ok)
        self.assertEqual(changed, [])
        with open(os.path.join(self.root, "two.txt"), "ab") as handle:
            handle.write(b"!")
        ok, changed = integrity.verify(manifest, self.root, "pass")
        self.assertFalse(ok)
        self.assertEqual(changed, ["two.txt"])

    def test_a_tampered_manifest_is_caught_as_a_whole(self):
        manifest = bytearray(integrity.seal_manifest(self.root, self.paths, "pass"))
        manifest[-1] ^= 1
        ok, changed = integrity.verify(bytes(manifest), self.root, "pass")
        self.assertFalse(ok)
        self.assertEqual(changed, ["<manifest>"])
        # The wrong passphrase cannot read it either.
        good = integrity.seal_manifest(self.root, self.paths, "pass")
        self.assertEqual(integrity.verify(good, self.root, "other"), (False, ["<manifest>"]))


if __name__ == "__main__":
    unittest.main()
