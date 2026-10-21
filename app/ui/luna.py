"""LUNA — Modular Windows desktop AI assistant GUI."""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QMessageBox, QStatusBar,
    QScrollArea,
)
from PySide6.QtCore import Qt
import sys

from app.agent.service import AgentService


class LunaGUI(QMainWindow):
    """Main GUI window for the LUNA application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LUNA")
        self.setMinimumSize(700, 500)
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

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)


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
