"""Saved Chats section extracted into its own PySide6 widget.

The widget owns everything the Saved Chats UI did inside ``LunaGUI``: listing
saved conversations newest first, refreshing the list, multi-selection,
opening a selected conversation, deleting selected conversations after
confirmation, the empty state, and database-error handling.

It never reaches into the main window. User intent is reported through
signals (``open_requested`` carries the selected conversation record;
``status_message`` carries text for the main window's status bar), and the
database is only touched through the public ``Database`` API - either the
shared accessor or an injected one - so ``LunaGUI`` keeps full ownership of
the main window, the sidebar, the chat area, and the view switching.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.storage.database import Database

# Styling for the Saved Chats list. Titles must be legible before anything is
# selected, so the list gets an opaque dark background (a translucent one washes
# the labels into the page behind it) and the ::item rule sets the text colour
# directly - which is where Qt actually applies it. Both selected states are
# spelled out so a selected row keeps light text on dark indigo whether the
# list has focus or not.
SAVED_CHATS_LIST_STYLE = (
    "QListWidget {"
    "background-color: #101a24;"
    "color: #f8fafc;"
    "border: 1px solid #475569;"
    "border-radius: 6px;"
    "padding: 4px;"
    "font-size: 12px;"
    "outline: 0;"
    "}"
    "QListWidget::item {"
    "color: #f8fafc;"
    "background-color: transparent;"
    "spacing: 4px;"
    "padding: 2px 6px 2px 6px;"
    "border-radius: 4px;"
    "}"
    "QListWidget::item:pressed {"
    "color: #ffffff;"
    "background-color: #4f46e5;"
    "}"
    "QListWidget::item:selected {"
    "color: #ffffff;"
    "background-color: #4f46e5;"
    "}"
)

# Shown when the list holds no conversations, including when the database
# cannot be reached - a failed read never breaks the GUI, it just shows
# nothing to act on.
EMPTY_STATE_LABEL = "No saved chats yet."


class ChatHistoryView(QWidget):
    """The Saved Chats section: list, refresh, open, delete selected."""

    #: Emitted when the user asks to open the selected conversation.
    #: Payload: the conversation record (dict) as returned by
    #: ``Database.get_all_conversations``.
    open_requested = Signal(object)

    #: Emitted with a short user-facing status message for the main window's
    #: status bar (refresh results, delete outcomes, prompts).
    status_message = Signal(str)

    def __init__(
        self,
        get_database: Callable[[], Database] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._get_database = get_database or Database.get_instance
        self._records: list[dict] = []
        self._setup_ui()
        # Show the chats saved in previous sessions, newest first, even though
        # the section may be closed. An unreachable database leaves an empty
        # list instead of breaking the window.
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel("Chat History")
        header.setStyleSheet("font-weight: bold; color: #93c5fd;")
        layout.addWidget(header)

        actions = QVBoxLayout()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh_button.setStyleSheet(
            "background-color: #0ea5e9;"
            "color: white;"
            "border-radius: 8px; padding: 8px 20px;"
            "font-weight: bold;"
            "min-width: 80px;"
        )
        actions.addWidget(self.refresh_button)

        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self.open_selected)
        self.open_button.setStyleSheet(
            "background-color: #7c3aed;"
            "color: white;"
            "border-radius: 8px; padding: 8px 20px;"
            "font-weight: bold;"
            "min-width: 80px;"
        )
        actions.addWidget(self.open_button)

        # Delete every conversation the user has selected in the list after one
        # confirmation prompt (red so it reads as a destructive action next to
        # Open). Only the selected ids are removed - see delete_selected.
        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.clicked.connect(self.delete_selected)
        self.delete_button.setStyleSheet(
            "background-color: #dc2626;"
            "color: white;"
            "border-radius: 8px; padding: 8px 20px;"
            "font-weight: bold;"
            "min-width: 80px;"
        )
        actions.addWidget(self.delete_button)

        actions.setAlignment(Qt.AlignHCenter)
        layout.addLayout(actions)

        self.list_widget = QListWidget()
        # See SAVED_CHATS_LIST_STYLE: opaque background plus an explicit
        # ::item colour keep conversation titles readable, and both selected
        # states keep light text so a marked row never goes dark-on-dark.
        self.list_widget.setStyleSheet(SAVED_CHATS_LIST_STYLE)
        # MultipleSelection lets one Delete Selected click act on several
        # conversations; SelectRows highlights and selects a whole row.
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        self.list_widget.setSelectionBehavior(QListWidget.SelectRows)
        self.list_widget.setMinimumHeight(140)
        layout.addWidget(self.list_widget)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-read the database and rebuild the list, newest first."""
        try:
            records = self._get_database().get_all_conversations()
        except Exception:  # noqa: S110 - an unreachable database shows nothing
            records = []
        self._records = records
        self.list_widget.clear()

        if not records:
            self.list_widget.insertItems(0, [EMPTY_STATE_LABEL])
            self.status_message.emit("No saved chats to show.")
            return

        labels = [self.label_for(record) for record in self._records]
        self.list_widget.insertItems(0, labels)
        self.status_message.emit(f"Saved chats refreshed: {len(self._records)}")

    @staticmethod
    def label_for(conversation: dict) -> str:
        """Build the one-line label shown in the Saved Chats list."""
        title = str(conversation.get("title") or "Untitled").strip()
        updated = str(
            conversation.get("updated_at") or conversation.get("created_at") or ""
        )
        message_count = len(conversation.get("messages") or [])
        return (
            f"#{conversation.get('id')} - {title} - {updated} "
            f"- {message_count} messages"
        )

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def selected_rows(self) -> list[int]:
        """Return the selected list rows that still have a cached record.

        Both selection styles count: the list's own multi-selection marks and
        the current row set by a single click. Rows outside the cached
        records are dropped so a stale selection can never address a
        conversation that is not shown in the list.
        """
        candidates: list[int] = []
        try:
            raw_selection = list(self.list_widget.selectedIndexes())
        except Exception:  # noqa: S110
            raw_selection = []

        for item in raw_selection:
            # QListWidget reports selection rows as QModelIndex-like values, so
            # the plain int conversion is tried first and the row accessor second.
            try:
                candidates.append(int(item))
            except (TypeError, ValueError):
                try:
                    candidates.append(int(item.row()))
                except Exception:  # noqa: S110
                    continue

        current_row = self.list_widget.currentRow()
        if current_row >= 0:
            candidates.append(current_row)

        rows: list[int] = []
        for row in candidates:
            if 0 <= row < len(self._records) and row not in rows:
                rows.append(row)

        return rows

    def clear_selection(self) -> None:
        """Drop every selection mark so a stale selection cannot be reused."""
        try:
            self.list_widget.clearSelection()
        except Exception:  # noqa: S110
            pass
        self.list_widget.setCurrentRow(-1)

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    def open_selected(self) -> None:
        """Ask the main window to open the topmost selected conversation.

        The current row wins when one is set, matching a single click; only
        then does the multi-selection fall back to its topmost row. The main
        window receives the conversation record through ``open_requested``
        and decides how to display it.
        """
        current_row = self.list_widget.currentRow()
        if 0 <= current_row < len(self._records):
            self.open_requested.emit(self._records[current_row])
            return

        rows = self.selected_rows()
        if not rows:
            self.status_message.emit(
                "Select a saved chat in the list, then click Open."
            )
            return

        self.open_requested.emit(self._records[rows[0]])

    def delete_selected(self) -> None:
        """Delete every selected saved conversation after one confirmation."""
        rows = self.selected_rows()
        if not rows:
            self.status_message.emit(
                "Select the saved chats to delete in the list, "
                "then click Delete Selected."
            )
            return

        conversations = [self._records[row] for row in rows]
        conversation_ids = [
            conversation.get("id")
            for conversation in conversations
            if conversation.get("id") is not None
        ]

        if not conversation_ids:
            self.status_message.emit(
                "The selected saved chats have no usable id, so nothing was "
                "deleted."
            )
            return

        if not self._confirm_deletion(conversations):
            self.status_message.emit(
                f"Delete cancelled - all {len(conversations)} saved chats are kept."
            )
            return

        try:
            database = self._get_database()
        except Exception:  # noqa: S110
            self.status_message.emit(
                "Delete failed - the database could not be reached."
            )
            return

        deleted_ids: list[int] = []
        failed_ids: list = []
        for conversation_id in conversation_ids:
            try:
                database.delete_conversation(conversation_id)
                deleted_ids.append(conversation_id)
            except Exception:  # noqa: S110
                failed_ids.append(conversation_id)

        if not deleted_ids:
            self.status_message.emit(
                "Delete failed - the saved chats are still in the database."
            )
            return

        # Re-read the database so the deleted rows disappear from the list,
        # then clear both selection marks: the old rows no longer exist.
        self.refresh()
        self.clear_selection()

        status = f"Deleted {len(deleted_ids)} saved chat(s) and their messages."
        if failed_ids:
            status += " Could not delete: " + ", ".join(
                f"#{conversation_id}" for conversation_id in failed_ids
            )
        self.status_message.emit(status)

    def _confirm_deletion(self, conversations: list[dict]) -> bool:
        """Ask before deleting; only an explicit Yes is treated as confirmed."""
        count = len(conversations)
        total_messages = sum(
            len(conversation.get("messages") or [])
            for conversation in conversations
        )
        listed = ", ".join(
            f"'{str(conversation.get('title') or 'Untitled').strip()}' "
            f"(#{conversation.get('id')})"
            for conversation in conversations[:8]
        )
        if count > 8:
            listed += f" and {count - 8} more"

        return (
            QMessageBox.question(
                self,
                "Delete saved chat?",
                f"Delete {count} selected conversation(s) and their "
                f"{total_messages} messages? Listed: {listed}. "
                "This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )
