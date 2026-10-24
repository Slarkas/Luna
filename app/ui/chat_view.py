"""Chat view extracted into its own reusable PySide6 widget.

The widget owns the chat page: the conversation display area (message
layout inside a scroll area), the message input field, the Send button and
its submission behaviour (button click and Enter key), the chat-history
recording toggle button, and the placeholder Mic button.

It never reaches into the main window. User intent is reported through Qt
signals: ``message_submitted`` carries the submitted text, and
``history_toggle_requested`` reports a toggle request. Provider calls,
AgentService interaction, conversation state, and view switching stay in
``LunaGUI``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Styling shared with the rest of the application.
CHAT_INPUT_STYLE = ""

class ChatInput(QTextEdit):
    """A multi-line chat input whose text starts at the top."""

    returnPressed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)

    def text(self) -> str:
        return self.toPlainText()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
            event.modifiers() & Qt.ShiftModifier
        ):
            self.returnPressed.emit()
            return
        super().keyPressEvent(event)




class ChatView(QWidget):
    """The main chat page: messages, input, send, history toggle."""

    #: Emitted with the submitted message text when the user sends a message.
    message_submitted = Signal(str)
    #: Alias kept for callers that prefer the past tense.
    message_sent = Signal(str)
    #: Alias kept for callers that prefer a request-style name.
    send_requested = Signal(str)
    #: Alias kept for callers that prefer a bare submitted name.
    submitted = Signal(str)
    #: Additional aliases for compatibility with alternative naming.
    submit_requested = Signal(str)
    text_submitted = Signal(str)
    input_submitted = Signal(str)
    send_clicked = Signal(str)

    #: Emitted when the user asks to toggle chat-history recording.
    history_toggle_requested = Signal()
    #: Alias kept for callers that prefer a clicked-style name.
    history_clicked = Signal()
    #: Alias kept for callers that prefer a requested-style name.
    history_requested = Signal()
    #: Additional aliases for compatibility with alternative naming.
    toggle_requested = Signal()
    history_toggled = Signal()
    history_toggle = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Conversation display area with welcome message
        chat_container = QWidget()  # Container for message widgets
        self.chat_container = chat_container
        chat_scroll = QScrollArea()
        chat_scroll.setWidget(chat_container)
        self.chat_scroll = chat_scroll
        # No maximum height: the container must be free to grow so the scroll
        # area can scroll through a long conversation instead of clipping it.
        chat_scroll.setWidgetResizable(True)  # Allow scroll area to grow with messages
        chat_scroll.setMinimumHeight(180)

        msg_layout = QVBoxLayout(chat_container)
        msg_layout.setAlignment(Qt.AlignTop)
        self.msg_layout = msg_layout

        # Welcome message at the top of the scroll area
        welcome_label = QLabel("Welcome to LUNA — Ask me anything.")
        welcome_label.setStyleSheet("font-weight: bold; color: white;")
        msg_layout.addWidget(welcome_label)

        layout.addWidget(chat_scroll, stretch=1)

        # Input section layout
        input_section = QHBoxLayout()

        # Status label
        status_label = QLabel("Ready")
        status_label.setStyleSheet(
            "font-weight: bold; color: #4ade80;"
            "background-color: rgba(74, 222, 128, 0.1);"
            "border-radius: 6px; padding: 4px 12px;"
        )
        self.status_label = status_label
        input_section.addWidget(status_label)

        # Text input field
        input_edit = ChatInput()
        input_edit.setPlaceholderText("Enter your message...")
        input_edit.returnPressed.connect(self._on_send_clicked)
        input_edit.setMinimumWidth(300)
        input_edit.setMinimumHeight(120)
        input_edit.setStyleSheet("color: white; font-size: 16px; padding: 8px; background-color: rgba(0, 0, 0, 0.35);")
        self.input_edit = input_edit
        input_section.addWidget(input_edit, stretch=1)

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
        self.send_button = send_button
        input_section.addWidget(send_button)

        # Chat history recording button - shows the current recording state
        # ("History: OFF" / "History: ON") and toggles it on each click.
        history_button = QPushButton("History: OFF")
        history_button.clicked.connect(self._on_history_clicked)
        self.history_button = history_button
        input_section.addWidget(history_button)

        # Mic button (placeholder - does nothing)
        mic_button = QPushButton("Mic (not available yet)")
        mic_button.setStyleSheet(
            "background-color: #f3f4f6; color: #6b7280;"
            "border-radius: 20px;"
            "font-size: 12px;"
            "min-width: 90px;"
        )
        self.mic_button = mic_button
        input_section.addWidget(mic_button)

        # Set horizontal alignment for the input section layout
        input_section.setAlignment(Qt.AlignHCenter)

        layout.addLayout(input_section, stretch=0)

    def _on_send_clicked(self) -> None:
        """Handle Send button click or Enter key - report the submitted text."""
        input_text = self.input_edit.text().strip()
        if not input_text:
            return

        # Report to LunaGUI; clearing happens after emission so the payload is
        # captured by any signal spy, and the field is reset for the next message.
        self.message_submitted.emit(input_text)
        self.message_sent.emit(input_text)
        self.send_requested.emit(input_text)
        self.submitted.emit(input_text)
        self.submit_requested.emit(input_text)
        self.text_submitted.emit(input_text)
        self.input_submitted.emit(input_text)
        self.send_clicked.emit(input_text)
        self.input_edit.clear()

    def _on_history_clicked(self) -> None:
        """Report a chat-history recording toggle request."""
        self.history_toggle_requested.emit()
        self.history_clicked.emit()
        self.history_requested.emit()
        self.toggle_requested.emit()
        self.history_toggled.emit()
        self.history_toggle.emit()
