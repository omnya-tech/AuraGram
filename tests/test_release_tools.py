"""What a released program needs around the chats: a way past a block, news of updates, a trace of errors, picture descriptions."""
import hashlib
import json
import logging
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

import wx

import core.constants as c
import core.settings as s
import ui.help_menu
import ui.message_actions
from core import diagnostics, proxy, updates, vision
from tests.harness import FakeChooser, FakeTelegramClient, WindowTestCase, make_message, make_user, pump
from ui.login_frame import LoginFrame
from ui.proxy_dialog import ProxyDialog
from ui.settings_dialog import SettingsDialog

ALI = make_user(1, "Ali")
SECRET = "0123456789abcdef0123456789abcdef"


def a_proxy(**changes):
    values = proxy.no_proxy()
    values.update(changes)
    return values


class ProxyRulesTest(unittest.TestCase):
    def test_both_kinds_of_link_are_read_in_both_spellings(self):
        mtproto = proxy.parse_link("tg://proxy?server=1.2.3.4&port=443&secret=" + SECRET)
        self.assertEqual((mtproto["type"], mtproto["host"], mtproto["port"], mtproto["secret"]),
                         (c.PROXY_MTPROTO, "1.2.3.4", "443", SECRET))
        socks = proxy.parse_link(" https://t.me/socks?server=example.org&port=1080&user=me&pass=pw ")
        self.assertEqual((socks["type"], socks["host"], socks["port"], socks["user"], socks["password"]),
                         (c.PROXY_SOCKS5, "example.org", "1080", "me", "pw"))

    def test_other_text_is_not_a_proxy_link(self):
        for text in ("", "hello", "https://t.me/someone", "https://example.org/proxy?server=a&port=1",
                     "tg://proxy?server=a"):
            self.assertIsNone(proxy.parse_link(text), text)

    def test_what_is_filled_in_wrong_is_named(self):
        self.assertIsNone(proxy.error_key(a_proxy()))
        socks = dict(type=c.PROXY_SOCKS5, host="example.org", port="1080")
        self.assertIsNone(proxy.error_key(a_proxy(**socks)))
        self.assertEqual(proxy.error_key(a_proxy(**dict(socks, host=" "))), c.ERR_PROXY_HOST_KEY)
        for port in ("", "0", "70000", "abc"):
            self.assertEqual(proxy.error_key(a_proxy(**dict(socks, port=port))), c.ERR_PROXY_PORT_KEY)
        mtproto = dict(type=c.PROXY_MTPROTO, host="1.2.3.4", port="443")
        self.assertIsNone(proxy.error_key(a_proxy(secret=SECRET, **mtproto)))
        self.assertIsNone(proxy.error_key(a_proxy(secret="dd" + SECRET, **mtproto)))
        self.assertEqual(proxy.error_key(a_proxy(secret="short", **mtproto)), c.ERR_PROXY_SECRET_KEY)
        self.assertEqual(proxy.error_key(a_proxy(secret="ee" + SECRET + "6578", **mtproto)), c.ERR_PROXY_FAKE_TLS_KEY)

    def test_the_client_is_told_how_to_connect(self):
        self.assertEqual(proxy.client_arguments(None), {})
        self.assertEqual(proxy.client_arguments(a_proxy()), {})
        socks = proxy.client_arguments(a_proxy(type=c.PROXY_SOCKS5, host="example.org", port="1080", user="me"))
        self.assertEqual(socks["proxy"], {
            "proxy_type": "socks5", "addr": "example.org", "port": 1080, "username": "me", "password": None, "rdns": True
        })
        mtproto = proxy.client_arguments(a_proxy(type=c.PROXY_MTPROTO, host="1.2.3.4", port="443", secret=SECRET))
        self.assertEqual(mtproto["proxy"], ("1.2.3.4", 443, SECRET))
        self.assertIn("MTProxy", mtproto["connection"].__name__)
        # A proxy that cannot work is not half-used: the connection stays direct.
        self.assertEqual(proxy.client_arguments(a_proxy(type=c.PROXY_SOCKS5, host="", port="1")), {})


class ProxyWindowTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def open_dialog(self):
        dialog = ProxyDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(dialog.Destroy)
        dialog.EndModal = lambda code: setattr(dialog, "ended_with", code)
        return dialog

    def test_a_link_fills_the_form_and_ok_reconnects_through_it(self):
        dialog = self.open_dialog()
        dialog.link_input.SetValue("tg://socks?server=example.org&port=1080")
        dialog.on_fill(None)
        self.assertEqual(dialog.entered()["host"], "example.org")
        self.assertEqual(self.spoken[-1], self.text(c.MSG_PROXY_FILLED_KEY))
        chats_before = dict(self.manager.entities)
        dialog.on_ok(None)
        self.assertEqual(dialog.ended_with, wx.ID_OK)
        self.assertEqual(self.frame.settings.get(s.SETTING_PROXY_TYPE), c.PROXY_SOCKS5)
        self.assertTrue(pump(lambda: len(FakeTelegramClient.created_with) == 2 and self.manager.client.connected))
        self.assertEqual(FakeTelegramClient.created_with[-1]["proxy"]["addr"], "example.org")
        # The chats on screen go on working: what is known about them was kept.
        self.assertEqual(self.manager.entities, chats_before)

    def test_a_wrong_form_or_link_is_refused_with_the_reason(self):
        dialog = self.open_dialog()
        dialog.link_input.SetValue("not a link")
        dialog.on_fill(None)
        self.assertEqual(self.boxes[-1], self.text(c.ERR_PROXY_LINK_KEY))
        dialog.type_choice.SetSelection(c.PROXY_TYPES.index(c.PROXY_MTPROTO))
        dialog.inputs["host"].SetValue("1.2.3.4")
        dialog.inputs["port"].SetValue("443")
        dialog.on_ok(None)
        self.assertEqual(self.boxes[-1], self.text(c.ERR_PROXY_SECRET_KEY))
        self.assertFalse(hasattr(dialog, "ended_with"))
        self.assertEqual(len(FakeTelegramClient.created_with), 1)

    def test_login_window_keeps_the_proxy_button_usable_while_it_waits(self):
        login = LoginFrame(self.i18n, self.manager, self.frame.settings)
        self.addCleanup(login.Destroy)
        self.assertTrue(login.is_processing)
        self.assertTrue(login.proxy_btn.IsEnabled())
        self.assertFalse(login.phone_input.IsEnabled())
        login.set_step(c.STEP_PHONE)
        self.assertTrue(login.phone_input.IsEnabled())

    def test_settings_keep_the_gemini_key_and_the_update_choice(self):
        dialog = SettingsDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(dialog.Destroy)
        dialog.gemini_key_input.SetValue("  my-key  ")
        dialog.checkboxes[s.SETTING_CHECK_UPDATES].SetValue(False)
        dialog.apply_app_settings()
        reloaded = s.Settings()
        self.assertEqual(reloaded.get(s.SETTING_GEMINI_KEY), "my-key")
        self.assertFalse(reloaded.get(s.SETTING_CHECK_UPDATES))


PAGE = "https://example.org/releases/tag/v99.0.0"
CONTENT = b"installer bytes " * 1000


def package(content=CONTENT, name="setup.exe", **changes):
    described = {
        "url": "https://example.org/download/" + name, "sha256": hashlib.sha256(content).hexdigest(), "size": len(content)
    }
    described.update(changes)
    return described


def release_file(**changes):
    info = {"version": "99.0.0", "url": PAGE, "notes": {"ar": "جديد", "en": "new"}}
    info.update(changes)
    return json.dumps(info)


