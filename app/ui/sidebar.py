"""Reusable sidebar navigation widget for the LUNA desktop GUI.

The sidebar is a persistent menu column: it owns the navigation option buttons
(Chat History, Settings, Back) and emits Qt signals when one is clicked. Page
switching and any application logic stay with the owner (LunaGUI); this widget
only renders the menu and reports selections.
"""

import os

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap


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
SIDEBAR_IMAGE_NAME = "menu_side_1.jpg"
SIDEBAR_IMAGE_PATH = os.path.join(
    os.path.dirname(__file__), "img", SIDEBAR_IMAGE_NAME
).replace("\\", "/")



SIDEBAR_PANEL_STYLE = (
    "QFrame {"
    f"border-image: url({SIDEBAR_IMAGE_PATH}) 0 0 0 0 stretch stretch;"
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
        self.background_image = SIDEBAR_IMAGE_PATH
        self.background_image_path = SIDEBAR_IMAGE_PATH
        self.background_pixmap = QPixmap(SIDEBAR_IMAGE_PATH)
        self.setMinimumWidth(218)
        self.setMaximumWidth(278)
        self.setStyleSheet(SIDEBAR_PANEL_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        menu_header = QLabel("Menu")
        menu_header.setStyleSheet(
            "QLabel {"
            "background-color: rgba(0, 0, 0, 0.45);"
            "color: #93c5fd;"
            "font-size: 14px;"
            "font-weight: bold;"
            "padding: 10px 18px;"
            "border-top: 1px solid rgba(0, 0, 0, 0.6);"
            "border-left: 1px solid rgba(0, 0, 0, 0.6);"
            "border-right: 1px solid rgba(0, 0, 0, 0.6);"
            "border-bottom: none;"
            "}"
        )
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
