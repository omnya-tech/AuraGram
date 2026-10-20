"""Signing in: the login window with the real manager and a fake Telegram."""
import unittest
from unittest import mock

import wx
from telethon.errors import PhoneCodeInvalidError, SendCodeUnavailableError
from telethon.tl import types

import core.constants as c
import core.telegram_client as telegram_client
import ui.login_frame
from core.i18n import I18NManager
from tests.harness import Record, get_app, pump
from ui.login_frame import LoginFrame


def country(iso, name, code, prefixes=()):
    return types.help.Country(
        iso2=iso, default_name=name, name=name,
        country_codes=[types.help.CountryCode(country_code=code, prefixes=list(prefixes) or None)]
    )


# Two that share +1, told apart by what follows it, as Telegram lists them.
COUNTRIES = types.help.CountriesList(countries=[
    country("EG", "مصر", "20"), country("SA", "السعودية", "966"),
    country("US", "الولايات المتحدة", "1"), country("CA", "كندا", "1", prefixes=["204", "416"]),
], hash=0)


class FakeLoginClient:
    """Telegram for an account that is not signed in yet."""

    calls = []
    # What each "send me the code" request answers, in order: (how it was sent, what is next).
    deliveries = []

    def __init__(self, *args, **kwargs):
        self.connected = False

    def add_event_handler(self, handler, event):
        pass

    def is_connected(self):
        return self.connected

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def is_user_authorized(self):
        return False

    def _sent_code(self):
        if not self.deliveries:
            raise SendCodeUnavailableError(None)
        sent_type, next_type = self.deliveries.pop(0)
        return Record(phone_code_hash="hash%d" % len(self.calls), type=sent_type, next_type=next_type)

    async def send_code_request(self, phone):
        self.calls.append(("send_code", phone))
        return self._sent_code()

    async def __call__(self, request):
        if type(request).__name__ == "GetCountriesListRequest":
            return COUNTRIES
        self.calls.append((type(request).__name__, request.phone_number, request.phone_code_hash))
        return self._sent_code()

    async def sign_in(self, phone=None, code=None, password=None, phone_code_hash=None):
        self.calls.append(("sign_in", phone, code, phone_code_hash))
        if code != "12345":
            raise PhoneCodeInvalidError(None)


