"""Unit tests for the extracted ChatView widget and its signals."""

import unittest

from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton
from PySide6.QtTest import QSignalSpy

from app.ui.chat_view import ChatView


def get_application():
    return QApplication.instance() or QApplication()


class TestChatView(unittest.TestCase):
    def setUp(self):
        self.app = get_application()
        self.view = ChatView()

    def test_has_expected_controls(self):
        self.assertIsInstance(self.view.input_edit, QLineEdit)
        self.assertIsInstance(self.view.send_button, QPushButton)
        self.assertIsInstance(self.view.history_button, QPushButton)

    def test_send_button_emits_message_signals(self):
        self.view.input_edit.setText("hello")
        spy = QSignalSpy(self.view.message_submitted)
        spy_sent = QSignalSpy(self.view.message_sent)
        spy_req = QSignalSpy(self.view.send_requested)
        spy_sub = QSignalSpy(self.view.submitted)
        self.view.send_button.click()
        self.assertEqual(spy.size(), 1)
        self.assertEqual(spy_sent.size(), 1)
        self.assertEqual(spy_req.size(), 1)
        self.assertEqual(spy_sub.size(), 1)
        self.assertEqual(spy.at(0)[0], "hello")
        self.assertEqual(self.view.input_edit.text(), "")

    def test_enter_key_emits_message(self):
        self.view.input_edit.setText("hi there")
        spy = QSignalSpy(self.view.message_submitted)
        self.view.input_edit.returnPressed.emit()
        self.assertEqual(spy.size(), 1)
        self.assertEqual(spy.at(0)[0], "hi there")

    def test_empty_input_does_not_emit(self):
        spy = QSignalSpy(self.view.message_submitted)
        self.view.send_button.click()
        self.assertEqual(spy.size(), 0)

    def test_history_button_emits_toggle_signals(self):
        spy = QSignalSpy(self.view.history_toggle_requested)
        spy_clicked = QSignalSpy(self.view.history_clicked)
        spy_req = QSignalSpy(self.view.history_requested)
        self.view.history_button.click()
        self.assertEqual(spy.size(), 1)
        self.assertEqual(spy_clicked.size(), 1)
        self.assertEqual(spy_req.size(), 1)


if __name__ == "__main__":
    unittest.main()