class UpdateRulesTest(unittest.TestCase):
    def test_versions_compare_as_numbers(self):
        self.assertTrue(updates.is_newer("1.10.0", "1.9.3"))
        self.assertTrue(updates.is_newer("v2.0", "1.9.3"))
        self.assertFalse(updates.is_newer("1.9.3", "1.9.3"))
        self.assertFalse(updates.is_newer("1.0", "1.0.1"))
        self.assertFalse(updates.is_newer("soon", "1.0.0"))

    def test_a_release_file_is_read_with_notes_in_the_users_language(self):
        release = updates.read_release(release_file(), "en")
        self.assertEqual(release, {"version": "99.0.0", "url": PAGE, "notes": "new", "packages": {}})
        self.assertEqual(updates.read_release(release_file(), "ar")["notes"], "جديد")

    def test_anything_odd_in_the_file_means_no_release(self):
        for data in ("not json", "[]", release_file(version="x"), release_file(url="http://example.org/page"),
                     release_file(url="file:///C:/setup.exe")):
            self.assertIsNone(updates.read_release(data, "ar"), data)

    def test_both_packages_are_offered_when_this_copy_can_take_them(self):
        data = release_file(full=package(), update=dict(package(name="update.exe"), **{"from": "1.0.0"}))
        packages = updates.read_release(data, "ar", installed="1.2.0")["packages"]
        self.assertEqual(set(packages), {c.PACKAGE_FULL, c.PACKAGE_UPDATE})
        self.assertEqual(packages[c.PACKAGE_FULL], package())

    def test_small_package_is_kept_from_a_copy_too_old_for_it(self):
        # Its libraries differ: only the whole installer would leave something that runs.
        data = release_file(full=package(), update=dict(package(), **{"from": "1.5.0"}))
        self.assertEqual(set(updates.read_release(data, "ar", installed="1.2.0")["packages"]), {c.PACKAGE_FULL})
        # And one that does not say what it fits over fits over nothing.
        data = release_file(update=package())
        self.assertEqual(updates.read_release(data, "ar", installed="1.2.0")["packages"], {})

    def test_a_package_that_cannot_be_checked_is_not_offered(self):
        for broken in (package(url="http://example.org/setup.exe"), package(sha256="abc"), package(sha256=None),
                       package(size=0), package(size="big"), package(size=c.UPDATE_MAX_BYTES + 1), "setup.exe"):
            release = updates.read_release(release_file(full=broken), "ar")
            # The release is still announced: its page can be opened in the browser.
            self.assertEqual(release["packages"], {}, broken)

    def test_no_address_means_no_asking(self):
        with mock.patch.object(updates, "UPDATE_INFO_URL", ""), \
                mock.patch.object(updates.urllib.request, "urlopen", side_effect=AssertionError("asked")):
            self.assertFalse(updates.is_configured())
            self.assertIsNone(updates.fetch_release("ar"))


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.target = os.path.join(tempfile.mkdtemp(), "downloads", "AuraGram-Setup.exe")

    def fetch(self, described, served=CONTENT, final_url=None, progress=None):
        response = Response(served, final_url or described["url"])
        with mock.patch.object(updates.urllib.request, "urlopen", lambda request, timeout: response):
            updates.download_package(described, self.target, progress)

    def left_behind(self):
        folder = os.path.dirname(self.target)
        return os.listdir(folder) if os.path.isdir(folder) else []

    def test_a_package_that_is_what_was_announced_is_kept(self):
        seen = []
        with mock.patch.object(updates, "UPDATE_CHUNK_BYTES", 4000):
            self.fetch(package(), progress=seen.append)
        with open(self.target, "rb") as saved:
            self.assertEqual(saved.read(), CONTENT)
        self.assertEqual(self.left_behind(), ["AuraGram-Setup.exe"])
        self.assertEqual(seen[-1], 100)
        self.assertEqual(seen, sorted(set(seen)))

    def refused(self, *args, **kwargs):
        with self.assertRaises(updates.DownloadError) as caught:
            self.fetch(*args, **kwargs)
        # Nothing that failed the check is left where it could be run by mistake.
        self.assertEqual(self.left_behind(), [])
        return caught.exception.error_key

    def test_a_file_that_differs_in_any_way_is_deleted(self):
        self.assertEqual(self.refused(package(), served=CONTENT[:-1] + b"!"), c.ERR_UPDATE_VERIFY_KEY)
        self.assertEqual(self.refused(package(), served=CONTENT[:-100]), c.ERR_UPDATE_VERIFY_KEY)
        self.assertEqual(self.refused(package(), served=CONTENT + b"more"), c.ERR_UPDATE_VERIFY_KEY)

    def test_an_address_that_hands_over_to_an_unchecked_one_is_refused(self):
        self.assertEqual(self.refused(package(), final_url="http://example.org/setup.exe"), c.ERR_UPDATE_VERIFY_KEY)

    def test_a_dropped_connection_is_a_failed_download_not_a_bad_file(self):
        with mock.patch.object(updates.urllib.request, "urlopen", side_effect=urllib.error.URLError("offline")):
            with self.assertRaises(updates.DownloadError) as caught:
                updates.download_package(package(), self.target)
        self.assertEqual(caught.exception.error_key, c.ERR_UPDATE_DOWNLOAD_KEY)
        self.assertEqual(self.left_behind(), [])

    def test_build_describes_a_file_the_way_the_program_checks_it(self):
        os.makedirs(os.path.dirname(self.target))
        with open(self.target, "wb") as built:
            built.write(CONTENT)
        described = updates.describe_file(self.target, "https://example.org/download/setup.exe")
        self.assertEqual(described, package())
        self.assertEqual(updates.read_package(described), described)


class UpdateWindowTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        self.opened, self.started, self.fetched = [], [], []
        self.failure = None
        patches = [
            mock.patch.object(ui.help_menu, "DOWNLOADS_DIR", self.folder),
            mock.patch.object(wx, "LaunchDefaultBrowser", self.opened.append),
            mock.patch.object(os, "startfile", self.started.append, create=True),
            mock.patch.object(updates, "download_package", self.download),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def download(self, described, target, on_progress=None):
        self.fetched.append((described["url"], os.path.basename(target)))
        for percent in (0, 10, 25, 50, 100):
            on_progress(percent)
        if self.failure:
            raise updates.DownloadError(self.failure)

    def release(self, **packages):
        return {"version": "99.0.0", "url": PAGE, "notes": "better", "packages": packages}

    def check(self, release, quiet=True):
        with mock.patch.object(updates, "fetch_release", lambda language: release):
            self.frame.check_for_updates(quiet=quiet)
            pump(timeout=0.4)

    def both(self):
        return self.release(full=package(), update=package(name="update.exe", size=8 * 1024 * 1024))

    def test_user_is_offered_the_update_alone_the_full_version_or_the_page(self):
        FakeChooser.confirmed = False
        self.check(self.both())
        self.assertIn("99.0.0", FakeChooser.last_message)
        self.assertIn("better", FakeChooser.last_message)
        text = self.text
        self.assertEqual(len(FakeChooser.last_choices), 3)
        self.assertTrue(FakeChooser.last_choices[0].startswith(text(c.UPDATE_CHOICE_FORMAT_KEYS[c.PACKAGE_UPDATE])[:8]))
        self.assertIn("8", FakeChooser.last_choices[0])
        self.assertEqual(FakeChooser.last_choices[2], text(c.UPDATE_CHOICE_PAGE_KEY))
        # Backing out fetches nothing and opens nothing.
        self.assertEqual((self.fetched, self.opened, self.started), ([], [], []))

    def test_chosen_update_is_downloaded_then_installed_only_after_a_yes(self):
        # How far it has come is said only to whoever asked to hear it.
        self.frame.settings.set(s.FEEDBACK_SETTINGS[c.FEEDBACK_PERCENT], True)
        FakeChooser.selection = 0
        self.check(self.both())
        self.assertEqual(self.fetched, [("https://example.org/download/update.exe", "AuraGram-Update-99.0.0.exe")])
        self.assertEqual(self.started, [os.path.join(self.folder, "AuraGram-Update-99.0.0.exe")])
        self.assertIn("99.0.0", self.boxes[-1])
        self.assertFalse(self.frame.update_downloading)
        # Progress was told at the quarters, not at every step.
        told = [line for line in self.spoken if line.startswith(self.text(c.MSG_UPDATE_DOWNLOADING_FORMAT_KEY)[:6])]
        self.assertEqual(len(told), 3)

    def test_full_version_can_be_chosen_and_kept_for_later(self):
        FakeChooser.selection = 1
        self.box_answer = wx.NO
        self.check(self.both())
        self.assertEqual(self.fetched[0][1], "AuraGram-Setup-99.0.0.exe")
        self.assertEqual(self.started, [])
        self.assertIn(os.path.join(self.folder, "AuraGram-Setup-99.0.0.exe"), self.boxes[-1])

    def test_only_what_this_copy_can_install_is_listed_and_the_page_always_is(self):
        FakeChooser.selection = 1
        self.check(self.release(full=package()))
        self.assertEqual(len(FakeChooser.last_choices), 2)
        self.assertEqual(self.opened, [PAGE])
        self.assertEqual(self.fetched, [])
        FakeChooser.selection = 0
        self.check(self.release())
        self.assertEqual(self.opened, [PAGE, PAGE])

    def test_a_download_that_fails_its_check_is_reported_and_never_run(self):
        self.failure = c.ERR_UPDATE_VERIFY_KEY
        FakeChooser.selection = 0
        self.check(self.both())
        self.assertEqual(self.boxes[-1], self.text(c.ERR_UPDATE_VERIFY_KEY))
        self.assertEqual(self.started, [])
        self.assertFalse(self.frame.update_downloading)

    def test_no_news_is_said_only_when_asked_for(self):
        same = dict(self.release(), version=c.APP_VERSION)
        self.spoken.clear()
        self.check(same)
        self.check(None)
        self.assertEqual((self.spoken, self.boxes), ([], []))
        self.check(same, quiet=False)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_UP_TO_DATE_FORMAT_KEY).format(current=c.APP_VERSION))
        self.check(None, quiet=False)
        self.assertEqual(self.spoken[-1], self.text(c.ERR_UPDATE_CHECK_KEY))

    def test_the_program_looks_by_itself_once_and_only_if_allowed(self):
        asked = []
        with mock.patch.object(updates, "is_configured", lambda: True), \
                mock.patch.object(self.frame, "check_for_updates", lambda quiet: asked.append(quiet)):
            self.frame.settings.set(s.SETTING_CHECK_UPDATES, False)
            self.frame.check_updates_once()
            self.assertEqual(asked, [])
            self.frame.settings.set(s.SETTING_CHECK_UPDATES, True)
            self.frame.check_updates_once()
            self.frame.check_updates_once()
            self.assertEqual(asked, [True])