class LoginTest(unittest.TestCase):
    def setUp(self):
        get_app()
        FakeLoginClient.calls = []
        FakeLoginClient.deliveries = [
            (types.auth.SentCodeTypeApp(5), types.auth.CodeTypeSms()),
            (types.auth.SentCodeTypeSms(5), types.auth.CodeTypeCall()),
            (types.auth.SentCodeTypeCall(5), None),
        ]
        self.spoken = []
        self.errors = []
        self.steps = []
        for patch in (
            mock.patch.object(telegram_client, "TelegramClient", FakeLoginClient),
            mock.patch.object(ui.login_frame, "speak", self.spoken.append),
            mock.patch.object(wx, "MessageBox", lambda message, *args, **kwargs: self.errors.append(message)),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.i18n = I18NManager("ar")
        self.manager = telegram_client.TelegramManager(self.on_step)
        self.frame = LoginFrame(self.i18n, self.manager)
        self.addCleanup(self.frame.Destroy)
        self.manager.start()
        self.addCleanup(self.manager.stop)
        self.assertTrue(pump(lambda: self.steps == [c.STEP_PHONE]), "login did not reach the phone step")

    def on_step(self, step, error_key=None):
        """What main.py does with the manager's answers, minus opening the main window."""
        def apply():
            self.steps.append(step)
            if step != c.STEP_DONE:
                self.frame.set_step(step)
                if error_key:
                    self.frame.show_error(error_key)
        wx.CallAfter(apply)

    def text(self, key):
        return self.i18n.get_string(key)

    def enter_phone(self):
        self.frame.phone_input.SetValue("+201000000000")
        self.frame.on_send_phone(None)
        self.assertTrue(pump(lambda: self.steps[-1] == c.STEP_CODE))

    def resend(self):
        before = len(self.steps)
        self.frame.on_resend_code(None)
        self.assertTrue(pump(lambda: len(self.steps) > before))

    def choice(self):
        return self.frame.country_choice.GetStringSelection()

    def test_countries_are_listed_and_typing_a_code_chooses_one(self):
        self.assertTrue(pump(lambda: self.frame.country_choice.GetCount() == 5))
        self.assertEqual(self.frame.country_choice.GetString(0), self.text(c.COUNTRY_NONE_KEY))
        field = self.frame.phone_input
        field.SetValue("+96650")
        self.assertEqual(self.choice(), self.text(c.COUNTRY_ROW_FORMAT_KEY).format(name="السعودية", code="966"))
        # +1 then the area code: Canada's, then nobody's but the United States'.
        field.SetValue("+1416555")
        self.assertIn("كندا", self.choice())
        field.SetValue("+1212555")
        self.assertIn("الولايات المتحدة", self.choice())
        field.SetValue("00201000")
        self.assertIn("مصر", self.choice())
        field.SetValue("+999")
        self.assertEqual(self.frame.country_choice.GetSelection(), 0)

    def test_choosing_a_country_puts_its_code_in_front_of_the_number(self):
        self.assertTrue(pump(lambda: self.frame.country_choice.GetCount() == 5))
        field = self.frame.phone_input
        names = [entry["name"] for entry in self.frame.countries]
        field.ChangeValue("01001234567")
        self.frame.country_choice.SetSelection(names.index("مصر") + 1)
        self.frame.on_country_chosen(None)
        # Dialled at home with a 0 in front; with the country's code, without it.
        self.assertEqual(field.GetValue(), "+201001234567")
        self.frame.country_choice.SetSelection(names.index("السعودية") + 1)
        self.frame.on_country_chosen(None)
        self.assertEqual(field.GetValue(), "+9661001234567")

    def test_the_country_windows_is_set_to_starts_the_number(self):
        with mock.patch.object(ui.login_frame, "home_country", lambda: "SA"):
            self.frame.phone_input.ChangeValue("")
            self.frame.fill_countries()
        self.assertEqual(self.frame.phone_input.GetValue(), "+966")
        self.assertIn("السعودية", self.choice())

    def test_resend_button_appears_only_while_entering_the_code(self):
        self.assertFalse(self.frame.resend_btn.IsShown())
        self.enter_phone()
        self.assertTrue(self.frame.resend_btn.IsShown())

    def test_code_step_says_where_the_code_went_and_offers_the_next_way(self):
        self.enter_phone()
        self.assertEqual(self.frame.instruction_label.GetLabel().replace("\n", " "), self.text("CODE_DELIVERY_APP"))
        self.assertEqual(self.spoken[-1], self.text("CODE_DELIVERY_APP"))
        self.assertEqual(self.frame.resend_btn.GetLabel(), self.text("BTN_RESEND_SMS"))

    def test_asking_again_moves_through_sms_to_a_voice_call(self):
        self.enter_phone()
        self.resend()
        self.assertEqual(self.spoken[-1], self.text("CODE_DELIVERY_SMS"))
        self.assertEqual(self.frame.resend_btn.GetLabel(), self.text("BTN_RESEND_CALL"))
        self.resend()
        self.assertEqual(self.spoken[-1], self.text("CODE_DELIVERY_CALL"))
        # Telegram offered nothing after the call, so the button falls back to its general wording.
        self.assertEqual(self.frame.resend_btn.GetLabel(), self.text(c.BTN_RESEND_OTHER_KEY))
        resends = [call for call in FakeLoginClient.calls if call[0] == "ResendCodeRequest"]
        self.assertEqual(len(resends), 2)
        self.assertEqual(resends[0][1], "+201000000000")

    def test_each_resend_uses_the_hash_of_the_latest_code(self):
        self.enter_phone()
        first_hash = self.manager.phone_hash
        self.resend()
        resend = [call for call in FakeLoginClient.calls if call[0] == "ResendCodeRequest"][0]
        self.assertEqual(resend[2], first_hash)
        self.assertNotEqual(self.manager.phone_hash, first_hash)
        self.frame.code_input.SetValue("12345")
        self.frame.on_send_code(None)
        self.assertTrue(pump(lambda: self.steps[-1] == c.STEP_DONE))
        sign_in = [call for call in FakeLoginClient.calls if call[0] == "sign_in"][0]
        self.assertEqual(sign_in[3], self.manager.phone_hash)

    def test_when_no_other_way_is_left_it_says_so_and_stays_on_the_code(self):
        self.enter_phone()
        self.resend()
        self.resend()
        self.resend()
        self.assertEqual(self.errors, [self.text(c.ERR_NO_OTHER_DELIVERY_KEY)])
        self.assertEqual(self.steps[-1], c.STEP_CODE)
        self.assertFalse(self.frame.is_processing)
        self.assertTrue(self.frame.code_input.IsShown())

    def test_a_rejected_app_key_is_named_as_such_and_logged(self):
        from telethon.errors import ApiIdInvalidError

        async def rejected(self, phone):
            raise ApiIdInvalidError(None)

        with mock.patch.object(FakeLoginClient, "send_code_request", rejected), \
                self.assertLogs("core.telegram_client", level="ERROR"):
            self.frame.phone_input.SetValue("+201000000000")
            self.frame.on_send_phone(None)
            self.assertTrue(pump(lambda: len(self.errors) == 1))
        self.assertEqual(self.errors, [self.text(c.ERR_API_INVALID_KEY)])
        self.assertEqual(self.steps[-1], c.STEP_PHONE)

    def test_an_unexpected_failure_leaves_its_details_in_the_log(self):
        async def broken(self, phone):
            raise RuntimeError("something nobody planned for")

        with mock.patch.object(FakeLoginClient, "send_code_request", broken), \
                self.assertLogs("core.telegram_client", level="ERROR") as logged:
            self.frame.phone_input.SetValue("+201000000000")
            self.frame.on_send_phone(None)
            self.assertTrue(pump(lambda: len(self.errors) == 1))
        self.assertEqual(self.errors, [self.text(c.ERR_GENERAL_KEY)])
        self.assertIn("something nobody planned for", "\n".join(logged.output))

    def test_wrong_code_keeps_the_resend_button_available(self):
        self.enter_phone()
        self.frame.code_input.SetValue("00000")
        self.frame.on_send_code(None)
        self.assertTrue(pump(lambda: len(self.errors) == 1))
        self.assertEqual(self.errors, [self.text(c.ERR_CODE_INVALID_KEY)])
        self.assertTrue(self.frame.resend_btn.IsShown())
        self.assertEqual(self.frame.resend_btn.GetLabel(), self.text("BTN_RESEND_SMS"))

    # The code goes off once its last digit is typed; no Enter is needed.
    def sign_ins(self):
        return [call for call in FakeLoginClient.calls if call[0] == "sign_in"]

    def test_the_last_digit_sends_the_code(self):
        self.enter_phone()
        self.frame.code_input.SetValue("1234")
        pump(timeout=0.1)
        self.assertEqual(self.sign_ins(), [])
        self.frame.code_input.SetValue("12345")
        self.assertTrue(pump(lambda: self.steps[-1] == c.STEP_DONE))
        self.assertEqual(self.sign_ins()[0][2], "12345")

    def test_a_pasted_code_with_a_dash_goes_as_its_digits(self):
        self.enter_phone()
        self.frame.code_input.SetValue("123-45")
        self.assertTrue(pump(lambda: self.steps[-1] == c.STEP_DONE))
        self.assertEqual(self.sign_ins()[0][2], "12345")

    def test_a_wrong_code_can_be_typed_again(self):
        self.enter_phone()
        self.frame.code_input.SetValue("99999")
        self.assertTrue(pump(lambda: self.errors))
        self.frame.code_input.SetValue("12345")
        self.assertTrue(pump(lambda: self.steps[-1] == c.STEP_DONE))


if __name__ == "__main__":
    unittest.main()
