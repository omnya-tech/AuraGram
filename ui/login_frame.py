import ctypes
import wx
from ui.layout import prepare_window
from core.speech import speak
from core.constants import (
    BTN_RESEND_OTHER_KEY, APP_TITLE_KEY, LOGIN_TITLE_KEY, MSG_LOADING_KEY,
    MSG_ENTER_PHONE_KEY, PHONE_LABEL_KEY, BTN_SEND_PHONE_KEY,
    MSG_CODE_SENT_KEY, CODE_LABEL_KEY, BTN_SEND_CODE_KEY,
    MSG_PASSWORD_NEEDED_KEY, PASSWORD_LABEL_KEY, BTN_SEND_PASSWORD_KEY,
    STEP_PHONE, STEP_CODE, STEP_PASSWORD, BTN_PROXY_KEY, COUNTRY_LABEL_KEY, COUNTRY_NONE_KEY, COUNTRY_ROW_FORMAT_KEY
)
from core.settings import SETTING_COUNTRIES

# Windows' own way of saying where the computer is set to be, as a two-letter country code.
GEO_NAME_LENGTH = 16


def home_country():
    """The two-letter code of the country Windows is set to, upper case; "" if it cannot say."""
    try:
        buffer = ctypes.create_unicode_buffer(GEO_NAME_LENGTH)
        if ctypes.windll.kernel32.GetUserDefaultGeoName(buffer, GEO_NAME_LENGTH):
            return buffer.value.upper()
    except (AttributeError, OSError):
        pass
    return ""


def country_for(number, countries):
    """The country a number typed with its code belongs to: the one whose code, or code and prefix,
    is the longest start of its digits. None if it starts with none of them, or has no code."""
    text = number.strip()
    if not text.startswith(("+", "00")):
        return None
    digits = "".join(char for char in text if char.isdigit())
    if text.startswith("00"):
        digits = digits[2:]
    best, best_length = None, 0
    for country in countries:
        for code in country["codes"]:
            if len(code) > best_length and digits.startswith(code):
                best, best_length = country, len(code)
    return best
from ui.proxy_dialog import ProxyDialog