class InstallerScriptTest(unittest.TestCase):
    def test_small_installer_brings_only_the_programs_own_files_and_needs_an_install(self):
        with open(os.path.join(c.BASE_DIR, "installer.iss"), encoding="utf-8") as script_file:
            script = script_file.read()
        small = script[script.index("[Files]"):].split("#else")[0]
        self.assertIn("#ifdef UpdateOnly", small)
        for part in ("{#AppExe}", "locales", "assets", c.BUNDLED_CONFIG_NAME, c.LICENSE_FILE_NAME, c.NOTICES_FILE_NAME):
            self.assertIn(part, small)
        # Never the whole folder: that is what makes it small.
        self.assertNotIn('dist\\{#AppName}\\*"', small)
        self.assertIn("NeedsFullInstall", script)
        self.assertEqual(script.count("#ifdef UpdateOnly") + script.count("#ifndef UpdateOnly"), script.count("#endif") - script.count("#ifndef App"))


class DiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.log = os.path.join(self.folder, "auragram.log")
        patch = mock.patch.object(diagnostics, "LOG_FILE", self.log)
        patch.start()
        self.addCleanup(patch.stop)

    def test_report_holds_the_description_the_versions_and_the_end_of_the_log(self):
        with open(self.log, "w", encoding="utf-8") as log_file:
            log_file.write("old line\n" + "x" * c.REPORT_LOG_BYTES + "\nthe last error\n")
        path = diagnostics.write_report(os.path.join(self.folder, "out"), "  it broke  ", ["Language: ar"])
        with open(path, encoding="utf-8") as report_file:
            report = report_file.read()
        self.assertIn(c.APP_NAME + " " + c.APP_VERSION, report)
        self.assertIn("Language: ar", report)
        self.assertIn("it broke", report)
        self.assertIn("the last error", report)
        self.assertNotIn("old line", report)

    def test_report_is_written_even_with_no_log_at_all(self):
        path = diagnostics.write_report(self.folder, "", [])
        self.assertTrue(os.path.getsize(path) > 0)

    def test_an_error_nobody_caught_is_logged_and_the_user_told_once(self):
        told = []
        hooks = (sys.excepthook, diagnostics.on_unexpected_error, diagnostics._last_notice)
        self.addCleanup(lambda: (setattr(sys, "excepthook", hooks[0]),
                                 setattr(diagnostics, "on_unexpected_error", hooks[1]),
                                 setattr(diagnostics, "_last_notice", hooks[2])))
        import threading
        self.addCleanup(setattr, threading, "excepthook", threading.excepthook)
        diagnostics.catch_unexpected_errors()
        diagnostics.on_unexpected_error = lambda: told.append(True)
        diagnostics._last_notice = 0.0
        with self.assertLogs(diagnostics.logger, logging.ERROR) as logged:
            for _ in range(3):
                try:
                    raise RuntimeError("the menu fell over")
                except RuntimeError:
                    sys.excepthook(*sys.exc_info())
        self.assertIn("the menu fell over", logged.output[0])
        self.assertEqual(len(logged.output), 3)
        self.assertEqual(told, [True])


class ProblemReportTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def test_menu_saves_a_report_and_shows_where(self):
        folder = tempfile.mkdtemp()
        shown = []
        FakeChooser.values = ["cannot hear new messages"]
        with mock.patch.object(ui.help_menu, "DOWNLOADS_DIR", folder), \
                mock.patch.object(os, "startfile", shown.append, create=True):
            self.frame.on_problem_report_menu(None)
        files = os.listdir(folder)
        self.assertEqual(len(files), 1)
        self.assertEqual(shown, [folder])
        self.assertIn(files[0], self.boxes[-1])
        with open(os.path.join(folder, files[0]), encoding="utf-8") as report_file:
            self.assertIn("cannot hear new messages", report_file.read())

    def test_backing_out_saves_nothing(self):
        FakeChooser.confirmed = False
        with mock.patch.object(diagnostics, "write_report", side_effect=AssertionError("written")):
            self.frame.on_problem_report_menu(None)


class Response:
    def __init__(self, body, url="https://example.org/"):
        self.body = body
        self.url = url
        self.position = 0

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=None):
        # In pieces when a size is asked for, as a real connection gives a large file.
        end = len(self.body) if size is None else min(self.position + size, len(self.body))
        piece, self.position = self.body[self.position:end], end
        return piece


def answer(text):
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()


class VisionRulesTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "photo.jpg")
        with open(self.path, "wb") as image_file:
            image_file.write(b"jpeg bytes")

    def test_picture_and_question_go_to_gemini_with_the_key_in_a_header(self):
        sent = []

        def urlopen(request, timeout):
            sent.append(request)
            return Response(answer("  A cat on a mat.  "))
        with mock.patch.object(vision.urllib.request, "urlopen", urlopen):
            self.assertEqual(vision.describe_image(self.path, " my-key ", "Describe"), "A cat on a mat.")
        request = sent[0]
        self.assertIn(c.GEMINI_MODEL + ":generateContent", request.full_url)
        self.assertNotIn("my-key", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "my-key")
        parts = json.loads(request.data)["contents"][0]["parts"]
        self.assertEqual(parts[0]["inline_data"], {"mime_type": "image/jpeg", "data": "anBlZyBieXRlcw=="})
        self.assertEqual(parts[1], {"text": "Describe"})

    def failure(self, raised):
        with mock.patch.object(vision.urllib.request, "urlopen", side_effect=raised),                 mock.patch.object(vision.time, "sleep"):
            with self.assertRaises(vision.VisionError) as caught:
                vision.describe_image(self.path, "key", "Describe")
        return caught.exception.error_key

    def http_error(self, status, body=b"{}"):
        import io as _io
        return urllib.error.HTTPError("https://x", status, "no", {}, _io.BytesIO(body))

    def test_each_way_of_failing_has_its_own_words(self):
        self.assertEqual(self.failure(self.http_error(400, b'{"error": {"details": [{"reason": "API_KEY_INVALID"}]}}')), c.ERR_VISION_KEY_KEY)
        self.assertEqual(self.failure(self.http_error(403)), c.ERR_VISION_KEY_KEY)
        self.assertEqual(self.failure(self.http_error(429)), c.ERR_VISION_QUOTA_KEY)
        self.assertEqual(self.failure(self.http_error(400)), c.ERR_VISION_FAILED_KEY)
        self.assertEqual(self.failure(self.http_error(503)), c.ERR_VISION_BUSY_KEY)
        # Google's service out of reach is not Telegram out of reach.
        self.assertEqual(self.failure(urllib.error.URLError("offline")), c.ERR_VISION_UNREACHABLE_KEY)
        self.assertEqual(self.failure(TimeoutError("The read operation timed out")), c.ERR_VISION_BUSY_KEY)

    def test_a_retired_model_gives_way_to_the_next(self):
        asked = []

        def urlopen(request, timeout):
            asked.append(request.full_url)
            if len(asked) == 1:
                raise self.http_error(404, b'{"error": {"message": "model not found"}}')
            return Response(answer("A dog."))
        with mock.patch.object(vision.urllib.request, "urlopen", urlopen), self.assertLogs("core.vision", "WARNING"):
            self.assertEqual(vision.describe_image(self.path, "key", "Describe"), "A dog.")
        self.assertIn(c.GEMINI_MODELS[0] + ":", asked[0])
        self.assertIn(c.GEMINI_MODELS[1] + ":", asked[1])

    def test_a_busy_model_gives_way_to_the_next(self):
        asked = []

        def urlopen(request, timeout):
            asked.append(request.full_url)
            if len(asked) == 1:
                raise self.http_error(503, b'{"error": {"status": "UNAVAILABLE"}}')
            return Response(answer("A bird."))
        with mock.patch.object(vision.urllib.request, "urlopen", urlopen), self.assertLogs("core.vision", "WARNING"):
            self.assertEqual(vision.describe_image(self.path, "key", "Describe", wait=lambda seconds: None), "A bird.")
        self.assertEqual(len(asked), 2)

    def test_a_busy_model_is_asked_again_then_googles_own_list_is_tried(self):
        asked, waits = [], []

        def urlopen(request, timeout):
            asked.append(request.full_url)
            if request.full_url == c.GEMINI_MODELS_URL:
                return Response(json.dumps({"models": [
                    {"name": "models/" + c.GEMINI_MODELS[0], "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-9-flash-lite", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/text-embedding", "supportedGenerationMethods": ["embedContent"]},
                ]}).encode())
            if "gemini-9-flash-lite" in request.full_url:
                return Response(answer("A boat."))
            raise self.http_error(503, b'{"error": {"status": "UNAVAILABLE"}}')
        with mock.patch.object(vision.urllib.request, "urlopen", urlopen), self.assertLogs("core.vision", "WARNING"):
            self.assertEqual(vision.describe_image(self.path, "key", "Describe", wait=waits.append), "A boat.")
        # Each of its own models twice, then the list, then the one model there it had not asked.
        self.assertEqual(len(asked), 2 * len(c.GEMINI_MODELS) + 2)
        self.assertEqual(waits, [c.GEMINI_BUSY_WAIT_SECONDS] * len(c.GEMINI_MODELS))

    def test_when_every_model_is_gone_it_says_so(self):
        with self.assertLogs("core.vision", "WARNING"):
            self.assertEqual(self.failure(self.http_error(404)), c.ERR_VISION_FAILED_KEY)

    def test_a_key_is_tried_without_sending_a_picture(self):
        sent = []

        def urlopen(request, timeout):
            sent.append(request)
            return Response(b'{"models": []}')
        with mock.patch.object(vision.urllib.request, "urlopen", urlopen):
            vision.check_key(" my-key ")
        self.assertEqual(sent[0].full_url, c.GEMINI_MODELS_URL)
        self.assertIsNone(sent[0].data)
        self.assertEqual(sent[0].get_header("X-goog-api-key"), "my-key")
        with mock.patch.object(vision.urllib.request, "urlopen", side_effect=self.http_error(403)),                 self.assertLogs("core.vision", "WARNING"):
            with self.assertRaises(vision.VisionError) as caught:
                vision.check_key("bad")
        self.assertEqual(caught.exception.error_key, c.ERR_VISION_KEY_KEY)

    def test_an_answer_without_words_is_a_refusal(self):
        for body in (b"{}", b"not json", json.dumps({"candidates": [{"finishReason": "SAFETY"}]}).encode(), answer("  ")):
            with mock.patch.object(vision.urllib.request, "urlopen", lambda request, timeout, body=body: Response(body)):
                with self.assertRaises(vision.VisionError) as caught:
                    vision.describe_image(self.path, "key", "Describe")
            self.assertEqual(caught.exception.error_key, c.ERR_VISION_NO_ANSWER_KEY)

    def test_what_is_not_a_still_picture_or_is_too_big_is_never_sent(self):
        self.assertIsNone(vision.image_mime_type("sticker.tgs"))
        self.assertEqual(vision.image_mime_type("Photo.PNG"), "image/png")
        with mock.patch.object(vision, "GEMINI_MAX_IMAGE_BYTES", 4), \
                mock.patch.object(vision.urllib.request, "urlopen", side_effect=AssertionError("sent")):
            with self.assertRaises(vision.VisionError) as caught:
                vision.describe_image(self.path, "key", "Describe")
        self.assertEqual(caught.exception.error_key, c.ERR_VISION_TOO_BIG_KEY)


class DescribePictureTest(WindowTestCase):
    chats = [(ALI, 0, False)]
    history = {1: [
        make_message(1, "just words", sender=ALI),
        make_message(2, "look", sender=ALI, photo=True),
    ]}

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp()
        self.asked = []
        self.shown = []
        self.outcome = "A red door."
        patches = [
            mock.patch.object(ui.message_actions, "VISION_TEMP_DIR", self.folder),
            mock.patch.object(ui.message_actions, "describe_image", self.describe),
            mock.patch.object(FakeTelegramClient, "download_media", self.download),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.frame.show_text = lambda title_key, text: self.shown.append((title_key, text))
        self.frame.settings.set(s.SETTING_GEMINI_KEY, "my-key")
        self.open_chat(0)

    async def download(self, message, file, progress_callback=None):
        path = os.path.join(file, self.file_name)
        with open(path, "wb") as image_file:
            image_file.write(b"picture")
        return path

    file_name = "photo.jpg"

    def describe(self, path, api_key, prompt):
        self.asked.append((os.path.exists(path), api_key, prompt))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def select(self, index):
        self.frame.messages_list.SetSelection(index)

    def test_picture_is_described_in_the_interface_language_and_not_kept(self):
        self.select(1)
        self.frame.on_describe_image_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_DESCRIBING_KEY))
        self.assertTrue(pump(lambda: self.shown == [(c.VISION_TITLE_KEY, "A red door.")]))
        self.assertEqual(self.asked, [(True, "my-key", self.text(c.VISION_PROMPT_KEY))])
        self.assertFalse(self.frame.is_busy)
        self.assertEqual(os.listdir(self.folder), [])

        # Asking again shows what was said the first time, without another request.
        self.frame.on_describe_image_menu(None)
        self.assertEqual(len(self.shown), 2)
        self.assertEqual(len(self.asked), 1)

    def test_without_a_key_the_user_is_told_where_to_put_one(self):
        self.frame.settings.set(s.SETTING_GEMINI_KEY, " ")
        self.select(1)
        self.frame.on_describe_image_menu(None)
        self.assertEqual(self.boxes[-1], self.text(c.MSG_VISION_NO_KEY_KEY))
        pump(timeout=0.1)
        self.assertEqual((self.asked, self.calls("download")), ([], []))

    def test_a_message_without_a_picture_sends_nothing(self):
        self.select(0)
        self.frame.on_describe_image_menu(None)
        self.assertEqual(self.spoken[-1], self.text(c.MSG_NOT_AN_IMAGE_KEY))
        self.assertEqual(self.asked, [])

    def test_a_file_that_turns_out_not_to_be_a_picture_is_not_sent(self):
        self.file_name = "sticker.tgs"
        self.select(1)
        self.frame.on_describe_image_menu(None)
        self.assertTrue(pump(lambda: self.spoken[-1] == self.text(c.MSG_NOT_AN_IMAGE_KEY)))
        self.assertEqual(self.asked, [])
        self.assertFalse(self.frame.is_busy)
        self.assertEqual(os.listdir(self.folder), [])

    def test_a_refused_key_is_reported_and_the_window_is_usable_again(self):
        self.outcome = vision.VisionError(c.ERR_VISION_KEY_KEY)
        self.select(1)
        self.frame.on_describe_image_menu(None)
        self.assertTrue(pump(lambda: self.boxes[-1:] == [self.text(c.ERR_VISION_KEY_KEY)]))
        self.assertFalse(self.frame.is_busy)
        self.assertEqual(self.shown, [])

    def test_context_menu_offers_it_on_pictures_only(self):
        label = self.text(c.CONTEXT_DESCRIBE_IMAGE_KEY)
        self.select(1)
        self.frame.on_message_context_menu(self.context_event(self.frame.messages_list))
        self.assertIn(label, self.menu_labels)
        self.select(0)
        self.frame.on_message_context_menu(self.context_event(self.frame.messages_list))
        self.assertNotIn(label, self.menu_labels)


