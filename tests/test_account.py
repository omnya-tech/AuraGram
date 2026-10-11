"""The account itself: username, photo, two-step verification, notification defaults, synced drafts."""
from unittest import mock

import wx

import core.constants as c
from tests.harness import FakeChooser, FakeTelegramClient, Record, WindowTestCase, make_channel, make_user, pump
from ui.settings_dialog import SettingsDialog

ALI = make_user(1, "Ali")
TEAM = make_channel(4, "Team", group=True)


class AccountTest(WindowTestCase):
    chats = [(ALI, 0, False), (TEAM, 0, False)]

    def open_settings(self):
        dialog = SettingsDialog(self.frame, self.i18n, self.frame.settings, self.manager)
        self.addCleanup(dialog.Destroy)
        self.assertTrue(pump(lambda: dialog.profile is not None and dialog.notify_settings is not None))
        return dialog

    def requests(self, name):
        return [call[1] for call in self.calls(name)]

    def test_username_is_saved_without_the_at_sign(self):
        dialog = self.open_settings()
        self.assertIsNone(dialog.changed_profile())
        dialog.profile_inputs["username"].SetValue("@new_name")
        self.manager.save_profile(dialog.changed_profile(), lambda result, error_key: None)
        self.assertTrue(pump(lambda: self.requests("UpdateUsernameRequest")))
        self.assertEqual(self.requests("UpdateUsernameRequest")[0].username, "new_name")

    def test_photo_is_uploaded_and_can_be_deleted(self):
        dialog = self.open_settings()
        dialog.set_photo("me.jpg")
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_PHOTO_SET_KEY)]))
        self.assertEqual(self.requests("UploadProfilePhotoRequest")[0].file, "uploaded:me.jpg")

        dialog.on_delete_photo(None)
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_NO_PHOTO_KEY)]))
        FakeTelegramClient.profile_photos = [Record(id=77, access_hash=1, file_reference=b"")]
        dialog.on_delete_photo(None)
        self.assertTrue(pump(lambda: self.spoken[-1:] == [self.text(c.MSG_PHOTO_DELETED_KEY)]))
        self.assertEqual(self.requests("DeletePhotosRequest")[0].id[0].id, 77)

    def test_deleting_the_photo_asks_first(self):
        dialog = self.open_settings()
        self.box_answer = wx.NO
        dialog.on_delete_photo(None)
        pump(timeout=0.2)
        self.assertEqual(self.requests("DeletePhotosRequest"), [])

    def two_step(self, dialog, values, selection=0):
        FakeChooser.values = list(values)
        FakeChooser.selection = selection
        with mock.patch.object(wx, "PasswordEntryDialog", FakeChooser):
            dialog.on_two_step(None)
            pump(timeout=0.4)

    def test_two_step_is_turned_on_changed_and_off(self):
        dialog = self.open_settings()
        self.two_step(dialog, ["secret", "secret", "my hint", ""])
        self.assertEqual(self.calls("2fa"), [("2fa", True, "my hint")])
        self.assertEqual(self.boxes[-1], self.text(c.MSG_TWO_STEP_SAVED_KEY))

        self.two_step(dialog, ["secret", "better", "better", "", ""])
        self.assertEqual(FakeTelegramClient.two_step_password, "better")

        self.two_step(dialog, ["better"], selection=1)
        self.assertIsNone(FakeTelegramClient.two_step_password)
        self.assertEqual(self.boxes[-1], self.text(c.MSG_TWO_STEP_DISABLED_KEY))

    def test_mistyped_new_password_changes_nothing(self):
        dialog = self.open_settings()
        self.two_step(dialog, ["secret", "secert"])
        self.assertEqual(self.boxes[-1], self.text(c.ERR_TWO_STEP_MISMATCH_KEY))
        self.assertEqual(self.calls("2fa"), [])

    def test_wrong_current_password_is_reported(self):
        FakeTelegramClient.two_step_password = "real"
        dialog = self.open_settings()
        self.two_step(dialog, ["guess", "new", "new", "", ""])
        self.assertEqual(self.boxes[-1], self.text(c.ERR_PASSWORD_INVALID_KEY))
        self.assertEqual(FakeTelegramClient.two_step_password, "real")

    def test_only_changed_notification_defaults_are_saved(self):
        dialog = self.open_settings()
        self.assertEqual(dialog.changed_notify(), {})
        self.assertTrue(dialog.notify_boxes[c.NOTIFY_GROUPS].GetValue())
        dialog.notify_boxes[c.NOTIFY_GROUPS].SetValue(False)
        self.assertEqual(dialog.changed_notify(), {c.NOTIFY_GROUPS: False})
        self.manager.save_notify(dialog.changed_notify(), lambda result, error_key: None)
        self.assertTrue(pump(lambda: self.requests("UpdateNotifySettingsRequest")))
        self.assertEqual(type(self.requests("UpdateNotifySettingsRequest")[0].peer).__name__, "InputNotifyChats")

    def test_chat_without_its_own_setting_follows_the_default_for_its_kind(self):
        FakeTelegramClient.muted_kinds = {"InputNotifyChats"}
        self.frame.load_dialogs()
        self.assertTrue(pump(lambda: self.frame.find_known_dialog(self.frame.dialogs[1]["id"])["muted"]))
        self.assertFalse(self.frame.find_known_dialog(1)["muted"])

    def test_draft_from_another_device_is_waiting_in_the_chat(self):
        FakeTelegramClient.drafts = {1: "typed on the phone"}
        self.frame.load_dialogs()
        self.assertTrue(pump(lambda: self.frame.drafts.get(1) == "typed on the phone"))
        self.open_chat(0)
        self.assertEqual(self.frame.message_input.GetValue(), "typed on the phone")

    def test_draft_is_saved_to_the_account_when_leaving_the_chat_and_cleared_when_emptied(self):
        self.open_chat(0)
        self.frame.message_input.SetValue("half a thought")
        self.open_chat(1)
        self.assertTrue(pump(lambda: len(self.requests("SaveDraftRequest")) == 1))
        self.assertEqual(self.requests("SaveDraftRequest")[0].message, "half a thought")

        self.open_chat(0)
        self.frame.message_input.SetValue("")
        self.open_chat(1)
        self.assertTrue(pump(lambda: len(self.requests("SaveDraftRequest")) == 2))
        self.assertEqual(self.requests("SaveDraftRequest")[1].message, "")
        # Coming and going without typing sends nothing.
        self.open_chat(0)
        self.open_chat(1)
        pump(timeout=0.2)
        self.assertEqual(len(self.requests("SaveDraftRequest")), 2)
