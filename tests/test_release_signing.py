"""The release file signed by the release key, and the build's own checks: the libraries' versions,
and the code signing certificate where there is one."""
import json
import os
import tempfile
import unittest
from unittest import mock

import rsa

import build
from core import signing, updates

# Small keys: as good as big ones for checking the logic, and made in an instant.
PUBLIC, PRIVATE = rsa.newkeys(512)
OTHER_PUBLIC, OTHER_PRIVATE = rsa.newkeys(512)
PAGE = "https://example.org/releases/tag/v99.0.0"


def release(**changes):
    info = {"version": "99.0.0", "url": PAGE, "notes": {"ar": "جديد", "en": "new"}}
    info.update(changes)
    return info


class SignatureTest(unittest.TestCase):
    def read(self, info, keys=(PUBLIC,)):
        with mock.patch.object(updates, "trusted_keys", lambda: keys):
            return updates.read_release(json.dumps(info, ensure_ascii=False), "en")

    def test_a_file_signed_by_the_release_key_is_taken(self):
        self.assertEqual(self.read(signing.sign(release(), PRIVATE))["version"], "99.0.0")

    def test_unsigned_or_signed_by_another_key_or_changed_after_it_is_refused(self):
        self.assertIsNone(self.read(release()))
        self.assertIsNone(self.read(signing.sign(release(), OTHER_PRIVATE)))
        changed = signing.sign(release(), PRIVATE)
        changed["url"] = "https://example.org/somewhere-else"
        self.assertIsNone(self.read(changed))
        broken = dict(signing.sign(release(), PRIVATE), signature="not base64 !")
        self.assertIsNone(self.read(broken))

    def test_the_layout_of_the_file_does_not_matter_only_its_content(self):
        signed = signing.sign(release(), PRIVATE)
        # Written back with other spacing and order, as an editor may: still the same release.
        rewritten = json.loads(json.dumps(dict(reversed(list(signed.items()))), indent=2))
        self.assertTrue(signing.is_signed_by(rewritten, (PUBLIC,)))

    def test_while_a_key_is_replaced_either_one_is_taken(self):
        self.assertIsNotNone(self.read(signing.sign(release(), OTHER_PRIVATE), keys=(PUBLIC, OTHER_PUBLIC)))

    def test_a_copy_built_without_a_key_takes_unsigned_files(self):
        self.assertIsNotNone(self.read(release(), keys=()))

    def test_keys_are_read_one_after_another_from_one_file(self):
        path = os.path.join(tempfile.mkdtemp(), "keys.pem")
        with open(path, "wb") as keys_file:
            keys_file.write(PUBLIC.save_pkcs1() + OTHER_PUBLIC.save_pkcs1())
        self.assertEqual(signing.load_public_keys(path), (PUBLIC, OTHER_PUBLIC))
        self.assertEqual(signing.load_public_keys(path + ".missing"), ())

    def test_the_program_ships_the_release_key_it_trusts(self):
        self.assertGreaterEqual(len(signing.load_public_keys()), 1)


class BuildSigningTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "update.json")
        with open(self.path, "w", encoding="utf-8") as info_file:
            json.dump(release(), info_file, ensure_ascii=False)

    def test_the_build_signs_the_file_and_the_program_takes_it(self):
        self.assertTrue(build.sign_release_file(self.path, PRIVATE, (PUBLIC,)))
        with open(self.path, encoding="utf-8") as info_file:
            data = info_file.read()
        with mock.patch.object(updates, "trusted_keys", lambda: (PUBLIC,)):
            self.assertEqual(updates.read_release(data, "ar")["notes"], "جديد")

    def test_signing_again_after_the_notes_are_written_keeps_it_valid(self):
        build.sign_release_file(self.path, PRIVATE, (PUBLIC,))
        with open(self.path, encoding="utf-8") as info_file:
            info = json.load(info_file)
        info["notes"]["ar"] = "ما الجديد: كذا وكذا"
        with open(self.path, "w", encoding="utf-8") as info_file:
            json.dump(info, info_file, ensure_ascii=False)
        self.assertFalse(signing.is_signed_by(info, (PUBLIC,)))
        build.sign_release_file(self.path, PRIVATE, (PUBLIC,))
        with open(self.path, encoding="utf-8") as info_file:
            self.assertTrue(signing.is_signed_by(json.load(info_file), (PUBLIC,)))

    def test_the_build_stops_rather_than_ship_what_the_copies_installed_would_refuse(self):
        with mock.patch.object(build, "load_signing_key", lambda: None), self.assertRaises(SystemExit):
            build.sign_release_file(self.path, None, (PUBLIC,))
        # A key that is not the one the program trusts.
        with self.assertRaises(SystemExit):
            build.sign_release_file(self.path, OTHER_PRIVATE, (PUBLIC,))

    def test_without_a_trusted_key_the_file_is_left_unsigned(self):
        self.assertFalse(build.sign_release_file(self.path, PRIVATE, ()))


