"""Reusable sidebar navigation widget for the LUNA desktop GUI.

The sidebar is a persistent menu column: it owns the navigation option buttons
(Chat History, Settings, Back) and emits Qt signals when one is clicked. Page
switching and any application logic stay with the owner (LunaGUI); this widget
only renders the menu and reports selections.
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal


NAV_ACTIVE_STYLE = (
    "background-color: #4f46e5;"
    "color: white;"
    "border-radius: 8px; padding: 10px 18px;"
    "font-weight: bold;"
    "min-width: 110px;"
)
NAV_INACTIVE_STYLE = (
    "background-color: #475569;"
    "color: #e2e8f0;"
    "border-radius: 8px; padding: 10px 18px;"
    "font-weight: bold;"
    "min-width: 110px;"
)

SIDEBAR_PANEL_STYLE = (
    "QFrame {"
    "background-color: #1b1f27;"
    "border-right: 1px solid #3b424f;"
    "}"
)

MENU_HEADER_STYLE = (
    "QLabel {"
    "font-size: 14px;"
    "font-weight: bold;"
    "color: #93c5fd;"
    "padding-bottom: 6px;"
    "border-bottom: 1px solid #3b424f;"
    "}"
)


class Sidebar(QFrame):
    chat_history_clicked = Signal()
    chat_history_requested = Signal()

    settings_clicked = Signal()
    settings_requested = Signal()

    back_clicked = Signal()
    back_requested = Signal()
    new_chat_clicked = Signal()
    new_chat_requested = Signal()

    navigation_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setMaximumWidth(240)
        self.setStyleSheet(SIDEBAR_PANEL_STYLE)

        layout = QVBoxLayout(self)

        menu_header = QLabel("Menu")
        menu_header.setStyleSheet(MENU_HEADER_STYLE)
        layout.addWidget(menu_header)

        self.nav_history_button = QPushButton("Chat History")
        self.nav_history_button.setStyleSheet(NAV_INACTIVE_STYLE)
        self.nav_history_button.clicked.connect(self._emit_chat_history)
        layout.addWidget(self.nav_history_button)

        self.nav_settings_button = QPushButton("Settings")
        self.nav_settings_button.setStyleSheet(NAV_INACTIVE_STYLE)
        self.nav_settings_button.clicked.connect(self._emit_settings)
        layout.addWidget(self.nav_settings_button)

        self.nav_back_button = QPushButton("Back")
        self.nav_back_button.setStyleSheet(NAV_ACTIVE_STYLE)
        self.nav_back_button.clicked.connect(self._emit_back)
        layout.addWidget(self.nav_back_button)

        self.chat_history_button = self.nav_history_button
        self.history_button = self.nav_history_button
        self.settings_button = self.nav_settings_button
        self.back_button = self.nav_back_button
        self.new_chat_button = self.nav_back_button

    def _emit_chat_history(self) -> None:
        self.chat_history_clicked.emit()
        self.chat_history_requested.emit()
        self.navigation_requested.emit("history")

    def _emit_settings(self) -> None:
        self.settings_clicked.emit()
        self.settings_requested.emit()
        self.navigation_requested.emit("settings")

    def _emit_back(self) -> None:
        self.back_clicked.emit()
        self.back_requested.emit()
        self.new_chat_clicked.emit()
        self.new_chat_requested.emit()
        self.navigation_requested.emit("chat")

    def set_active(self, view: str) -> None:
        self.nav_history_button.setStyleSheet(
            NAV_ACTIVE_STYLE if view == "history" else NAV_INACTIVE_STYLE
        )
        self.nav_settings_button.setStyleSheet(
            NAV_ACTIVE_STYLE if view == "settings" else NAV_INACTIVE_STYLE
        )
        self.nav_back_button.setStyleSheet(
            NAV_ACTIVE_STYLE if view == "chat" else NAV_INACTIVE_STYLE
        )

    def refresh_active(self, view: str) -> None:
        self.set_active(view)
