import wx
from ui.layout import prepare_window
from core.constants import (
    MSG_POLL_SETTINGS_KEY, POLL_SETTINGS_TITLE_KEY, POLL_SETTING_ANONYMOUS, POLL_SETTING_ANONYMOUS_CHANNEL_KEY,
    POLL_SETTING_MULTIPLE, POLL_SETTING_QUIZ, POLL_SETTING_SHUFFLE, POLL_SETTING_HIDE_RESULTS, POLL_SETTING_NO_REVOTE,
    MSG_POLL_CORRECT_ANSWER_KEY, MSG_POLL_EXPLANATION_PROMPT_KEY, POLL_CLOSE_LABEL_KEY, POLL_CLOSE_CHOICES,
    ERR_POLL_QUIZ_MULTIPLE_KEY, ERR_POLL_EXPLANATION_LONG_FORMAT_KEY, POLL_EXPLANATION_MAX, APP_TITLE_KEY,
)

# Each tick box of the window: the setting it stands for, and the locale key of its label.
FLAGS = (
    ("anonymous", POLL_SETTING_ANONYMOUS),
    ("multiple", POLL_SETTING_MULTIPLE),
    ("quiz", POLL_SETTING_QUIZ),
    ("shuffle", POLL_SETTING_SHUFFLE),
    ("hide_results", POLL_SETTING_HIDE_RESULTS),
    ("no_revote", POLL_SETTING_NO_REVOTE),
)


def telegram_length(text):
    """A text's length as Telegram counts it: in UTF-16 units, so an emoji counts two."""
    return len(text.encode("utf-16-le")) // 2


class PollSettingsDialog(wx.Dialog):
    """Everything a poll can be set to, in one window, each a tick box or a list, read by Tab:
    anonymous or not, several answers, a quiz with its right answer and explanation, the options in
    any order, the results hidden until it closes, no changing a vote, and closing by itself.

    In a channel voting is always anonymous, by Telegram's rule: the box is there, ticked, and
    cannot be changed, so it is clear why. `settings()` gives what was chosen."""

    def __init__(self, parent, i18n, options, defaults, in_channel=False):
        super().__init__(parent, title=i18n.get_string(POLL_SETTINGS_TITLE_KEY), style=wx.DEFAULT_DIALOG_STYLE)
        prepare_window(self, i18n)
        self.i18n = i18n
        self.options = list(options)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(MSG_POLL_SETTINGS_KEY)), flag=wx.ALL, border=10)
        self.boxes = {}
        for name, label_key in FLAGS:
            label = i18n.get_string(POLL_SETTING_ANONYMOUS_CHANNEL_KEY if name == "anonymous" and in_channel else label_key)
            box = wx.CheckBox(self, label=label)
            box.SetValue(bool(defaults.get(name)))
            self.boxes[name] = box
            sizer.Add(box, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)
        if in_channel:
            self.boxes["anonymous"].SetValue(True)
            self.boxes["anonymous"].Disable()
        # A quiz's right answer and explanation, offered only while "quiz" is ticked.
        self.answer_label = wx.StaticText(self, label=i18n.get_string(MSG_POLL_CORRECT_ANSWER_KEY))
        self.answer_choice = wx.Choice(self, choices=self.options)
        self.answer_choice.SetSelection(0)
        self.explanation_label = wx.StaticText(self, label=i18n.get_string(MSG_POLL_EXPLANATION_PROMPT_KEY))
        self.explanation_input = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(-1, 60))
        for control in (self.answer_label, self.answer_choice, self.explanation_label, self.explanation_input):
            sizer.Add(control, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)
        sizer.Add(wx.StaticText(self, label=i18n.get_string(POLL_CLOSE_LABEL_KEY)), flag=wx.LEFT | wx.RIGHT, border=10)
        self.close_choice = wx.Choice(self, choices=[i18n.get_string(key) for seconds, key in POLL_CLOSE_CHOICES])
        seconds = [seconds for seconds, key in POLL_CLOSE_CHOICES]
        self.close_choice.SetSelection(seconds.index(defaults.get("close_after", 0)) if defaults.get("close_after", 0) in seconds else 0)
        sizer.Add(self.close_choice, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)
        sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), flag=wx.EXPAND | wx.ALL, border=10)
        self.SetSizerAndFit(sizer)
        self.boxes["quiz"].Bind(wx.EVT_CHECKBOX, lambda event: self.show_quiz_parts())
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)
        self.show_quiz_parts()
        self.CenterOnParent()
        self.boxes["anonymous" if not in_channel else "multiple"].SetFocus()

    def show_quiz_parts(self):
        quiz = self.boxes["quiz"].GetValue()
        for control in (self.answer_label, self.answer_choice, self.explanation_label, self.explanation_input):
            control.Show(quiz)
        self.Fit()

    def problem(self):
        """What Telegram would refuse in these settings, said; None if it would take them."""
        if self.boxes["quiz"].GetValue() and self.boxes["multiple"].GetValue():
            return self.i18n.get_string(ERR_POLL_QUIZ_MULTIPLE_KEY)
        explanation = self.explanation_input.GetValue().strip()
        if self.boxes["quiz"].GetValue() and telegram_length(explanation) > POLL_EXPLANATION_MAX:
            return self.i18n.get_string(ERR_POLL_EXPLANATION_LONG_FORMAT_KEY).format(
                length=telegram_length(explanation), limit=POLL_EXPLANATION_MAX
            )
        return None

    def on_ok(self, event):
        problem = self.problem()
        if problem is not None:
            # Kept open, with everything as it was set, to put right.
            wx.MessageBox(problem, self.i18n.get_string(APP_TITLE_KEY), wx.OK | wx.ICON_ERROR, self)
            return
        event.Skip()

    def settings(self):
        """{"anonymous", "multiple", "shuffle", "hide_results", "no_revote", "close_after",
        "quiz_answer" (index of the right option, or None), "explanation"}."""
        quiz = self.boxes["quiz"].GetValue()
        chosen = {name: box.GetValue() for name, box in self.boxes.items() if name != "quiz"}
        chosen["close_after"] = POLL_CLOSE_CHOICES[self.close_choice.GetSelection()][0]
        chosen["quiz_answer"] = self.answer_choice.GetSelection() if quiz else None
        chosen["explanation"] = self.explanation_input.GetValue().strip() if quiz else ""
        return chosen

    def remembered(self):
        """What is kept for the next poll: the ticks and the closing, not a quiz's own answer."""
        # A channel's rule is not a choice: the anonymous box there leaves the default as it was.
        kept = {name: box.GetValue() for name, box in self.boxes.items() if box.IsEnabled()}
        kept["close_after"] = POLL_CLOSE_CHOICES[self.close_choice.GetSelection()][0]
        return kept
