"""Regression tests for LunaGUI settings behavior."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.ui import luna as luna_module
from app.ui.luna import LunaGUI
from app.ui.settings_controller import SettingsController


def make_gui(user_name="User"):
    gui = SimpleNamespace()
    gui.user_name = user_name
    gui.status_bar = SimpleNamespace(showMessage=Mock())
    gui.chat_view = SimpleNamespace(set_api_connected=Mock())
    return gui


class TestLunaGUISettings(unittest.TestCase):
    def setUp(self):
        self.gui = make_gui("User")
        self.gui._is_api_connected = LunaGUI._is_api_connected.__get__(self.gui, type(self.gui))
        self.mock_agent = Mock()
        self.mock_db = Mock()
        self.mock_db.initialize = Mock()
        self.mock_db.set_user_name = Mock()
        self.mock_db.set_setting = Mock()
        self.mock_db.get_user_name = Mock(return_value="User")
        self.gui.settings_controller = SettingsController(
            agent_service_factory=lambda: self.mock_agent,
            database_factory=lambda: self.mock_db,
        )

    def tearDown(self):
        pass

    def test_api_connected_returns_service_result(self):
        self.mock_agent.is_api_connected.return_value = True
        self.assertTrue(LunaGUI._is_api_connected(self.gui))
        self.mock_agent.is_api_connected.return_value = False
        self.assertFalse(LunaGUI._is_api_connected(self.gui))

    def test_api_connected_swallows_exceptions(self):
        self.mock_agent.is_api_connected.side_effect = RuntimeError("boom")
        self.assertFalse(LunaGUI._is_api_connected(self.gui))

    def test_api_status_aliases_match_detection(self):
        self.mock_agent.is_api_connected.return_value = True
        for alias in (
            "_update_api_status",
            "_refresh_api_status",
            "update_api_status",
            "refresh_api_status",
            "is_api_connected",
        ):
            self.assertTrue(getattr(LunaGUI, alias)(self.gui))

    def test_set_api_connected_uses_detection_when_none(self):
        self.mock_agent.is_api_connected.return_value = True
        LunaGUI.set_api_connected(self.gui)
        self.gui.chat_view.set_api_connected.assert_called_with(True)

    def test_set_api_connected_uses_explicit_value(self):
        LunaGUI.set_api_connected(self.gui, False)
        self.gui.chat_view.set_api_connected.assert_called_with(False)

    def test_on_api_settings_applied(self):
        LunaGUI._on_api_settings_applied(self.gui, endpoint="http://x")
        self.mock_agent.apply_api_settings.assert_called_with(endpoint="http://x")
        self.gui.chat_view.set_api_connected.assert_called()
        self.assertEqual(self.gui.status_bar.showMessage.call_count, 2)

    def test_username_settings_from_positional(self):
        LunaGUI._on_username_settings_applied(self.gui, "  Alice  ")
        self.assertEqual(self.gui.user_name, "Alice")
        self.assertEqual(luna_module.USER_NAME, "Alice")
        self.mock_db.set_user_name.assert_called_with("Alice")
        self.gui.status_bar.showMessage.assert_called_with("User name updated.")

    def test_username_settings_from_kwargs(self):
        for key in ("username", "user_name", "name"):
            gui = make_gui("User")
            gui.status_bar = self.gui.status_bar
            gui.chat_view = self.gui.chat_view
            gui._is_api_connected = LunaGUI._is_api_connected.__get__(gui, type(gui))
            gui.settings_controller = SettingsController(
                agent_service_factory=lambda: self.mock_agent,
                database_factory=lambda: self.mock_db,
            )
            LunaGUI._on_username_settings_applied(gui, **{key: "Bob"})
            self.assertEqual(gui.user_name, "Bob")

    def test_username_settings_empty_falls_back(self):
        self.gui.user_name = "Kept"
        LunaGUI._on_username_settings_applied(self.gui, "   ")
        self.assertEqual(self.gui.user_name, "Kept")

    def test_username_settings_last_resort_value(self):
        LunaGUI._on_username_settings_applied(self.gui, foo="Carol")
        self.assertEqual(self.gui.user_name, "Carol")

    def test_username_settings_non_string_arg_falls_back(self):
        self.gui.user_name = "Kept"
        LunaGUI._on_username_settings_applied(self.gui, 123)
        self.assertEqual(self.gui.user_name, "Kept")

    def test_username_changed_updates_state(self):
        LunaGUI._on_username_changed(self.gui, "  Dave  ")
        self.assertEqual(self.gui.user_name, "Dave")
        self.assertEqual(luna_module.USER_NAME, "Dave")
        self.mock_db.set_user_name.assert_called_with("Dave")

    def test_username_changed_from_kwargs(self):
        LunaGUI._on_username_changed(self.gui, name="Eve")
        self.assertEqual(self.gui.user_name, "Eve")

    def test_username_changed_last_resort(self):
        LunaGUI._on_username_changed(self.gui, foo="Frank")
        self.assertEqual(self.gui.user_name, "Frank")

    def test_username_changed_empty_does_not_update(self):
        self.gui.user_name = "Kept"
        LunaGUI._on_username_changed(self.gui, "   ")
        self.assertEqual(self.gui.user_name, "Kept")

    def test_username_changed_non_string_arg(self):
        LunaGUI._on_username_changed(self.gui, 123)
        self.assertEqual(self.gui.user_name, "123")

    def test_persist_user_name_uses_set_user_name(self):
        LunaGUI._persist_user_name(self.gui, "Zoe")
        self.mock_db.initialize.assert_called()
        self.mock_db.set_user_name.assert_called_with("Zoe")

    def test_persist_user_name_falls_back_to_settings(self):
        db = self.mock_db
        if hasattr(db, "set_user_name"):
            delattr(db, "set_user_name")
        LunaGUI._persist_user_name(self.gui, "Zoe")
        self.mock_db.set_setting.assert_any_call("user_name", "Zoe")
        self.mock_db.set_setting.assert_any_call("username", "Zoe")

    def test_persist_user_name_swallows_exceptions(self):
        self.mock_db.initialize.side_effect = RuntimeError("boom")
        LunaGUI._persist_user_name(self.gui, "Zoe")


if __name__ == "__main__":
    unittest.main()

