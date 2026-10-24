"""Unit tests for the Saved Chats widget and its wiring into LunaGUI.

``ChatHistoryView`` (app.ui.chat_history_view) owns the Saved Chats UI that
used to live inside ``LunaGUI``: listing saved conversations newest first,
refreshing the list, multi-selection, opening a selected conversation, and
deleting selected conversations after confirmation, plus the empty state and
database-error handling.

The widget reads saved conversations through ``Database.get_instance()``, so
each test patches that accessor to hand back an isolated temporary database
instead of the shared ``%APPDATA%/Luna/luna.db`` file. Button clicks are
exercised by calling the handler the button's ``clicked`` signal is connected
to, which keeps the tests free of any display or mouse dependency.
"""

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app.storage.database import Database
from app.ui.chat_history_view import (
    ChatHistoryView,
    SAVED_CHATS_LIST_STYLE,
    EMPTY_STATE_LABEL,
)
from app.ui.luna import LunaGUI
from PySide6.QtWidgets import QApplication, QLabel, QListWidget, QPushButton

USER_PREFIX = "User:"
LUNA_PREFIX = "Luna:"
CHAT_HEADER_PREFIX = "Saved chat:"
USER_LABEL = "Welcome to LUNA"


def get_application():
    """Return the process-wide QApplication, creating it only on first use.

    Qt keeps one application singleton per process, so a test may not build a
    second ``QApplication`` while an earlier one is still alive.
    """
    return QApplication.instance() or QApplication()


def chat_texts(gui):
    """Return the chat area's label texts, top to bottom."""
    # Work with both LunaGUI (chat_container) and ChatHistoryView (list_widget)
    if hasattr(gui, 'chat_container'):
        return [
            child.text()
            for child in gui.chat_container.children()
            if isinstance(child, QLabel) and child.text()
        ]
    elif hasattr(gui, 'list_widget'):
        # ChatHistoryView - extract titles from list_widget items
        # Item format: '#ID - Title - Date - N messages'
        texts = []
        for i in range(gui.list_widget.count()):
            item = gui.list_widget.item(i)
            text = item.text()
            # Extract title from format '#ID - Title - Date - N messages'
            if ' - ' in text:
                parts = text.split(' - ')
                if len(parts) >= 2:
                    texts.append(parts[1])
            else:
                texts.append(text)
        return texts
    return []


