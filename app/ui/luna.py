"""LUNA — Modular Windows desktop AI assistant GUI."""

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QStatusBar,
    QScrollArea, QFrame,
)
from PySide6.QtCore import Qt
import sys

from app.agent.service import AgentService
from app.storage.database import Database
from app.ui.chat_history_view import ChatHistoryView

# Sidebar navigation styling. Exactly one menu option carries the filled indigo
# look (the same accent used elsewhere for the active state): the option that
# owns the section currently open in the content area, or "Back" while the main
# chat page is showing. The other options stay muted slate so they read as
# clickable but not current, and the active look is what tells the user which
# page they are on without hiding the menu itself.
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

# The menu column is drawn as a panel so it reads as a menu rather than as three
# buttons floating on the page background: the panel is a shade lighter than the
# window and is closed off on the edge that faces the content area. QFrame (not
# QWidget) is what makes these two properties paint - a plain QWidget container
# ignores them - and the border is only ever drawn on the one facing edge, never
# as a four sided box around the column.
SIDEBAR_PANEL_STYLE = (
    "QFrame {"
    "background-color: #1b1f27;"
    "border-right: 1px solid #3b424f;"
    "}"
)

# Header label above the options: it names the column so the eye reads a menu
# (Menu / Chat History / Settings / Back) top down instead of loose buttons, and
# the hairline under it separates the heading from the options it introduces.
MENU_HEADER_STYLE = (
    "QLabel {"
    "font-size: 14px;"
    "font-weight: bold;"
    "color: #93c5fd;"
    "padding-bottom: 6px;"
    "border-bottom: 1px solid #3b424f;"
    "}"
)


class LunaGUI(QMainWindow):
    """Main GUI window for the LUNA application."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LUNA")
        self.setMinimumSize(700, 500)
        self._apply_initial_window_size()

        # Chat history recording is opt-in and always starts OFF for a new
        # application session.
        self._history_recording: bool = False
        AgentService().disable_history_recording()

        # Which section the content area is showing. The sidebar menu is always
        # visible; only the content it points at changes, and a new session
        # starts on the main chat page rather than inside a menu section.
        self._current_view: str = "chat"

        self._setup_ui()

    def _apply_initial_window_size(self) -> None:
        """Open the window at roughly twice the minimum layout size.

        The starting size is twice the minimum the UI needs, but it is capped
        by the screen's available area so the window never spills off the
        display. Only the initial size is set - the window keeps its default
        resizable behaviour between that minimum and the screen limit.
        """
        minimum_width = self.minimumSize().width()
        minimum_height = self.minimumSize().height()

        initial_width = minimum_width * 2
        initial_height = minimum_height * 2

        screen = self.screen()
        if screen is not None:
            available = screen.availableSize()
            if available.width() > 0 and available.height() > 0:
                initial_width = min(initial_width, available.width())
                initial_height = min(initial_height, available.height())

        self.resize(
            max(initial_width, minimum_width),
            max(initial_height, minimum_height),
        )

    def _on_send_clicked(self) -> None:
        """Handle Send button click - submit text to conversation."""
        input_text = self.input_edit.text().strip()
        if not input_text:
            return

        # The message lands in the chat display, so make sure that page is the
        # open one. This is a silent switch: it changes only what is visible,
        # never the menu structure or the history recording state.
        self._set_current_view("chat")

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
    # Sidebar navigation
    #
    # The left sidebar is a persistent menu, so clicking an option only decides
    # which section the content area shows: the main chat page, the Chat History
    # section, or the Settings placeholder. Switching sections never reads or
    # writes the database, never touches the history recording flag or its
    # button, and never clears the messages already shown in the chat area -
    # leaving a section is purely a view change.
    # ------------------------------------------------------------------

    def _on_chat_history_clicked(self) -> None:
        """Menu option "Chat History" - open the saved-chat history section."""
        self._set_current_view("history")
        self.status_bar.showMessage(
            "Chat History opened - select the rows to act on, then use "
            "Refresh, Open or Delete Selected."
        )

    def _on_settings_clicked(self) -> None:
        """Menu option "Settings" - open the placeholder section."""
        self._set_current_view("settings")
        self.status_bar.showMessage(
            "Settings opened - no settings are configurable yet."
        )

    def _on_back_clicked(self) -> None:
        """Leave the open section and return to the main chat page."""
        self._set_current_view("chat")
        self.status_bar.showMessage("Back on the main chat page.")

    def _set_current_view(self, view: str) -> None:
        """Show one content section at a time and mark its menu option active."""
        if view not in self._view_widgets:
            return

        self._current_view = view
        self._apply_view_visibility()
        self._refresh_navigation_buttons()

    def _apply_view_visibility(self) -> None:
        """Leave only the current section visible; the others stay built.

        Hiding a section (instead of removing it) keeps its list selection, its
        buttons and the chat area's messages intact, so going Back to the main
        page or re-opening Chat History never loses state.
        """
        for view, widget in self._view_widgets.items():
            widget.setVisible(view == self._current_view)

    def _refresh_navigation_buttons(self) -> None:
        """Mark the menu option that owns the page currently showing."""
        self.nav_history_button.setStyleSheet(
            NAV_ACTIVE_STYLE if self._current_view == "history"
            else NAV_INACTIVE_STYLE
        )
        self.nav_settings_button.setStyleSheet(
            NAV_ACTIVE_STYLE if self._current_view == "settings"
            else NAV_INACTIVE_STYLE
        )
        self.nav_back_button.setStyleSheet(
            NAV_ACTIVE_STYLE if self._current_view == "chat"
            else NAV_INACTIVE_STYLE
        )

    # ------------------------------------------------------------------
    # Saved chats
    #
    # History: ON is what writes conversations into the shared database, so the
    # saved chats are exactly those records. Reading them is independent of the
    # recording flag: the list can be shown (and a chat opened) while recording
    # is off, and a database that cannot be reached never breaks the GUI.
    # ------------------------------------------------------------------

    def _open_saved_chat(self, conversation: dict) -> None:
        """Show one saved conversation from the history widget on the chat page.

        Opening happens from the Chat History section, but the conversation
        itself is displayed on the main chat page, so switch the content area
        back first. No provider request or database write is involved: the
        conversation record already carries its messages.
        """
        self._set_current_view("chat")

        self._clear_chat_area()

        conversation_id = conversation.get("id")
        title = str(conversation.get("title") or "Untitled").strip()
        header = QLabel(f"Saved chat: {title} (#{conversation_id})")
        header.setStyleSheet("font-weight: bold; color: #3b82f6;")
        self.msg_layout.addWidget(header)

        messages = conversation.get("messages") or self._saved_messages(
            conversation_id
        )
        for message in messages:
            content = str(message.get("content", ""))
            if message.get("role") == "user":
                _display_user_message(content, self.msg_layout)
            else:
                _display_agent_message(content, self.msg_layout)

        self.status_bar.showMessage(
            f"Opened saved chat #{conversation_id} ({len(messages)} messages)"
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
        # Central widget split into two columns: a persistent navigation sidebar
        # on the left and the content area on the right. The sidebar carries the
        # menu options and is never swapped out or hidden, so the menu is
        # reachable from any page; the content area shows one section at a time
        # (the chat display, the Chat History section, or the Settings
        # placeholder), and switching sections never rebuilds any of them.
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        body_layout = QHBoxLayout(central_widget)
        body_layout.setContentsMargins(20, 20, 20, 20)

        # Left column: the menu. It stays a narrow column so the content area
        # always keeps most of the window.
        #
        # The menu band is constrained instead of pinned to one width: any fixed
        # pixel width competes with the content area for space, so a too-wide
        # menu pushed the chat/input row out of the window and off the display at
        # the default 80% UI scaling (which is what made the window look blank
        # with the input row missing). 180 is the narrowest usable menu, 240 is
        # the widest it may ever take, and the content area absorbs the rest of
        # the window, so the menu always renders as a slim left column.
        #
        # QFrame (not QWidget) so the menu panel and its right edge line are
        # painted at all: a plain QWidget container ignores them. The two
        # properties are kept apart so the line only closes the side that faces
        # the content area and never boxes the whole column.
        sidebar = QFrame()
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(240)
        sidebar.setStyleSheet(SIDEBAR_PANEL_STYLE)
        sidebar_layout = QVBoxLayout(sidebar)

        # Right column: every section lives here, and _apply_view_visibility
        # leaves only the one matching self._current_view visible.
        content_area = QWidget()
        content_area.setMinimumWidth(420)

        body_layout.addWidget(sidebar)
        body_layout.addWidget(content_area, stretch=1)

        content_layout = QVBoxLayout(content_area)

        # Menu header plus the options. Chat History and Settings open a section
        # in the content area; Back leaves the menu as it is and returns to the
        # main chat page.
        menu_header = QLabel("Menu")
        menu_header.setStyleSheet(MENU_HEADER_STYLE)
        sidebar_layout.addWidget(menu_header)

        self.nav_history_button = QPushButton("Chat History")
        self.nav_history_button.clicked.connect(self._on_chat_history_clicked)
        self.nav_history_button.setStyleSheet(NAV_INACTIVE_STYLE)
        sidebar_layout.addWidget(self.nav_history_button)

        self.nav_settings_button = QPushButton("Settings")
        self.nav_settings_button.clicked.connect(self._on_settings_clicked)
        self.nav_settings_button.setStyleSheet(NAV_INACTIVE_STYLE)
        sidebar_layout.addWidget(self.nav_settings_button)

        # Back is the way out of a section: it changes only which section the
        # content area shows, never what the menu looks like structurally.
        self.nav_back_button = QPushButton("Back")
        self.nav_back_button.clicked.connect(self._on_back_clicked)
        self.nav_back_button.setStyleSheet(NAV_ACTIVE_STYLE)
        sidebar_layout.addWidget(self.nav_back_button)

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

        content_layout.addWidget(chat_scroll, stretch=1)

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

        content_layout.addLayout(input_section, stretch=1)

        # Status bar - must be created before connecting chat_history signals
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Chat History section - a self-contained widget. Luna only reacts to
        # its signals: opening a conversation and showing status messages.
        self.chat_history = ChatHistoryView()
        self.chat_history.open_requested.connect(self._open_saved_chat)
        self.chat_history.status_message.connect(self.status_bar.showMessage)
        content_layout.insertWidget(0, self.chat_history, stretch=1)

        # Settings section - shown only when the Settings menu option is opened,
        # and only a placeholder: opening it changes nothing else on the page,
        # in the chat area, or in the history recording state.
        settings_view = QWidget()
        self.settings_view = settings_view
        settings_layout = QVBoxLayout(settings_view)
        settings_layout.setAlignment(Qt.AlignTop)

        settings_header = QLabel("Settings")
        settings_header.setStyleSheet("font-weight: bold; color: #93c5fd;")
        settings_layout.addWidget(settings_header)

        settings_placeholder = QLabel(
            "Settings are not available yet - this option is a placeholder "
            "only, so opening it changes nothing."
        )
        settings_placeholder.setStyleSheet("color: #94a3b8;")
        settings_placeholder.setWordWrap(True)
        settings_layout.addWidget(settings_placeholder)

        # Both sections are inserted above the input row so an opened section
        # becomes the page's focus area while the input row stays where the main
        # chat page keeps it. Only one section is ever visible (_apply_view
        # visibility), so stacking them in one column never competes for space.
        content_layout.insertWidget(0, self.chat_history, stretch=1)
        content_layout.insertWidget(0, settings_view, stretch=1)

        self._view_widgets = {
            "chat": chat_scroll,
            "history": self.chat_history,
            "settings": settings_view,
        }

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Show the chats already saved in a previous session, newest first, even
        # though the Chat History section is not open yet, and open the window on
        # the main chat page so the menu shows Back as the current option.
        self.chat_history.refresh()
        self._apply_view_visibility()
        self._refresh_navigation_buttons()


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
    msg_label = QLabel(f"Luna:\n{text}")

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