class LoginFrame(wx.Frame):
    def __init__(self, i18n, telegram_manager, settings=None):
        super().__init__(None, title=i18n.get_string(LOGIN_TITLE_KEY), size=(520, 470))
        prepare_window(self, i18n)
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        # Where the proxy is kept; without it the window offers none.
        self.settings = settings
        self.is_processing = False
        self.step_controls = {}
        # The countries offered, as Telegram listed them; the last list is kept for the next sign-in.
        cached = settings.get(SETTING_COUNTRIES) if settings is not None else {}
        self.countries = cached.get("countries", []) if cached.get("language") == i18n.lang_code else []
        self.countries_asked = False
        self.country = None
        self.init_ui()

    def init_ui(self):
        self.panel = wx.Panel(self)
        self.vbox = wx.BoxSizer(wx.VERTICAL)

        self.instruction_label = wx.StaticText(self.panel)
        self.vbox.Add(self.instruction_label, flag=wx.ALL, border=15)

        # The country first: choosing it writes its code in the number, and typing a code chooses it.
        country_label = wx.StaticText(self.panel, label=self.i18n.get_string(COUNTRY_LABEL_KEY))
        self.vbox.Add(country_label, flag=wx.LEFT|wx.RIGHT, border=15)
        self.country_choice = wx.Choice(self.panel)
        self.country_choice.SetName(self.i18n.get_string(COUNTRY_LABEL_KEY))
        self.country_choice.Bind(wx.EVT_CHOICE, self.on_country_chosen)
        self.vbox.Add(self.country_choice, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=15)
        self.phone_input = self.add_step(
            STEP_PHONE, MSG_ENTER_PHONE_KEY, PHONE_LABEL_KEY, BTN_SEND_PHONE_KEY, self.on_send_phone
        )
        self.phone_input.Bind(wx.EVT_TEXT, self.on_phone_typed)
        instruction_key, text_input, controls = self.step_controls[STEP_PHONE]
        self.step_controls[STEP_PHONE] = (instruction_key, text_input, (country_label, self.country_choice) + controls)
        for control in (country_label, self.country_choice):
            control.Hide()
        self.fill_countries()
        self.code_input = self.add_step(
            STEP_CODE, MSG_CODE_SENT_KEY, CODE_LABEL_KEY, BTN_SEND_CODE_KEY, self.on_send_code
        )
        # Sent by itself once the last digit is in, as Telegram's own apps do.
        self.code_input.Bind(wx.EVT_TEXT, self.on_code_typed)
        self.resend_btn = self.add_step_button(STEP_CODE, BTN_RESEND_OTHER_KEY, self.on_resend_code)
        self.password_input = self.add_step(
            STEP_PASSWORD, MSG_PASSWORD_NEEDED_KEY, PASSWORD_LABEL_KEY, BTN_SEND_PASSWORD_KEY,
            self.on_send_password, input_style=wx.TE_PASSWORD
        )

        # Usable at every step and while waiting too: where Telegram is blocked,
        # the waiting never ends until a proxy is set.
        self.proxy_btn = wx.Button(self.panel, label=self.i18n.get_string(BTN_PROXY_KEY))
        self.proxy_btn.Bind(wx.EVT_BUTTON, self.on_proxy)
        self.proxy_btn.Show(self.settings is not None)
        self.vbox.Add(self.proxy_btn, flag=wx.ALL, border=15)

        self.panel.SetSizer(self.vbox)
        self.Center()
        self.set_busy()

    def add_step(self, step, instruction_key, label_key, button_key, handler, input_style=0):
        label = wx.StaticText(self.panel, label=self.i18n.get_string(label_key))
        self.vbox.Add(label, flag=wx.LEFT|wx.RIGHT, border=15)

        text_input = wx.TextCtrl(self.panel, style=input_style|wx.TE_PROCESS_ENTER)
        text_input.Bind(wx.EVT_TEXT_ENTER, handler)
        self.vbox.Add(text_input, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, border=15)

        button = wx.Button(self.panel, label=self.i18n.get_string(button_key))
        button.Bind(wx.EVT_BUTTON, handler)
        self.vbox.Add(button, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=15)

        controls = (label, text_input, button)
        for control in controls:
            control.Hide()
        self.step_controls[step] = (instruction_key, text_input, controls)
        return text_input

    def add_step_button(self, step, label_key, handler):
        """An extra button shown only during one step, below that step's own controls."""
        button = wx.Button(self.panel, label=self.i18n.get_string(label_key))
        button.Bind(wx.EVT_BUTTON, handler)
        button.Hide()
        self.vbox.Add(button, flag=wx.LEFT|wx.RIGHT|wx.BOTTOM, border=15)
        instruction_key, text_input, controls = self.step_controls[step]
        self.step_controls[step] = (instruction_key, text_input, controls + (button,))
        return button

    def set_busy(self):
        """Lock the form while waiting for Telegram to answer."""
        self.is_processing = True
        self.set_instruction(MSG_LOADING_KEY)
        self.lock_steps(True)

    def set_step(self, step):
        """Show only the controls of the given login step and unlock the form."""
        self.is_processing = False
        self.lock_steps(False)
        for controls_step, (_, _, controls) in self.step_controls.items():
            for control in controls:
                control.Show(controls_step == step)
        instruction_key, text_input, _ = self.step_controls[step]
        if step == STEP_CODE:
            # Say where the code actually went, and offer the next way Telegram allows.
            instruction_key = self.telegram_manager.code_delivery
            self.resend_btn.SetLabel(self.i18n.get_string(
                self.telegram_manager.next_code_delivery or BTN_RESEND_OTHER_KEY
            ))
        self.set_instruction(instruction_key)
        if step == STEP_PHONE:
            self.ask_countries()
        self.panel.Layout()
        text_input.SetFocus()
        text_input.SelectAll()
        if step == STEP_CODE:
            # Focus alone would read only the field's label, not how the code is coming.
            speak(self.i18n.get_string(instruction_key))

    def ask_countries(self):
        """Once a sign-in, the list Telegram has now; the one kept from last time stands in until it comes."""
        if self.countries_asked:
            return
        self.countries_asked = True
        self.telegram_manager.load_countries(
            self.i18n.lang_code, lambda countries, error_key: wx.CallAfter(self.on_countries, countries)
        )

    def on_countries(self, countries):
        # Without an answer, the number is typed with its code as before.
        if not self or not countries:
            return
        self.countries = countries
        if self.settings is not None:
            self.settings.set(SETTING_COUNTRIES, {"language": self.i18n.lang_code, "countries": countries})
            self.settings.save()
        self.fill_countries()

    def fill_countries(self):
        text = self.i18n.get_string
        self.country_choice.Set([text(COUNTRY_NONE_KEY)] + [
            text(COUNTRY_ROW_FORMAT_KEY).format(name=country["name"], code=country["code"]) for country in self.countries
        ])
        if not self.phone_input.GetValue().strip():
            # Nothing typed yet: start from the country Windows is set to.
            home = next((country for country in self.countries if country["iso"] == home_country()), None)
            if home is not None:
                self.phone_input.ChangeValue("+" + home["code"])
        self.show_country(country_for(self.phone_input.GetValue(), self.countries))

    def show_country(self, country):
        self.country = country
        self.country_choice.SetSelection(self.countries.index(country) + 1 if country is not None else 0)

    def on_country_chosen(self, event):
        index = self.country_choice.GetSelection()
        if index <= 0:
            return
        country = self.countries[index - 1]
        number = self.phone_input.GetValue().strip()
        digits = "".join(char for char in number if char.isdigit())
        if number.startswith("00"):
            digits = digits[2:]
        old = country_for(number, self.countries)
        if old is not None:
            # The code of the country chosen before gives way to the new one; the rest of the number stays.
            rest = digits[len(old["code"]):]
        elif number.startswith(("+", "00")):
            # A code no country has: it is replaced whole.
            rest = ""
        else:
            # Written the way it is dialled at home: its leading 0 is not part of it abroad.
            rest = digits[1:] if digits.startswith("0") else digits
        self.country = country
        self.phone_input.ChangeValue("+" + country["code"] + rest)
        self.phone_input.SetInsertionPointEnd()

    def on_phone_typed(self, event):
        event.Skip()
        country = country_for(self.phone_input.GetValue(), self.countries)
        if country is self.country:
            return
        self.show_country(country)
        if country is not None and self.phone_input.HasFocus():
            # The country the code points to, said once, as it changes.
            speak(country["name"])

    def lock_steps(self, locked):
        """Lock or unlock what the login steps are made of; the proxy button stays usable either way."""
        for _, _, controls in self.step_controls.values():
            for control in controls:
                control.Enable(not locked)

    def on_proxy(self, event):
        with ProxyDialog(self, self.i18n, self.settings, self.telegram_manager) as proxy_dialog:
            if proxy_dialog.ShowModal() == wx.ID_OK:
                # Connecting again, the new way; Telegram's answer brings the form back.
                self.set_busy()

    def show_error(self, error_key):
        wx.MessageBox(
            self.i18n.get_string(error_key), self.i18n.get_string(APP_TITLE_KEY),
            wx.OK | wx.ICON_ERROR, self
        )

    def set_instruction(self, key):
        self.instruction_label.SetLabel(self.i18n.get_string(key))
        self.instruction_label.Wrap(self.panel.GetClientSize().width - 30)

    def on_send_phone(self, event):
        self.submit(self.phone_input, self.telegram_manager.send_phone)

    def on_send_code(self, event):
        self.submit(self.code_input, self.telegram_manager.send_code)

    def on_code_typed(self, event):
        """Send the code as soon as it has as many digits as Telegram said it would."""
        length = self.telegram_manager.code_length
        digits = "".join(char for char in self.code_input.GetValue() if char.isdigit())
        if length and len(digits) == length and not self.is_processing:
            # Pasted with spaces or a dash in it, it is still the same code.
            self.set_busy()
            self.telegram_manager.send_code(digits)

    def on_resend_code(self, event):
        if self.is_processing:
            return
        self.set_busy()
        self.telegram_manager.resend_code()

    def on_send_password(self, event):
        self.submit(self.password_input, self.telegram_manager.send_password, strip=False)

    def submit(self, text_input, send, strip=True):
        if self.is_processing:
            return
        value = text_input.GetValue()
        if strip:
            value = value.strip()
        if value:
            self.set_busy()
            send(value)