class ReleaseNotesTest(unittest.TestCase):
    def test_the_notes_of_the_version_are_read_and_missing_ones_are_empty(self):
        path = os.path.join(tempfile.mkdtemp(), "release_notes.json")
        with open(path, "w", encoding="utf-8") as notes_file:
            json.dump({"99.0.0": {"ar": " جديد \n", "en": "new"}, "98.0.0": {"ar": "قديم"}}, notes_file)
        self.assertEqual(build.release_notes("99.0.0", path), {"ar": "جديد", "en": "new"})
        self.assertEqual(build.release_notes("98.0.0", path), {"ar": "قديم", "en": ""})
        self.assertEqual(build.release_notes("97.0.0", path), {"ar": "", "en": ""})
        self.assertEqual(build.release_notes("99.0.0", path + ".missing"), {"ar": "", "en": ""})

    def test_this_version_has_its_notes_in_every_language(self):
        # So no release is offered to the users without saying what it brings.
        for language, text in build.release_notes().items():
            self.assertTrue(text, "release_notes.json has no %s notes for this version" % language)

    def test_the_built_release_file_carries_the_notes_and_its_signature_holds(self):
        folder = tempfile.mkdtemp()
        packages = {}
        for kind in build.PACKAGES:
            packages[kind] = os.path.join(folder, kind + ".exe")
            with open(packages[kind], "wb") as package:
                package.write(b"installer")
        path = os.path.join(folder, "update.json")
        with mock.patch.object(build, "PACKAGES", packages), mock.patch.object(build, "UPDATE_INFO_FILE", path), \
                mock.patch.object(build, "load_signing_key", lambda: PRIVATE), \
                mock.patch.object(signing, "load_public_keys", lambda *args: (PUBLIC,)), \
                mock.patch("builtins.print"):
            build.write_update_info()
        with open(path, encoding="utf-8") as info_file:
            data = info_file.read()
        with mock.patch.object(updates, "trusted_keys", lambda: (PUBLIC,)):
            self.assertEqual(updates.read_release(data, "ar")["notes"], build.release_notes()["ar"])


class VersionPinsTest(unittest.TestCase):
    def test_pins_are_read_from_the_requirements(self):
        path = os.path.join(tempfile.mkdtemp(), "requirements.txt")
        with open(path, "w", encoding="utf-8") as requirements:
            requirements.write("# a note\nwxPython==4.2.5\npython-socks[asyncio]==3.2.1  # proxy\nloose>=1\n-r other.txt\n")
        self.assertEqual(build.pinned_versions([path]), {"wxpython": "4.2.5", "python-socks": "3.2.1"})

    def test_any_other_version_or_a_missing_library_is_found(self):
        installed = {"wxpython": "4.2.5", "numpy": "2.6.0"}

        def version(name):
            if name not in installed:
                raise ImportError(name)
            return installed[name]
        pins = {"wxpython": "4.2.5", "numpy": "2.5.4", "av": "19.0.2"}
        self.assertEqual(build.version_mismatches(pins, version), [("av", "19.0.2", None), ("numpy", "2.5.4", "2.6.0")])

    def test_the_project_pins_every_library_it_uses(self):
        pins = build.pinned_versions()
        for name in ("wxpython", "telethon", "rsa", "av", "numpy", "sounddevice", "python-socks", "pyinstaller"):
            self.assertIn(name, pins)


class AuthenticodeTest(unittest.TestCase):
    def test_a_certificate_file_or_one_in_the_store_is_named_to_signtool(self):
        pfx = os.path.join(tempfile.mkdtemp(), "omnya.pfx")
        open(pfx, "wb").close()
        command = build.signtool_command("signtool.exe", pfx, "secret", ["a.exe", "b.exe"])
        self.assertEqual(command[-6:], ["/f", pfx, "/p", "secret", "a.exe", "b.exe"])
        self.assertIn(build.TIMESTAMP_URL, command)
        command = build.signtool_command("signtool.exe", "AB CD 12", None, ["a.exe"])
        self.assertEqual(command[-3:], ["/sha1", "ABCD12", "a.exe"])

    def test_without_a_certificate_nothing_is_signed(self):
        with mock.patch.dict(os.environ, {build.SIGN_CERTIFICATE_ENV: ""}), \
                mock.patch.object(build, "run", side_effect=AssertionError("ran signtool")):
            self.assertFalse(build.authenticode(["a.exe"]))
