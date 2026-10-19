"""LUNA — Modular Windows desktop AI assistant GUI."""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QMessageBox, QStatusBar,
    QScrollArea,
)
from PySide6.QtCore import Qt, Signal
import sys

from app.agent.service import AgentService


class LunaGUI(QMainWindow):
    """Main GUI window for the LUNA application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LUNA")
        self.setMinimumSize(700, 500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initialize the UI layout and components."""
        # Initialize AgentService once in __init__
        self.agent_service = AgentService()

        # Create central widget with main vertical layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Welcome message at the top
        welcome_label = QLabel("Welcome to LUNA — Your AI Assistant")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 20px;"
        )
        main_layout.addWidget(welcome_label)

        # Scrollable conversation area — single ownership chain
        scroll_content = QWidget()
        self.msg_layout = QVBoxLayout(scroll_content)  # layout belongs to content widget

        # Add stretch at bottom of msg_layout so messages accumulate from top
        self.msg_layout.addStretch(1)

        # Create QScrollArea independently (no initial widget yet)
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_scroll.setStyleSheet("background-color: white; border: none;")

        # Attach scroll_content as the widget of chat_scroll exactly once
        self.chat_scroll.setWidget(scroll_content)

        main_layout.addWidget(self.chat_scroll, stretch=1)

        # Input container at the bottom
        input_container = QWidget()
        input_main_layout = QHBoxLayout(input_container)

        # Text input field
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Type your message here...")
        self.input_edit.returnPressed.connect(self._on_send_clicked)
        main_layout.addWidget(input_container, stretch=1)
        input_main_layout.addWidget(self.input_edit)

        # Buttons row below the text field
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.addStretch(1)  # Push buttons to right

        # Send button
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._on_send_clicked)
        self.send_button.setStyleSheet(
            "background-color: #3b82f6; color: white; font-weight: bold;"
        )
        button_layout.addWidget(self.send_button)

        # Microphone placeholder button
        self.mic_button = QPushButton("🎤")
        self.mic_button.clicked.connect(self._on_mic_clicked)
        self.mic_button.setStyleSheet(
            "background-color: #ef4444; color: white; font-weight: bold;"
        )
        button_layout.addWidget(self.mic_button)

        main_layout.addWidget(button_row, stretch=1)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _on_send_clicked(self) -> None:
        """Handle Send button click - submit text to conversation."""
        input_text = self.input_edit.text().strip()
        if not input_text:
            return

        # Display user message
        _display_user_message(input_text, self.msg_layout)
        self._process_agent_response(input_text)
        self.input_edit.clear()

    def _on_mic_clicked(self) -> None:
        """Handle Mic button click - currently a placeholder."""
        pass

    def _process_agent_response(self, message: str) -> None:
        """Process the agent's response and display it in the conversation."""
        self.agent_service.process_message(message)

# Standalone message-display functions (receive QVBoxLayout as argument)


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
