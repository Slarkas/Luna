"""Unit tests for the extracted Sidebar widget and its navigation signals."""

import unittest

from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtTest import QSignalSpy

from app.ui.sidebar import Sidebar


def get_application():
    return QApplication.instance() or QApplication()


class TestSidebar(unittest.TestCase):
    def setUp(self):
        self.app = get_application()
        self.sidebar = Sidebar()

    def _button_texts(self):
        return [
            btn.text()
            for btn in self.sidebar.findChildren(QPushButton)
        ]

    def test_has_expected_navigation_options(self):
        texts = self._button_texts()
        self.assertIn("Chat History", texts)
        self.assertIn("Settings", texts)
        self.assertIn("Back", texts)

    def test_chat_history_button_emits_signals(self):
        spy_clicked = QSignalSpy(self.sidebar.chat_history_clicked)
        spy_requested = QSignalSpy(self.sidebar.chat_history_requested)
        spy_nav = QSignalSpy(self.sidebar.navigation_requested)
        self.sidebar.nav_history_button.click()
        self.assertEqual(spy_clicked.size(), 1)
        self.assertEqual(spy_requested.size(), 1)
        self.assertEqual(spy_nav.size(), 1)
        self.assertEqual(spy_nav.at(0)[0], "history")

    def test_settings_button_emits_signals(self):
        spy_clicked = QSignalSpy(self.sidebar.settings_clicked)
        spy_requested = QSignalSpy(self.sidebar.settings_requested)
        spy_nav = QSignalSpy(self.sidebar.navigation_requested)
        self.sidebar.nav_settings_button.click()
        self.assertEqual(spy_clicked.size(), 1)
        self.assertEqual(spy_requested.size(), 1)
        self.assertEqual(spy_nav.size(), 1)
        self.assertEqual(spy_nav.at(0)[0], "settings")

    def test_back_button_emits_new_chat_and_back_signals(self):
        spy_back = QSignalSpy(self.sidebar.back_clicked)
        spy_back_req = QSignalSpy(self.sidebar.back_requested)
        spy_new = QSignalSpy(self.sidebar.new_chat_clicked)
        spy_new_req = QSignalSpy(self.sidebar.new_chat_requested)
        spy_nav = QSignalSpy(self.sidebar.navigation_requested)
        self.sidebar.nav_back_button.click()
        self.assertEqual(spy_back.size(), 1)
        self.assertEqual(spy_back_req.size(), 1)
        self.assertEqual(spy_new.size(), 1)
        self.assertEqual(spy_new_req.size(), 1)
        self.assertEqual(spy_nav.size(), 1)
        self.assertEqual(spy_nav.at(0)[0], "chat")

    def test_set_active_highlights_correct_button(self):
        self.sidebar.set_active("history")
        self.assertIn("#4f46e5", self.sidebar.nav_history_button.styleSheet())
        self.assertNotIn("#4f46e5", self.sidebar.nav_back_button.styleSheet())

        self.sidebar.set_active("chat")
        self.assertIn("#4f46e5", self.sidebar.nav_back_button.styleSheet())
        self.assertNotIn("#4f46e5", self.sidebar.nav_history_button.styleSheet())

    def test_button_aliases(self):
        self.assertIs(self.sidebar.chat_history_button, self.sidebar.nav_history_button)
        self.assertIs(self.sidebar.settings_button, self.sidebar.nav_settings_button)
        self.assertIs(self.sidebar.back_button, self.sidebar.nav_back_button)
        self.assertIs(self.sidebar.new_chat_button, self.sidebar.nav_back_button)
        self.assertIs(self.sidebar.history_button, self.sidebar.nav_history_button)


if __name__ == "__main__":
    unittest.main()
