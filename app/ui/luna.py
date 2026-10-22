"""LUNA — Modular Windows desktop AI assistant GUI."""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QMessageBox, QStatusBar,
    QScrollArea, QListWidget,
)
from PySide6.QtCore import Qt
import sys

from app.agent.service import AgentService
from app.storage.database import Database


class LunaGUI(QMainWindow):
    """Main GUI window for the LUNA application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LUNA")
        self.setMinimumSize(700, 500)

        # Chat history recording is opt-in and always starts OFF for a new
        # application session.
        self._history_recording: bool = False
        AgentService().disable_history_recording()

        # Saved conversations shown in the Saved Chats list, newest first. The
        # list is rebuilt from this record list so opening an entry never needs
        # another database read.
        self._saved_chat_records: list[dict] = []

        self._setup_ui()

    def _on_send_clicked(self) -> None:
        """Handle Send button click - submit text to conversation."""
        input_text = self.input_edit.text().strip()
        if not input_text:
            return
        _display_user_message(input_text, self.msg_layout)
        self._process_agent_response(input_text)
        self.input_edit.clear()

    def _on_mic_clicked(self) -> None:
        """Handle Mic button click - currently a placeholder."""
        pass

    def _on_history_clicked(self) -> None:
        """Handle history button click - toggle chat history recording.

        Toggling only flips the recording flag on AgentService and refreshes
        the button text; it never clears or changes the current chat.
        """
        service = AgentService()
        if self._history_recording:
            service.disable_history_recording()
            self._history_recording = False
        else:
            service.enable_history_recording()
            self._history_recording = True

        self._refresh_history_button()

    def _refresh_history_button(self) -> None:
        """Update the button text and colors to show the current state."""
        if self._history_recording:
            self.history_button.setText("History: ON")
            self.history_button.setStyleSheet(
                "background-color: #10b981;"
                "color: white;"
                "border-radius: 8px; padding: 10px 16px;"
                "font-weight: bold;"
                "min-width: 90px;"
            )
        else:
            self.history_button.setText("History: OFF")
            self.history_button.setStyleSheet(
                "background-color: #64748b;"
                "color: white;"
                "border-radius: 8px; padding: 10px 16px;"
                "font-weight: bold;"
                "min-width: 90px;"
            )

    # ------------------------------------------------------------------
    # Saved chats
    #
    # History: ON is what writes conversations into the shared database, so the
    # saved chats are exactly those records. Reading them is independent of the
    # recording flag: the list can be shown (and a chat opened) while recording
    # is off, and a database that cannot be reached never breaks the GUI.
    # ------------------------------------------------------------------

    def _saved_conversations(self) -> list[dict]:
        """Return saved conversations, newest first, or [] when unreachable."""
        try:
            return Database.get_instance().get_all_conversations()
        except Exception:  # noqa: S110
            return []

    def saved_chats_list_label(self, conversation: dict) -> str:
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

    def _refresh_saved_chats(self) -> None:
        """Re-read the database and rebuild the Saved Chats list, newest first."""
        self._saved_chat_records = self._saved_conversations()
        self.saved_chats_list.clear()

        if not self._saved_chat_records:
            self.saved_chats_list.insertItems(0, ["No saved chats yet."])
            self.status_bar.showMessage("No saved chats to show.")
            return

        labels = [
            self.saved_chats_list_label(conversation)
            for conversation in self._saved_chat_records
        ]
        self.saved_chats_list.insertItems(0, labels)
        self.status_bar.showMessage(
            f"Saved chats refreshed: {len(self._saved_chat_records)}"
        )

    def _open_saved_chat(self) -> None:
        """Show the selected saved conversation in the existing chat area."""
        row = self.saved_chats_list.currentRow()
        if row < 0 or row >= len(self._saved_chat_records):
            self.status_bar.showMessage(
                "Select a saved chat in the list, then click Open."
            )
            return

        conversation = self._saved_chat_records[row]
        conversation_id = conversation.get("id")
        messages = conversation.get("messages") or self._saved_messages(
            conversation_id
        )

        self._clear_chat_area()

        title = str(conversation.get("title") or "Untitled").strip()
        header = QLabel(f"Saved chat: {title} (#{conversation_id})")
        header.setStyleSheet("font-weight: bold; color: #3b82f6;")
        self.msg_layout.addWidget(header)

        for message in messages:
            content = str(message.get("content", ""))
            if message.get("role") == "user":
                _display_user_message(content, self.msg_layout)
            else:
                _display_agent_message(content, self.msg_layout)

        self.status_bar.showMessage(
            f"Opened saved chat #{conversation_id} ({len(messages)} messages)"
        )

    def _delete_saved_chat(self) -> None:
        """Delete the selected saved conversation after an explicit confirmation."""
        row = self.saved_chats_list.currentRow()
        if row < 0 or row >= len(self._saved_chat_records):
            self.status_bar.showMessage(
                "Select a saved chat in the list, then click Delete."
            )
            return

        conversation = self._saved_chat_records[row]
        conversation_id = conversation.get("id")

        if not self._confirm_deletion(conversation):
            self.status_bar.showMessage("Delete cancelled - the saved chat is kept.")
            return

        try:
            Database.get_instance().delete_conversation(conversation_id)
        except Exception:  # noqa: S110
            self.status_bar.showMessage(
                f"Delete failed for saved chat #{conversation_id}."
            )
            return

        # Rebuild the list and the record cache so the deleted entry disappears.
        self._refresh_saved_chats()
        self.status_bar.showMessage(
            f"Deleted saved chat #{conversation_id} and its messages."
        )

    def _confirm_deletion(self, conversation: dict) -> bool:
        """Ask before deleting; only an explicit Yes is treated as confirmation."""
        title = str(conversation.get("title") or "Untitled").strip()
        conversation_id = conversation.get("id")
        message_count = len(conversation.get("messages") or [])

        return (
            QMessageBox.question(
                self,
                "Delete saved chat?",
                f"Delete '{title}' (#{conversation_id}) and its "
                f"{message_count} messages? This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        )

    def _saved_messages(self, conversation_id: int) -> list[dict]:
        """Return one conversation's messages in creation order, [] if failed."""
        try:
            return Database.get_instance().get_messages_for_conversation(
                conversation_id
            )
        except Exception:  # noqa: S110
            return []

    def _clear_chat_area(self) -> None:
        """Remove the messages currently shown in the chat scroll area."""
        for child in list(self.chat_container.children()):
            # The layout itself is a child in Qt 6: keep it so later messages
            # still land in the same chat area.
            if child is not self.msg_layout:
                child.setParent(None)

    def _process_agent_response(self, message: str) -> None:
        """Process the agent's response and display it in the conversation."""
        service = AgentService()
        response = service.process_message(message)
        _display_agent_message(response, self.msg_layout)

    def _setup_ui(self) -> None:
        """Build the main window UI components."""
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Conversation display area with welcome message
        chat_container = QWidget()  # Container for message widgets
        self.chat_container = chat_container  # Kept so saved chats can reset it
        chat_scroll = QScrollArea()
        chat_scroll.setWidget(chat_container)
        self.chat_scroll = chat_scroll  # Instance variable reference
        chat_container.setMaximumHeight(350)
        chat_scroll.setWidgetResizable(True)  # Allow scroll area to grow with messages

        msg_layout = QVBoxLayout(chat_container)
        msg_layout.setAlignment(Qt.AlignTop)
        self.msg_layout = msg_layout  # Assign as instance variable

        # Welcome message at the top of the scroll area
        welcome_label = QLabel("Welcome to LUNA — Ask me anything.")
        welcome_label.setStyleSheet("font-weight: bold; color: #3b82f6;")
        msg_layout.addWidget(welcome_label)

        main_layout.addWidget(chat_scroll, stretch=1)

        # Input section layout
        input_section = QHBoxLayout()

        # Status label
        status_label = QLabel("Ready")
        status_label.setStyleSheet(
            "font-weight: bold; color: #4ade80;"
            "background-color: rgba(74, 222, 128, 0.1);"
            "border-radius: 6px; padding: 4px 12px;"
        )

        input_section.addWidget(status_label)

        # Text input field
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Enter your message...")
        self.input_edit.returnPressed.connect(self._on_send_clicked)
        self.input_edit.setMinimumWidth(300)

        input_section.addWidget(self.input_edit, stretch=1)

        # Send button
        send_button = QPushButton("Send")
        send_button.clicked.connect(self._on_send_clicked)
        send_button.setStyleSheet(
            "background-color: #4f46e5;"
            "color: white;"
            "border-radius: 8px; padding: 10px 24px;"
            "font-weight: bold;"
            "min-width: 90px;"
        )

        input_section.addWidget(send_button)

        # Chat history recording button - shows the current recording state
        # ("History: OFF" / "History: ON") and toggles it on each click.
        self.history_button = QPushButton("History: OFF")
        self.history_button.clicked.connect(self._on_history_clicked)
        self._refresh_history_button()

        input_section.addWidget(self.history_button)

        # Mic button (placeholder - does nothing)
        mic_button = QPushButton("Mic (not available yet)")
        mic_button.setStyleSheet(
            "background-color: #f3f4f6; color: #6b7280;"
            "border-radius: 20px;"
            "font-size: 12px;"
            "min-width: 90px;"
        )

        input_section.addWidget(mic_button)

        # Set horizontal alignment for the input section layout
        input_section.setAlignment(Qt.AlignHCenter)

        main_layout.addLayout(input_section, stretch=1)

        # Saved Chats section - lists conversations saved while History was ON
        # (newest first), rebuilds the list on Refresh, and shows the messages
        # of the selected conversation in the chat area above on Open.
        saved_chats_header = QLabel("Saved Chats")
        saved_chats_header.setStyleSheet("font-weight: bold; color: #93c5fd;")
        main_layout.addWidget(saved_chats_header)

        saved_chats_actions = QHBoxLayout()

        self.saved_chats_refresh = QPushButton("Refresh")
        self.saved_chats_refresh.clicked.connect(self._refresh_saved_chats)
        self.saved_chats_refresh.setStyleSheet(
            "background-color: #0ea5e9;"
            "color: white;"
            "border-radius: 8px; padding: 8px 20px;"
            "font-weight: bold;"
            "min-width: 80px;"
        )
        saved_chats_actions.addWidget(self.saved_chats_refresh)

        self.saved_chats_open = QPushButton("Open")
        self.saved_chats_open.clicked.connect(self._open_saved_chat)
        self.saved_chats_open.setStyleSheet(
            "background-color: #7c3aed;"
            "color: white;"
            "border-radius: 8px; padding: 8px 20px;"
            "font-weight: bold;"
            "min-width: 80px;"
        )
        saved_chats_actions.addWidget(self.saved_chats_open)

        # Delete the selected saved conversation after a confirmation prompt
        # (red so it reads as a destructive action next to Open).
        self.saved_chats_delete = QPushButton("Delete")
        self.saved_chats_delete.clicked.connect(self._delete_saved_chat)
        self.saved_chats_delete.setStyleSheet(
            "background-color: #dc2626;"
            "color: white;"
            "border-radius: 8px; padding: 8px 20px;"
            "font-weight: bold;"
            "min-width: 80px;"
        )
        saved_chats_actions.addWidget(self.saved_chats_delete)

        saved_chats_actions.setAlignment(Qt.AlignHCenter)
        main_layout.addLayout(saved_chats_actions)

        self.saved_chats_list = QListWidget()
        self.saved_chats_list.setStyleSheet(
            "QListWidget {"
            "color: #e5e7eb;"
            "spacing: 4px;"
            "background-color: rgba(148, 163, 184, 0.08);"
            "}"
            "QListWidget::item:selected {"
            "background-color: #4f46e5;"
            "color: white;"
            "}"
        )
        self.saved_chats_list.setMinimumHeight(140)
        main_layout.addWidget(self.saved_chats_list)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Show the chats already saved in a previous session, newest first.
        self._refresh_saved_chats()


def _display_user_message(text: str, msg_layout: QVBoxLayout) -> None:
    """Display a user message in the conversation area."""
    msg_label = QLabel(f"User:\n{text}")

    msg_style = (
        "background-color: #3b82f6;"
        "color: white;"
        "border-radius: 12px;"
        "margin: 4px 12px;"
        "padding: 8px 16px;"
        "max-width: 70%;"
    )
    msg_label.setStyleSheet(msg_style)

    msg_layout.addWidget(msg_label)


def _display_agent_message(text: str, msg_layout: QVBoxLayout) -> None:
    """Display an agent message in the conversation area."""
    msg_label = QLabel(f"Agent:\n{text}")

    msg_style = (
        "background-color: #10b981;"
        "color: white;"
        "border-radius: 12px;"
        "margin: 4px 12px;"
        "padding: 8px 16px;"
        "max-width: 70%;"
    )
    msg_label.setStyleSheet(msg_style)

    msg_layout.addWidget(msg_label)
# probe2
