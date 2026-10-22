"""The menu bar: the chat list's menus outside a chat, and inside one only what that chat's kind has."""
import wx

import core.constants as c
import core.shortcuts as shortcuts
import core.telegram_client as telegram_client
from tests.harness import WindowTestCase, make_channel, make_user, pump
from ui.main_frame import EVERY_CHAT

ALI = make_user(1, "Ali")
HELPER = make_user(2, "Helper", contact=False, bot=True)
NEWS = make_channel(3, "News")
MY_GROUP = make_channel(4, "MyGroup", group=True, creator=True)


class MenuBarTest(WindowTestCase):
    chats = [(ALI, 0, False), (HELPER, 0, False), (NEWS, 0, False), (MY_GROUP, 0, False)]

    def titles(self):
        return [title for _, title in self.frame.GetMenuBar().GetMenus()]

    def enter(self, entity):
        peer_id = telegram_client.get_peer_id(entity)
        self.open_chat([dialog["id"] for dialog in self.frame.dialogs].index(peer_id))
        # The menu bar follows once the key that opened the chat is done with the old one.
        self.assertTrue(pump(lambda: self.text(c.MENU_OPEN_CHAT_KEY) in self.titles()))

    def leave(self):
        self.frame.close_chat()
        self.assertTrue(pump(lambda: self.text(c.MENU_CHATS_KEY) in self.titles()))

    def test_the_chat_list_has_its_menus_and_no_chat_ones(self):
        self.assertEqual(self.titles(), [self.text(key) for key in (
            c.MENU_FILE_KEY, c.MENU_CHATS_KEY, c.MENU_CHAT_VIEWS_KEY, c.MENU_SEARCH_KEY, c.MENU_HELP_KEY)])
        for key in (c.MENU_GO_TO_DATE_KEY, c.MENU_SEARCH_MESSAGES_KEY, c.MESSAGE_VIEW_PHOTOS, c.MENU_TOPICS_KEY):
            self.assertNotIn(key, self.frame.menu_items)
        # Every chat command is there for the chat selected.
        for key in (c.MENU_CHAT_MANAGE_KEY, c.MENU_CHAT_BLOCK_KEY, c.MENU_NEW_GROUP_KEY, c.MENU_STORIES_KEY):
            self.assertIn(key, self.frame.menu_items)

    def test_a_private_chat_has_contact_and_block_but_no_group_entries(self):
        self.enter(ALI)
        self.assertEqual(self.titles(), [self.text(key) for key in (
            c.MENU_FILE_KEY, c.MENU_OPEN_CHAT_KEY, c.MENU_CHAT_VIEWS_KEY, c.MENU_GO_KEY, c.MENU_SEARCH_KEY,
            c.MENU_HELP_KEY)])
        for key in (c.MENU_CHAT_CONTACT_KEY, c.MENU_CHAT_BLOCK_KEY, c.MENU_GO_TO_DATE_KEY, c.MESSAGE_VIEW_PHOTOS):
            self.assertIn(key, self.frame.menu_items)
        for key in (c.MENU_CHAT_MANAGE_KEY, c.MENU_COPY_INVITE_KEY, c.MESSAGE_VIEW_MENTIONS, c.MENU_TOPICS_KEY,
                    c.MENU_NEW_GROUP_KEY, c.MENU_STORIES_KEY):
            self.assertNotIn(key, self.frame.menu_items)

    def test_a_group_has_its_own_entries_and_back_on_the_list_the_list_menus_return(self):
        self.enter(MY_GROUP)
        for key in (c.MENU_CHAT_MANAGE_KEY, c.MENU_COPY_INVITE_KEY, c.MESSAGE_VIEW_MENTIONS):
            self.assertIn(key, self.frame.menu_items)
        for key in (c.MENU_CHAT_CONTACT_KEY, c.MENU_CHAT_BLOCK_KEY, c.MENU_CHAT_JOIN_KEY):
            self.assertNotIn(key, self.frame.menu_items)
        self.leave()
        self.assertNotIn(c.MENU_GO_TO_DATE_KEY, self.frame.menu_items)
        self.assertIn(c.MENU_NEW_GROUP_KEY, self.frame.menu_items)

    def test_a_channel_not_run_here_has_no_management_nor_mentions(self):
        self.enter(NEWS)
        self.assertIn(c.MENU_COPY_INVITE_KEY, self.frame.menu_items)
        for key in (c.MENU_CHAT_MANAGE_KEY, c.MESSAGE_VIEW_MENTIONS, c.MENU_CHAT_BLOCK_KEY):
            self.assertNotIn(key, self.frame.menu_items)

    def test_the_chat_menu_acts_on_the_chat_open(self):
        self.enter(ALI)
        # Another chat selected in the hidden list does not count: the one open does.
        self.frame.dialogs_list.SetSelection(wx.NOT_FOUND)
        chosen = []
        self.frame.on_chat_menu(chosen.append)
        self.assertEqual([dialog["id"] for dialog in chosen], [telegram_client.get_peer_id(ALI)])

    def test_shortcuts_of_commands_not_on_this_menu_bar_still_work(self):
        table = shortcuts.defaults()
        # On the list, a chat's own commands; inside a private chat, the list's.
        self.assertIn(table[c.MENU_GO_TO_DATE_KEY], self.frame.menu_less_shortcuts)
        self.enter(ALI)
        self.assertIn(table[c.MENU_NEW_GROUP_KEY], self.frame.menu_less_shortcuts)
        self.assertIn(table[c.MENU_CHAT_MANAGE_KEY], self.frame.menu_less_shortcuts)
        self.assertNotIn(table[c.MENU_CHAT_BLOCK_KEY], self.frame.menu_less_shortcuts)

    def test_every_command_has_its_own_shortcut(self):
        table = shortcuts.defaults()
        used = [table[command] for command in self.frame.all_commands() if table.get(command)]
        self.assertEqual(sorted(used), sorted(set(used)))

    def test_both_screens_together_hold_the_list_and_the_chat_commands(self):
        layouts = (self.frame.menu_layout(None), self.frame.menu_layout(EVERY_CHAT))
        commands = {entry[0] for layout in layouts for _, entries in layout for entry in entries if entry}
        self.assertIn(c.MENU_GO_TO_DATE_KEY, commands)
        self.assertIn(c.MENU_NEW_GROUP_KEY, commands)

    def send_menu(self):
        self.frame.show_send_menu()
        return self.menu_labels

    def test_the_send_menu_offers_only_what_the_chat_has(self):
        mention, send_as, commands = (self.text(key) for key in (
            c.MENU_MENTION_KEY, c.MENU_SEND_AS_KEY, c.MENU_BOT_COMMANDS_KEY))
        self.enter(ALI)
        labels = self.send_menu()
        self.assertIn(self.text(c.MENU_SEND_FILE_KEY), labels)
        self.assertFalse({mention, send_as, commands} & set(labels))
        self.leave()
        self.enter(HELPER)
        labels = self.send_menu()
        self.assertIn(commands, labels)
        self.assertNotIn(mention, labels)
        self.leave()
        self.enter(MY_GROUP)
        self.assertTrue({mention, send_as, commands} <= set(self.send_menu()))
