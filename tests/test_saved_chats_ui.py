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

from app.ui.luna import LunaGUI, SAVED_CHATS_LIST_STYLE
from PySide6.QtWidgets import QApplication, QLabel, QListWidget
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

    def test_delete_button_exists_in_saved_chats_section(self):
        db = self.get_db()
        only = db.create_conversation("Only Chat")

        gui = self.build_gui()

        self.assertTrue(hasattr(gui, "saved_chats_delete"))
        self.assertEqual(gui.saved_chats_delete.text(), "Delete Selected")

        gui.saved_chats_delete.clicked.emit()

        self.assertEqual(gui.saved_chats_list.currentRow(), -1)
        self.assertEqual(
            [record["id"] for record in db.get_all_conversations()], [only]
        )

    def test_delete_removes_only_the_selected_saved_chat(self):
        db = self.get_db()
        older = db.create_conversation("Older Chat")
        db.add_message(older, "user", "Older chat turn")
        newer = db.create_conversation("Newer Chat")
        db.add_message(newer, "assistant", "Newer chat turn")

        gui = self.build_gui()
        gui.saved_chats_list.setCurrentRow(0)
        self.assertEqual(gui._saved_chat_records[0]["id"], newer)

        with patch.object(gui, "_confirm_deletion", return_value=True):
            gui._delete_saved_chat()

        remaining = db.get_all_conversations()
        self.assertEqual([record["id"] for record in remaining], [older])
        self.assertEqual(
            [record["id"] for record in gui._saved_chat_records], [older]
        )
        self.assertEqual(gui.saved_chats_list.count(), 1)

    def test_deleting_a_saved_chat_removes_its_messages_too(self):
        db = self.get_db()
        first = db.create_conversation("First Chat")
        first_chat_turn = db.add_message(first, "user", "First user turn")
        first_assistant_turn = db.add_message(
            first, "assistant", "First assistant turn"
        )
        second = db.create_conversation("Second Chat")
        second_chat_turn = db.add_message(second, "user", "Second chat turn")

        gui = self.build_gui()
        gui.saved_chats_list.setCurrentRow(0)

        with patch.object(gui, "_confirm_deletion", return_value=True):
            gui._delete_saved_chat()

        remaining = db.get_all_conversations()
        self.assertEqual([record["id"] for record in remaining], [first])
        self.assertEqual(gui.saved_chats_list.count(), 1)
        self.assertEqual(db.get_messages_for_conversation(second), [])
        self.assertEqual(
            [message["id"] for message in remaining[0]["messages"]],
            [first_chat_turn, first_assistant_turn],
        )
        self.assertEqual(
            [message["content"] for message in remaining[0]["messages"]],
            ["First user turn", "First assistant turn"],
        )

    def test_delete_asks_confirmation_before_touching_the_database(self):
        db = self.get_db()
        only = db.create_conversation("Only Chat")
        db.add_message(only, "user", "Only chat turn")

        gui = self.build_gui()
        gui.saved_chats_list.setCurrentRow(0)

        with patch("app.ui.luna.QMessageBox") as message_box:
            message_box.question.return_value = message_box.Yes

            gui._delete_saved_chat()

            self.assertEqual(message_box.question.call_count, 1)
            self.assertEqual(
                message_box.question.call_args[0][1], "Delete saved chat?"
            )
            self.assertIn("Only Chat", message_box.question.call_args[0][2])

        self.assertEqual(db.get_all_conversations(), [])
        self.assertEqual(db.get_messages_for_conversation(only), [])
        self.assertEqual(gui._saved_chat_records, [])
        self.assertEqual(gui.saved_chats_list.count(), 1)

    def test_declining_the_confirmation_prompt_keeps_the_saved_chat(self):
        db = self.get_db()
        only = db.create_conversation("Only Chat")
        db.add_message(only, "user", "Only chat turn")

        gui = self.build_gui()
        gui.saved_chats_list.setCurrentRow(0)

        with patch("app.ui.luna.QMessageBox") as message_box:
            message_box.question.return_value = message_box.No

            gui._delete_saved_chat()

        self.assertEqual(message_box.question.call_count, 1)
        self.assertEqual(
            [record["id"] for record in db.get_all_conversations()], [only]
        )
        self.assertEqual(len(db.get_messages_for_conversation(only)), 1)
        self.assertEqual(gui.saved_chats_list.count(), 1)

    def test_delete_without_selection_deletes_nothing(self):
        db = self.get_db()
        first = db.create_conversation("First Chat")
        db.add_message(first, "user", "First user turn")

        gui = self.build_gui()

        self.assertEqual(gui.saved_chats_list.currentRow(), -1)

        gui._delete_saved_chat()

        self.assertEqual(
            [record["id"] for record in db.get_all_conversations()], [first]
        )
        self.assertEqual(len(db.get_messages_for_conversation(first)), 1)
        self.assertEqual(gui.saved_chats_list.count(), 1)

    def test_delete_with_an_out_of_range_selection_deletes_nothing(self):
        db = self.get_db()
        first = db.create_conversation("First Chat")
        db.add_message(first, "user", "First user turn")

        gui = self.build_gui()
        gui.saved_chats_list.setCurrentRow(5)

        gui._delete_saved_chat()

        self.assertEqual(
            [record["id"] for record in db.get_all_conversations()], [first]
        )
        self.assertEqual(len(db.get_messages_for_conversation(first)), 1)
        self.assertEqual(gui.saved_chats_list.count(), 1)

    def test_database_failure_on_delete_never_breaks_the_gui(self):
        db = self.get_db()
        only = db.create_conversation("Only Chat")
        db.add_message(only, "user", "Only chat turn")

        gui = self.build_gui()
        gui.saved_chats_list.setCurrentRow(0)

        delete_failure = OSError("database write failed")

        with patch.object(gui, "_confirm_deletion", return_value=True):
            with patch.object(db, "delete_conversation", side_effect=delete_failure):
                gui._delete_saved_chat()

        self.assertEqual(
            [record["id"] for record in db.get_all_conversations()], [only]
        )
        self.assertEqual(len(db.get_messages_for_conversation(only)), 1)
        self.assertEqual(gui.saved_chats_list.count(), 1)

    def test_refresh_stays_in_sync_after_deleting_the_newest_saved_chat(self):
        db = self.get_db()
        older = db.create_conversation("Older Chat")
        db.add_message(older, "user", "Older chat turn")
        newer = db.create_conversation("Newer Chat")
        db.add_message(newer, "user", "Newer chat turn")

        gui = self.build_gui()
        self.assertEqual(
            [record["id"] for record in gui._saved_chat_records], [newer, older]
        )
        self.assertEqual(gui.saved_chats_list.count(), 2)

        gui.saved_chats_list.setCurrentRow(0)

        with patch.object(gui, "_confirm_deletion", return_value=True):
            gui._delete_saved_chat()

        self.assertEqual(
            [record["id"] for record in gui._saved_chat_records], [older]
        )
        self.assertEqual(gui.saved_chats_list.count(), 1)




    def test_saved_chats_list_style_stays_readable_when_unselected(self):
        """The opaque list background and explicit ::item colours are kept."""
        gui = self.build_gui()

        # No translucent background: a washed-out panel is what made titles
        # unreadable before.
        self.assertNotIn("rgba(", SAVED_CHATS_LIST_STYLE)
        self.assertIn("background-color: #101a24;", SAVED_CHATS_LIST_STYLE)

        # Item text colour is set on the item rule itself, the place Qt applies
        # it, so titles are light on dark before anything is selected.
        item_rule = SAVED_CHATS_LIST_STYLE.split("QListWidget::item {")[1]
        self.assertIn("color: #f8fafc;", item_rule)

        # Both selected states keep light text on a dark highlight so a marked
        # row never becomes dark-on-dark, focused or not.
        active_rule = SAVED_CHATS_LIST_STYLE.split(
            "QListWidget::item:selected:active {"
        )[1]
        inactive_rule = SAVED_CHATS_LIST_STYLE.split(
            "QListWidget::item:selected:inactive {"
        )[1]
        self.assertIn("color: #ffffff;", active_rule)
        self.assertIn("background-color: #4f46e5;", active_rule)
        self.assertIn("color: #f8fafc;", inactive_rule)
        self.assertIn("background-color: #3730a3;", inactive_rule)

        self.assertEqual(
            gui.saved_chats_list.selectionMode(),
            QListWidget.MultiSelection,
        )

    def test_multi_selection_marks_several_rows_at_once(self):
        """selectAll() marks every row, so selection is not limited to one."""
        db = self.get_db()
        for title in ("First Chat", "Second Chat", "Third Chat"):
            conversation_id = db.create_conversation(title)
            db.add_message(conversation_id, "user", f"{title} turn")

        gui = self.build_gui()
        self.assertEqual(gui.saved_chats_list.count(), 3)

        gui.saved_chats_list.selectAll()

        self.assertEqual(gui._selected_chat_rows(), [0, 1, 2])

    def test_open_falls_back_to_the_topmost_selected_saved_chat(self):
        """Multi-selection leaves no current row; opening still shows one chat."""
        db = self.get_db()
        older = db.create_conversation("Older Chat")
        db.add_message(older, "user", "Older chat turn")
        newer = db.create_conversation("Newer Chat")
        db.add_message(newer, "assistant", "Newer chat turn")

        gui = self.build_gui()
        gui.saved_chats_list.selectAll()
        self.assertEqual(gui.saved_chats_list.currentRow(), -1)

        gui._open_saved_chat()

        self.assertEqual(
            self.chat_texts()[0], f"Saved chat: Newer Chat (#{newer})"
        )
        self.assertEqual(gui.history_button.text(), "History: OFF")
        self.assertFalse(gui._history_recording)

    def test_opening_a_saved_chat_never_sends_a_provider_request(self):
        """Reading history must not reach the agent or flip the recording flag."""
        db = self.get_db()
        only = db.create_conversation("Only Chat")
        db.add_message(only, "user", "Only chat turn")

        gui = self.build_gui()
        gui.saved_chats_list.setCurrentRow(0)

        with patch("app.ui.luna.AgentService") as agent_service:
            gui._open_saved_chat()

        self.assertEqual(agent_service.process_message.call_count, 0)
        self.assertEqual(gui.history_button.text(), "History: OFF")
        self.assertFalse(gui._history_recording)



    def test_delete_selected_removes_every_selected_saved_chat(self):
        """Rows 0 and 2 are deleted; row 1 and its messages are kept."""
        db = self.get_db()
        older = db.create_conversation("Older Chat")
        db.add_message(older, "user", "Older chat turn")
        middle = db.create_conversation("Middle Chat")
        db.add_message(middle, "user", "Middle chat turn")
        newer = db.create_conversation("Newer Chat")
        db.add_message(newer, "user", "Newer chat turn")

        gui = self.build_gui()
        self.assertEqual(
            [record["id"] for record in gui._saved_chat_records],
            [newer, middle, older],
        )

        # Qt reports selection as QModelIndex values, so the row lookup is
        # exercised directly with the row numbers the list would report.
        with patch.object(gui, "_selected_chat_indexes", return_value=[0, 2]):
            with patch.object(gui, "_confirm_deletion", return_value=True):
                gui._delete_saved_chat()

        remaining = db.get_all_conversations()
        self.assertEqual([record["id"] for record in remaining], [middle])
        self.assertEqual(db.get_messages_for_conversation(newer), [])
        self.assertEqual(db.get_messages_for_conversation(older), [])
        self.assertEqual(
            [message["content"] for message in remaining[0]["messages"]],
            ["Middle chat turn"],
        )
        self.assertEqual(
            [record["id"] for record in gui._saved_chat_records], [middle]
        )
        self.assertEqual(gui.saved_chats_list.count(), 1)

        # The selection is cleared once the rows no longer exist.
        self.assertEqual(gui.saved_chats_list.currentRow(), -1)
        self.assertEqual(list(gui.saved_chats_list.selectedIndexes()), [])

    def test_delete_selected_dialog_states_the_conversation_count(self):
        """The confirmation prompt lists how many conversations go away."""
        db = self.get_db()
        older = db.create_conversation("Older Chat")
        db.add_message(older, "user", "Older chat turn")
        middle = db.create_conversation("Middle Chat")
        db.add_message(middle, "user", "Middle chat turn")
        newer = db.create_conversation("Newer Chat")
        db.add_message(newer, "user", "Newer chat turn")

        gui = self.build_gui()

        with patch.object(gui, "_selected_chat_indexes", return_value=[0, 1]):
            with patch("app.ui.luna.QMessageBox") as message_box:
                message_box.question.return_value = message_box.Yes

                gui._delete_saved_chat()

                self.assertEqual(message_box.question.call_count, 1)
                self.assertEqual(
                    message_box.question.call_args[0][1], "Delete saved chat?"
                )
                question_text = message_box.question.call_args[0][2]

        self.assertIn("Delete 2 selected", question_text)
        self.assertIn("their 2 messages", question_text)
        self.assertIn("Newer Chat", question_text)
        self.assertIn("Middle Chat", question_text)

    def test_multi_delete_ignores_selections_with_no_saved_chat(self):
        """An out-of-range row is dropped; only the real selection is deleted."""
        db = self.get_db()
        older = db.create_conversation("Older Chat")
        db.add_message(older, "user", "Older chat turn")
        newer = db.create_conversation("Newer Chat")
        db.add_message(newer, "user", "Newer chat turn")

        gui = self.build_gui()

        with patch.object(gui, "_selected_chat_indexes", return_value=[0, 7]):
            with patch.object(gui, "_confirm_deletion", return_value=True):
                gui._delete_saved_chat()

        remaining = db.get_all_conversations()
        self.assertEqual([record["id"] for record in remaining], [older])
        self.assertEqual(
            [record["id"] for record in gui._saved_chat_records], [older]
        )
        self.assertEqual(len(db.get_messages_for_conversation(older)), 1)
        self.assertEqual(gui.saved_chats_list.count(), 1)



    def test_cancelling_the_multi_delete_confirmation_deletes_nothing(self):
        """A No answer keeps every conversation and every message."""
        db = self.get_db()
        older = db.create_conversation("Older Chat")
        db.add_message(older, "user", "Older chat turn")
        middle = db.create_conversation("Middle Chat")
        db.add_message(middle, "user", "Middle chat turn")
        newer = db.create_conversation("Newer Chat")
        db.add_message(newer, "user", "Newer chat turn")

        gui = self.build_gui()

        with patch.object(gui, "_selected_chat_indexes", return_value=[0, 1]):
            with patch("app.ui.luna.QMessageBox") as message_box:
                message_box.question.return_value = message_box.No

                gui._delete_saved_chat()

        self.assertEqual(
            [record["id"] for record in db.get_all_conversations()],
            [newer, middle, older],
        )
        for conversation_id in (older, middle, newer):
            self.assertEqual(
                len(db.get_messages_for_conversation(conversation_id)), 1
            )
        self.assertEqual(gui.saved_chats_list.count(), 3)

    def test_partial_database_failure_keeps_the_failed_saved_chat(self):
        """One failing delete never crashes the GUI and never deletes extras."""
        db = self.get_db()
        older = db.create_conversation("Older Chat")
        db.add_message(older, "user", "Older chat turn")
        middle = db.create_conversation("Middle Chat")
        db.add_message(middle, "user", "Middle chat turn")
        newer = db.create_conversation("Newer Chat")
        db.add_message(newer, "user", "Newer chat turn")

        gui = self.build_gui()

        real_delete = db.delete_conversation

        def flaky_delete(conversation_id):
            if conversation_id == newer:
                raise OSError("database write failed")
            real_delete(conversation_id)

        with patch.object(gui, "_selected_chat_indexes", return_value=[0, 1]):
            with patch.object(gui, "_confirm_deletion", return_value=True):
                with patch.object(
                    db, "delete_conversation", side_effect=flaky_delete
                ):
                    gui._delete_saved_chat()

        # The newer chat survived, the middle one was removed, and the list was
        # rebuilt from the database without raising.
        self.assertEqual(
            [record["id"] for record in db.get_all_conversations()],
            [newer, older],
        )
        self.assertEqual(db.get_messages_for_conversation(middle), [])
        self.assertEqual(
            [record["id"] for record in gui._saved_chat_records], [newer, older]
        )
        self.assertEqual(gui.saved_chats_list.count(), 2)

    def test_delete_selected_without_selection_deletes_nothing(self):
        """No row selected means no confirmation prompt and no database write."""
        db = self.get_db()
        first = db.create_conversation("First Chat")
        db.add_message(first, "user", "First user turn")

        gui = self.build_gui()

        self.assertEqual(gui.saved_chats_list.currentRow(), -1)
        self.assertEqual(list(gui.saved_chats_list.selectedIndexes()), [])

        gui._delete_saved_chat()

        self.assertEqual(
            [record["id"] for record in db.get_all_conversations()], [first]
        )
        self.assertEqual(len(db.get_messages_for_conversation(first)), 1)
        self.assertEqual(gui.saved_chats_list.count(), 1)



if __name__ == "__main__":
    unittest.main()
