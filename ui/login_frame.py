import wx
from ui.layout import prepare_window
from core.speech import speak
from core.constants import (
    BTN_RESEND_OTHER_KEY, APP_TITLE_KEY, LOGIN_TITLE_KEY, MSG_LOADING_KEY,
    MSG_ENTER_PHONE_KEY, PHONE_LABEL_KEY, BTN_SEND_PHONE_KEY,
    MSG_CODE_SENT_KEY, CODE_LABEL_KEY, BTN_SEND_CODE_KEY,
    MSG_PASSWORD_NEEDED_KEY, PASSWORD_LABEL_KEY, BTN_SEND_PASSWORD_KEY,
    STEP_PHONE, STEP_CODE, STEP_PASSWORD
)

class LoginFrame(wx.Frame):
    def __init__(self, i18n, telegram_manager):
        super().__init__(None, title=i18n.get_string(LOGIN_TITLE_KEY), size=(520, 420))
        prepare_window(self, i18n)
        self.i18n = i18n
        self.telegram_manager = telegram_manager
        self.is_processing = False
        self.step_controls = {}
        self.init_ui()

    def init_ui(self):
        self.panel = wx.Panel(self)
        self.vbox = wx.BoxSizer(wx.VERTICAL)

        self.instruction_label = wx.StaticText(self.panel)
        self.vbox.Add(self.instruction_label, flag=wx.ALL, border=15)

        self.phone_input = self.add_step(
            STEP_PHONE, MSG_ENTER_PHONE_KEY, PHONE_LABEL_KEY, BTN_SEND_PHONE_KEY, self.on_send_phone
        )
        self.code_input = self.add_step(
            STEP_CODE, MSG_CODE_SENT_KEY, CODE_LABEL_KEY, BTN_SEND_CODE_KEY, self.on_send_code
        )
        self.resend_btn = self.add_step_button(STEP_CODE, BTN_RESEND_OTHER_KEY, self.on_resend_code)
        self.password_input = self.add_step(
            STEP_PASSWORD, MSG_PASSWORD_NEEDED_KEY, PASSWORD_LABEL_KEY, BTN_SEND_PASSWORD_KEY,
            self.on_send_password, input_style=wx.TE_PASSWORD
        )

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
        self.panel.Disable()

    def set_step(self, step):
        """Show only the controls of the given login step and unlock the form."""
        self.is_processing = False
        self.panel.Enable()
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
        self.panel.Layout()
        text_input.SetFocus()
        text_input.SelectAll()
        if step == STEP_CODE:
            # Focus alone would read only the field's label, not how the code is coming.
            speak(self.i18n.get_string(instruction_key))

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