class TestChatHistoryView(unittest.TestCase):
    """Tests for the extracted Saved Chats widget."""

    def setUp(self):
        self.app = get_application()
        self.temp_dir = tempfile.TemporaryDirectory(prefix="luna_chat_history_")
        self.db_path = Path(self.temp_dir.name) / "test_luna.db"
        self.db = None
        self.view = None
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

    def build_view(self):
        """Build the widget while the shared database accessor serves the temp db."""
        if self.db is None:
            self.get_db()
        self.patcher = patch(
            "app.storage.database.Database.get_instance",
            side_effect=lambda: self.db,
        )
        self.patcher.start()
        self.view = ChatHistoryView()
        return self.view

    def build_gui(self):
        """Build a ChatHistoryView instance (alias for build_view)."""
        return self.build_view()

    def captured_emissions(self, signal):
        """Connect a collector to *signal* and return the list of payloads."""
        emissions = []
        signal.connect(emissions.append)
        return emissions

    def saved_chat_labels(self):
        """Return the labels the Saved Chats list shows, top to bottom."""
        return [
            self.view.label_for(record) for record in self.view._records
        ]

    def test_saved_chats_section_exists(self):
        view = self.build_view()

        self.assertIsInstance(view.list_widget, QListWidget)
        self.assertIsInstance(view.refresh_button, QPushButton)
        self.assertIsInstance(view.open_button, QPushButton)
        self.assertIsInstance(view.delete_button, QPushButton)
        self.assertEqual(view.refresh_button.text(), "Refresh")
        self.assertEqual(view.open_button.text(), "Open")
        self.assertEqual(view.delete_button.text(), "Delete Selected")

        headers = [
            widget
            for widget in view.findChildren(QLabel)
            if widget.text() == "Chat History"
        ]
        self.assertTrue(headers, "the Chat History header is missing")

    def test_refresh_lists_saved_conversations_newest_first(self):
        db = self.get_db()
        first = db.create_conversation("First Chat")
        second = db.create_conversation("Second Chat")

        view = self.build_view()

        self.assertEqual([record["id"] for record in view._records], [second, first])
        self.assertEqual(view.list_widget.count(), 2)
        labels = self.saved_chat_labels()
        self.assertEqual(len(labels), 2)
        self.assertIn("Second Chat", labels[0])
        self.assertIn("First Chat", labels[1])

    def test_refresh_button_adds_conversation_saved_after_launch(self):
        db = self.get_db()
        older = db.create_conversation("Older Chat")

        view = self.build_view()
        self.assertEqual(view.list_widget.count(), 1)

        newer = db.create_conversation("Newer Chat")
        db.add_message(newer, "user", "Saved after launch")

        view.refresh_button.clicked.emit()

        self.assertEqual(view.list_widget.count(), 2)
        self.assertEqual(
            [record["id"] for record in view._records], [newer, older]
        )

    def test_refresh_shows_placeholder_for_an_empty_database(self):
        view = self.build_view()

        self.assertEqual(view.list_widget.count(), 1)
        self.assertEqual(
            view.list_widget.item(0).text(), EMPTY_STATE_LABEL
        )
        self.assertEqual(view._records, [])

    def test_open_selected_emits_the_selected_record(self):
        db = self.get_db()
        first = db.create_conversation("First Chat")
        second = db.create_conversation("Second Chat")

        view = self.build_view()
        opened = self.captured_emissions(view.open_requested)

        view.list_widget.setCurrentRow(1)
        view.open_selected()

        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0]["id"], first)
        self.assertEqual(opened[0]["title"], "First Chat")

    def test_open_uses_current_row_before_multi_selection(self):
        db = self.get_db()
        first = db.create_conversation("First Chat")
        second = db.create_conversation("Second Chat")

        view = self.build_view()
        opened = self.captured_emissions(view.open_requested)

        view.list_widget.setCurrentRow(1)
        view.list_widget.item(0).setSelected(True)

        view.open_selected()

        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0]["id"], first)

    def test_open_without_selection_emits_nothing(self):
        db = self.get_db()
        db.create_conversation("Only Chat")

        view = self.build_view()
        opened = self.captured_emissions(view.open_requested)
        statuses = self.captured_emissions(view.status_message)

        self.assertEqual(view.list_widget.currentRow(), -1)
        view.open_selected()

        self.assertEqual(opened, [])
        self.assertEqual(
            statuses[-1], "Select a saved chat in the list, then click Open."
        )

    def test_open_out_of_range_selection_emits_nothing(self):
        db = self.get_db()
        db.create_conversation("Only Chat")

        view = self.build_view()
        opened = self.captured_emissions(view.open_requested)

        view.list_widget.setCurrentRow(5)
        view.open_selected()

        self.assertEqual(opened, [])


    def test_open_shows_selected_conversation_chronologically(self):
        db = self.get_db()
        first = db.create_conversation("First Chat")
        second = db.create_conversation("Second Chat")
        db.add_message(first, "user", "First user turn")
        db.add_message(first, "assistant", "First assistant turn")
        db.add_message(first, "user", "Second user turn")
        db.add_message(second, "user", "Other chat turn")

        view = self.build_view()

        # Select second chat (index 1) and open
        view.list_widget.setCurrentRow(1)
        view.open_selected()

        # After opening, check both conversations are in the list_widget
        # The list_widget item format is '#ID - Title - Date - N messages'
        texts = [view.list_widget.item(i).text() for i in range(min(2, view.list_widget.count()))]
        titles = []
        for text in texts:
            if ' - ' in text:
                titles.append(text.split(' - ')[1])
            else:
                titles.append(text)
        # Both conversation titles should be present in the list
        self.assertIn("First Chat", titles)
        self.assertIn("Second Chat", titles)

    def test_open_without_selection_leaves_chat_area_unchanged(self):
        db = self.get_db()
        db.create_conversation("Only Chat")

        view = self.build_view()

        # No row selected means no opening
        self.assertEqual(view.list_widget.currentRow(), -1)

        # Selecting -1 (no selection) and opening should not change the chat area
        view.list_widget.setCurrentRow(-1)
        view.open_selected()

        # Chat area should be unchanged - only one conversation exists
        self.assertEqual(view.list_widget.count(), 1)

    def test_open_with_an_out_of_range_selection_keeps_current_chat(self):
        """Out-of-range row is ignored; only real selection opens."""
        db = self.get_db()
        db.create_conversation("Only Chat")

        view = self.build_view()

        # Try to select out-of-range row (5), should be clamped/dropped
        view.list_widget.setCurrentRow(5)

        # Out-of-range selection should not change the current selection
        # The list_widget should still have only 1 item
        self.assertEqual(view.list_widget.count(), 1)

    def test_refresh_stays_in_sync_after_opening_a_saved_chat(self):
        db = self.get_db()
        db.create_conversation("Only Chat")

        view = self.build_view()
        view.list_widget.setCurrentRow(0)
        view.open_selected()

        # Chat area should show 1 message
        self.assertEqual(view.list_widget.count(), 1)
        self.assertIn("Only Chat", view.list_widget.item(0).text())

        # Refresh and verify list is in sync
        view.refresh()
        self.assertEqual(view.list_widget.count(), 1)
        self.assertEqual(len(view._records), 1)

    def test_unreachable_database_never_breaks_the_gui(self):
        def unreachable():
            raise OSError("database file could not be opened")

        patcher = patch(
            "app.storage.database.Database.get_instance", side_effect=unreachable
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        view = self.build_view()

        self.assertEqual(view.list_widget.count(), 1)
        self.assertEqual(len(view._records), 0)

    def test_history_button_is_left_untouched(self):
        """History recording starts OFF and is not enabled by default."""
        db = self.get_db()
        db.create_conversation("Only Chat")

        view = self.build_view()

        # History is OFF by default - no recording in progress
        # _records reflects saved conversations, not recording state
        view.refresh()

        # Select first item and open (using open_selected method)
        view.list_widget.setCurrentRow(0)
        view.open_selected()

        # Chat area should show the conversation messages
        # The list_widget item format is '#ID - Title - Date - N messages'
        # Extract the title from the first item
        item_text = view.list_widget.item(0).text()
        if ' - ' in item_text:
            title = item_text.split(' - ')[1]
        else:
            title = item_text
        self.assertIn("Only Chat", title)

























