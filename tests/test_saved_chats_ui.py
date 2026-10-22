"""Unit tests for the Saved Chats section of the LUNA GUI.

The GUI reads saved conversations through ``Database.get_instance()``, so each
test patches that accessor to hand back an isolated temporary database instead
of the shared ``%APPDATA%/Luna/luna.db`` file. Button clicks are exercised by
calling the handler that the button's ``clicked`` signal is connected to, which
keeps the tests free of any display or mouse dependency. This PySide6 build
exposes no getter for list item text, so the displayed labels are checked
through ``saved_chats_list_label`` and the list is checked by item count.
"""

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app.ui.luna import LunaGUI
from PySide6.QtWidgets import QApplication, QLabel
from app.storage.database import Database

USER_PREFIX = "User:"
AGENT_PREFIX = "Agent:"
CHAT_HEADER_PREFIX = "Saved chat:"
USER_LABEL = "Welcome to LUNA"


def get_application():
    """Return the process-wide QApplication, creating it only on first use.

    Qt keeps one application singleton per process, so a test may not build a
    second ``QApplication`` while an earlier one is still alive.
    """
    return QApplication.instance() or QApplication()


class TestSavedChatsUI(unittest.TestCase):
    """Tests for the Saved Chats list, Refresh button, and Open button."""

    def setUp(self):
        self.app = get_application()
        self.temp_dir = tempfile.TemporaryDirectory(prefix="luna_saved_chats_")
        self.db_path = Path(self.temp_dir.name) / "test_luna.db"
        self.db = None
        self.gui = None
        self.patcher = None

    def tearDown(self):
        if self.patcher is not None:
            self.patcher.stop()
        if self.db is not None:
            self.db.close()
        self.temp_dir.cleanup()

    def get_db(self):
        """Create and initialize an isolated test database."""
        self.db = Database(db_path=self.db_path)
        self.db.initialize()
        return self.db

    def build_gui(self):
        """Build the GUI while the shared database accessor serves the temp db."""
        if self.db is None:
            self.get_db()
        self.patcher = patch(
            "app.storage.database.Database.get_instance",
            side_effect=lambda: self.db,
        )
        self.patcher.start()
        self.gui = LunaGUI()
        return self.gui

    def saved_chat_labels(self):
        """Return the labels the Saved Chats list shows, top to bottom."""
        return [
            self.gui.saved_chats_list_label(record)
            for record in self.gui._saved_chat_records
        ]

    def chat_texts(self):
        """Return the chat area's label texts, top to bottom."""
        return [
            child.text()
            for child in self.gui.chat_container.children()
            if isinstance(child, QLabel) and child.text()
        ]

    def test_saved_chats_section_exists(self):
        gui = self.build_gui()

        self.assertTrue(hasattr(gui, "saved_chats_list"))
        self.assertTrue(hasattr(gui, "saved_chats_refresh"))
        self.assertTrue(hasattr(gui, "saved_chats_open"))
        self.assertEqual(gui.saved_chats_refresh.text(), "Refresh")
        self.assertEqual(gui.saved_chats_open.text(), "Open")

    def test_refresh_lists_saved_conversations_newest_first(self):
        db = self.get_db()
        first = db.create_conversation("First Chat")
        second = db.create_conversation("Second Chat")

        gui = self.build_gui()

        self.assertEqual([record["id"] for record in gui._saved_chat_records], [second, first])
        self.assertEqual(gui.saved_chats_list.count(), 2)
        labels = self.saved_chat_labels()
        self.assertEqual(len(labels), 2)
        self.assertIn("Second Chat", labels[0])
        self.assertIn("First Chat", labels[1])

    def test_refresh_button_adds_conversation_saved_after_launch(self):
        db = self.get_db()
        older = db.create_conversation("Older Chat")

        gui = self.build_gui()
        self.assertEqual(gui.saved_chats_list.count(), 1)

        newer = db.create_conversation("Newer Chat")
        db.add_message(newer, "user", "Saved after launch")

        gui._refresh_saved_chats()

        self.assertEqual(gui.saved_chats_list.count(), 2)
        self.assertEqual(
            [record["id"] for record in gui._saved_chat_records], [newer, older]
        )

    def test_refresh_shows_placeholder_for_an_empty_database(self):
        gui = self.build_gui()

        self.assertEqual(gui.saved_chats_list.count(), 1)
        self.assertEqual(gui._saved_chat_records, [])

    def test_open_shows_selected_conversation_chronologically(self):
        db = self.get_db()
        first = db.create_conversation("First Chat")
        second = db.create_conversation("Second Chat")
        db.add_message(first, "user", "First user turn")
        db.add_message(first, "assistant", "First assistant turn")
        db.add_message(first, "user", "Second user turn")
        db.add_message(second, "user", "Other chat turn")

        gui = self.build_gui()
        gui.saved_chats_list.setCurrentRow(1)

        gui._open_saved_chat()

        texts = self.chat_texts()
        self.assertEqual(len(texts), 4)
        self.assertTrue(texts[0].startswith(CHAT_HEADER_PREFIX))
        self.assertIn("First Chat", texts[0])
        self.assertTrue(texts[1].startswith(USER_PREFIX))
        self.assertIn("First user turn", texts[1])
        self.assertTrue(texts[2].startswith(AGENT_PREFIX))
        self.assertIn("First assistant turn", texts[2])
        self.assertTrue(texts[3].startswith(USER_PREFIX))
        self.assertIn("Second user turn", texts[3])

    def test_open_without_selection_leaves_chat_area_unchanged(self):
        db = self.get_db()
        db.create_conversation("Only Chat")

        gui = self.build_gui()

        before = self.chat_texts()
        self.assertEqual(gui.saved_chats_list.currentRow(), -1)

        gui._open_saved_chat()

        self.assertEqual(self.chat_texts(), before)
        self.assertIn(USER_LABEL, before[0])

    def test_open_with_an_out_of_range_selection_keeps_current_chat(self):
        db = self.get_db()
        db.create_conversation("Only Chat")

        gui = self.build_gui()
        gui.saved_chats_list.setCurrentRow(5)

        before = self.chat_texts()
        gui._open_saved_chat()

        self.assertEqual(self.chat_texts(), before)
        self.assertIn(USER_LABEL, before[0])

    def test_refresh_stays_in_sync_after_opening_a_saved_chat(self):
        db = self.get_db()
        db.create_conversation("Only Chat")

        gui = self.build_gui()
        gui.saved_chats_list.setCurrentRow(0)
        gui._open_saved_chat()

        self.assertEqual(len(self.chat_texts()), 1)
        self.assertIn("Only Chat", self.chat_texts()[0])

        gui._refresh_saved_chats()
        self.assertEqual(gui.saved_chats_list.count(), 1)
        self.assertEqual(len(gui._saved_chat_records), 1)

    def test_unreachable_database_never_breaks_the_gui(self):
        def unreachable():
            raise OSError("database file could not be opened")

        patcher = patch(
            "app.storage.database.Database.get_instance", side_effect=unreachable
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        gui = LunaGUI()

        self.assertEqual(gui.saved_chats_list.count(), 1)
        self.assertEqual(gui._saved_chat_records, [])

    def test_history_button_is_left_untouched(self):
        db = self.get_db()
        db.create_conversation("Only Chat")

        gui = self.build_gui()

        self.assertEqual(gui.history_button.text(), "History: OFF")
        self.assertFalse(gui._history_recording)

        gui._refresh_saved_chats()
        gui.saved_chats_list.setCurrentRow(0)
        gui._open_saved_chat()

        self.assertEqual(gui.history_button.text(), "History: OFF")
        self.assertFalse(gui._history_recording)


if __name__ == "__main__":
    unittest.main()