class ReleasePapersTest(WindowTestCase):
    chats = [(ALI, 0, False)]

    def test_help_explains_the_licence_then_shows_the_components_and_its_text(self):
        shown = []
        self.frame.show_text = lambda title_key, text: shown.append((title_key, text))
        with mock.patch.object(ui.help_menu, "SOURCE_CODE_URL", ""):
            self.frame.on_license_menu(None)
        title_key, text = shown[0]
        self.assertEqual(title_key, c.LICENSE_TITLE_KEY)
        self.assertTrue(text.startswith(self.text(c.LICENSE_NOTICE_KEY)))
        self.assertLess(text.index("Telethon"), text.index("GNU GENERAL PUBLIC LICENSE"))
        self.assertIn("Version 3, 29 June 2007", text)
        # No address for the code is shown until there is one.
        self.assertNotIn(self.text(c.LICENSE_SOURCE_FORMAT_KEY).format(url=""), text)
        with mock.patch.object(ui.help_menu, "SOURCE_CODE_URL", "https://example.org/code"):
            self.frame.on_license_menu(None)
        self.assertIn(self.text(c.LICENSE_SOURCE_FORMAT_KEY).format(url="https://example.org/code"), shown[1][1])

    def test_installer_shows_the_licence_and_the_legal_files_exist(self):
        with open(os.path.join(c.BASE_DIR, "installer.iss"), encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertEqual(script.count('LicenseFile: "%s"' % c.LICENSE_FILE_NAME), len(c.LANGUAGES))
        for name in c.LEGAL_FILE_NAMES:
            self.assertTrue(os.path.getsize(os.path.join(c.BASE_DIR, name)) > 1000, name)

    def test_telegram_is_told_the_programs_own_version(self):
        made = FakeTelegramClient.created_with[-1]
        self.assertEqual(made["app_version"], c.APP_VERSION)
        self.assertTrue(made["system_version"].startswith("Windows"))


class PrivatePartTest(unittest.TestCase):
    """How a build packs the API id and hash is not published: those files stay out of the repository."""

    def test_the_private_files_are_kept_out_of_the_repository(self):
        with open(os.path.join(c.BASE_DIR, ".gitignore"), encoding="utf-8") as ignore_file:
            ignored = ignore_file.read().splitlines()
        for path in ("core/_seal.py", "core/_sealing.py", "tests/test_private_sealing.py", "protect.py", "config.json"):
            self.assertIn(path, ignored)

    def test_a_build_without_the_private_part_packs_nothing(self):
        import build
        import core.config as config
        with mock.patch.object(config, "_private_part", lambda: None), \
                mock.patch.object(build, "pack_credentials", config.pack_credentials), \
                mock.patch.object(build, "read_credentials", lambda path: (777, "0123456789abcdef0123456789abcdef")):
            self.assertIsNone(build.write_bundled_config())
