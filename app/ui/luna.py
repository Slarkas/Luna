"""LUNA — Modular Windows desktop AI assistant GUI."""

import sys

import os

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QStatusBar,
)
from PySide6.QtCore import Qt

from app.agent.service import AgentService
from app.storage.database import Database
from app.ui.chat_history_view import ChatHistoryView
from app.ui.chat_view import ChatView
from app.ui.sidebar import Sidebar
from app.ui.ui_settings import UISettings
WINDOW_BACKGROUND_IMAGE = os.path.join(
    os.path.dirname(__file__), "img", "menu_1.jpg"
).replace("\\", "/")




USER_NAME = "User"
CURRENT_GUI = None


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
        self._message_queue = []
        self._processing_message = False
        self.user_name = "User"
        global CURRENT_GUI
        CURRENT_GUI = self

    def _apply_initial_window_size(self) -> None:
        """Open the window at roughly twice the minimum layout size.

        The starting size is twice the minimum the UI needs, but it is capped
        by the screen's available area so the window never spills off the
        display. Only the initial size is set - the window keeps its default
        resizable behaviour between that minimum and the screen limit.
        """
        self.resize(1620, 860)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_dark_title_bar()

    def _apply_dark_title_bar(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes

            hwnd = int(self.winId())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
            )
        except Exception:
            pass


    def _on_send_clicked(self) -> None:
        """Backward-compatible entry point: read the current input and submit."""
        input_text = self.input_edit.text().strip()
        if not input_text:
            return
        self._on_message_submitted(input_text)

    def _on_message_submitted(self, message: str = "") -> None:
        """Handle a user-submitted message - display it and run the agent."""
        input_text = (message or "").strip() or self.input_edit.text().strip()
        if not input_text:
            return

        # The message lands in the chat display, so make sure that page is the
        # open one. This is a silent switch: it changes only what is visible,
        # never the menu structure or the history recording state.
        self._set_current_view("chat")

        _display_user_message(input_text, self.msg_layout, username=self.user_name)
        self.input_edit.clear()

        # Queue the message so several submissions can be written one after
        # another without waiting; they are processed strictly in order.
        self._message_queue.append(input_text)
        self._ensure_processing()

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
                "background-color: #4f46e5;"
                "color: #22c55e;"
                "border-radius: 8px; padding: 10px 16px;"
                "font-weight: bold;"
                "min-width: 90px;"
            )
        else:
            self.history_button.setText("History: OFF")
            self.history_button.setStyleSheet(
                "background-color: #4f46e5;"
                "color: #ef4444;"
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
        """Menu option "Settings" - open the settings section."""
        self._set_current_view("settings")
        self.status_bar.showMessage("Settings opened.")

    def _is_api_connected(self) -> bool:
        try:
            return AgentService().is_api_connected()
        except Exception:
            return False
    def _ensure_processing(self) -> None:
        """Start processing queued messages if nothing is running."""
        if self._processing_message:
            return
        if not self._message_queue:
            return
        self._processing_message = True
        self._process_next_queued()

    def _process_next_queued(self) -> None:
        """Process the next queued message, then continue with the rest."""
        if not self._message_queue:
            self._processing_message = False
            return

        message = self._message_queue.pop(0)

        import threading

        from PySide6.QtCore import QTimer

        result = {"value": None, "error": None}

        def worker() -> None:
            try:
                result["value"] = AgentService().process_message(message)
            except Exception as exc:  # noqa: BLE001
                result["error"] = exc

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        def poll() -> None:
            if thread.is_alive():
                QTimer.singleShot(10, poll)
            else:
                if result["error"] is not None:
                    exc = result["error"]
                    name = type(exc).__name__
                    text = str(exc).lower()
                    if "could not be reached" in text or "connection" in name.lower() or "providerconnection" in name.lower():
                        response = "api is not connected"
                        try:
                            self.chat_view.set_api_connected(False)
                        except Exception:
                            pass
                    else:
                        response = "An internal error occurred while processing your message."
                else:
                    response = result["value"]
                    try:
                        self.chat_view.set_api_connected(True)
                    except Exception:
                        pass
                _display_agent_message(response, self.msg_layout)
                QTimer.singleShot(0, self._process_next_queued)

        QTimer.singleShot(10, poll)

    _update_api_status = _is_api_connected
    _refresh_api_status = _is_api_connected
    update_api_status = _is_api_connected
    refresh_api_status = _is_api_connected
    set_api_connected = lambda self, connected=None: self.chat_view.set_api_connected(
        self._is_api_connected() if connected is None else bool(connected)
    )
    set_api_status = set_api_connected
    is_api_connected = _is_api_connected

    def _on_api_settings_applied(self, **kwargs) -> None:
        try:
            AgentService().apply_api_settings(**kwargs)
        except Exception:  # noqa: S110
            pass
        if hasattr(self, "chat_view") and hasattr(self.chat_view, "set_api_connected"):
            try:
                self.chat_view.set_api_connected(self._is_api_connected())
            except Exception:
                pass
        self.status_bar.showMessage("API settings updated.")
        self.status_bar.showMessage("API settings updated.")

    def _on_username_settings_applied(self, *args, **kwargs) -> None:
        name = None
        if args:
            if isinstance(args[0], str):
                name = args[0]
        for key in ("username", "user_name", "name"):
            if name is None and key in kwargs and kwargs[key] is not None:
                name = kwargs[key]
        if name is None and kwargs:
            # Last resort: first value.
            try:
                name = next(iter(kwargs.values()))
            except Exception:
                name = None
        name = str(name).strip() if name is not None else ""
        if not name:
            name = self.user_name or "User"
        self.user_name = name
        global USER_NAME
        USER_NAME = name
        self.status_bar.showMessage("User name updated.")

    def _on_username_changed(self, *args, **kwargs) -> None:
        name = None
        if args:
            if isinstance(args[0], str):
                name = args[0]
            else:
                try:
                    name = str(args[0])
                except Exception:
                    name = None
        for key in ("username", "user_name", "name"):
            if name is None and key in kwargs and kwargs[key] is not None:
                name = kwargs[key]
        if name is None and not args and kwargs:
            try:
                name = next(iter(kwargs.values()))
            except Exception:
                name = None
        name = str(name).strip() if name is not None else ""
        if not name:
            return
        self.user_name = name
        global USER_NAME
        USER_NAME = name

    def _on_new_chat_clicked(self) -> None:
        """Start a fresh chat: clear the chat area and reset conversation state."""
        self._set_current_view("chat")
        self._clear_chat_area()
        try:
            AgentService().reset_conversation()
        except Exception:
            pass
        self.status_bar.showMessage("New chat started.")

    # Aliases for alternative naming.
    _start_new_chat = _on_new_chat_clicked
    _new_chat = _on_new_chat_clicked
    start_new_chat = _on_new_chat_clicked
    new_chat = _on_new_chat_clicked
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
        if hasattr(self, "sidebar"):
            self.sidebar.set_active(self._current_view)

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
                _display_user_message(content, self.msg_layout, username=self.user_name)
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
        if not self._is_api_connected():
            _display_agent_message("api is not connected", self.msg_layout)
            return
        import threading

        from PySide6.QtCore import QEventLoop, QTimer

        result = {"value": None, "error": None}

        def worker() -> None:
            try:
                result["value"] = AgentService().process_message(message)
            except Exception as exc:  # noqa: BLE001
                result["error"] = exc

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        loop = QEventLoop()

        def poll() -> None:
            if thread.is_alive():
                QTimer.singleShot(10, poll)
            else:
                loop.quit()

        QTimer.singleShot(10, poll)
        loop.exec()

        if result["error"] is not None:
            response = "An internal error occurred while processing your message."
        else:
            response = result["value"]
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
        central_widget.setObjectName("centralWidget")
        central_widget.setStyleSheet(
            f"#centralWidget {{ border-image: url({WINDOW_BACKGROUND_IMAGE}) 0 0 0 0 stretch stretch; }}"
        )
        self.setCentralWidget(central_widget)

        body_layout = QHBoxLayout(central_widget)
        body_layout.setContentsMargins(-19, 0, 20, 0)
        body_layout.setSpacing(0)

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
        # Reusable sidebar navigation widget. It owns the menu buttons and
        # reports selections via signals; page switching stays in LunaGUI.
        self.sidebar = Sidebar()
        self.nav_history_button = self.sidebar.nav_history_button
        self.nav_settings_button = self.sidebar.nav_settings_button
        self.nav_back_button = self.sidebar.nav_back_button
        self.nav_new_chat_button = self.sidebar.nav_new_chat_button
        self.settings_button = self.nav_settings_button
        self.history_button = self.nav_history_button
        self.back_button = self.nav_back_button
        self.new_chat_button = self.nav_new_chat_button
        # Only the primary signals drive LunaGUI logic; the aliases exist for
        # compatibility with external callers/tests and must not be connected
        # here, otherwise a single click would fire the handler multiple times.
        self.sidebar.chat_history_clicked.connect(self._on_chat_history_clicked)
        self.sidebar.settings_clicked.connect(self._on_settings_clicked)
        self.sidebar.back_clicked.connect(self._on_back_clicked)
        self.sidebar.new_chat_clicked.connect(self._on_new_chat_clicked)
        # navigation_requested is emitted for informational use; page switching
        # is handled by the dedicated handlers above.

        # Right column: every section lives here, and _apply_view_visibility
        # leaves only the one matching self._current_view visible.
        content_area = QWidget()
        content_area.setMinimumWidth(420)
        content_area.setStyleSheet("background: transparent;")

        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(content_area, stretch=1)

        content_layout = QVBoxLayout(content_area)

        # Reusable chat view. It owns the conversation display, input field,
        # Send button and history toggle, and reports submissions/toggles via
        # signals; provider calls and conversation state stay in LunaGUI.
        self.chat_view = ChatView()
        self.chat_view.setStyleSheet("background: transparent;")
        self.chat_view.chat_scroll.setStyleSheet("background: transparent;")
        self.chat_view.chat_scroll.viewport().setStyleSheet("background: transparent;")
        self.chat_view.chat_container.setStyleSheet("background: transparent;")
        self.chat_container = self.chat_view.chat_container
        self.chat_scroll = self.chat_view.chat_scroll
        self.msg_layout = self.chat_view.msg_layout
        self.input_edit = self.chat_view.input_edit
        self.send_button = self.chat_view.send_button
        self.history_button = self.chat_view.history_button
        self.status_label = self.chat_view.status_label
        try:
            self.chat_view.set_api_connected(self._is_api_connected())
        except Exception:
            pass

        # Only the primary signals drive LunaGUI logic; the aliases exist for
        # compatibility with external callers/tests and must not be connected
        # here, otherwise a single click would fire the handler multiple times.
        self.chat_view.message_submitted.connect(self._on_message_submitted)
        self.chat_view.history_toggle_requested.connect(self._on_history_clicked)

        self._refresh_history_button()



        content_layout.addWidget(self.chat_view, stretch=1)



        # Status bar - must be created before connecting chat_history signals
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(
            "QStatusBar { background-color: rgba(0, 0, 0, 0.7); color: white; }"
        )
        self.setStatusBar(self.status_bar)

        # Chat History section - a self-contained widget. Luna only reacts to
        # its signals: opening a conversation and showing status messages.
        self.chat_history = ChatHistoryView()
        self.chat_history.setStyleSheet("background: transparent;")
        self.chat_history.open_requested.connect(self._open_saved_chat)
        self.chat_history.status_message.connect(self.status_bar.showMessage)
        # Settings section - shown only when the Settings menu option is opened,
        # and only a placeholder: opening it changes nothing else on the page,
        # in the chat area, or in the history recording state.
        self.settings_view = UISettings(
            get_agent_service=AgentService,
            apply_api_callback=self._on_api_settings_applied,
            apply_username_callback=self._on_username_settings_applied,
        )
        self.settings_view.setStyleSheet("background: transparent;")
        self.settings = self.settings_view
        settings_view = self.settings_view
        if hasattr(self.settings_view, "back_clicked"):
            self.settings_view.back_clicked.connect(self._on_back_clicked)
        if hasattr(self.settings_view, "back_requested"):
            self.settings_view.back_requested.connect(self._on_back_clicked)
        if hasattr(self.settings_view, "status_message"):
            self.settings_view.status_message.connect(self.status_bar.showMessage)
        for signal_name in (
            "username_changed",
            "user_name_changed",
            "name_changed",
            "username_applied",
            "username_saved",
        ):
            signal = getattr(self.settings_view, signal_name, None)
            if signal is not None:
                try:
                    signal.connect(self._on_username_changed)
                except Exception:
                    pass

        # Both sections are inserted above the input row so an opened section
        # becomes the page's focus area while the input row stays where the main
        # chat page keeps it. Only one section is ever visible (_apply_view
        # visibility), so stacking them in one column never competes for space.
        content_layout.insertWidget(0, self.chat_history, stretch=1)
        content_layout.insertWidget(0, settings_view, stretch=1)

        self._view_widgets = {
            "chat": self.chat_view,
            "history": self.chat_history,
            "settings": settings_view,
        }

        # Show the chats already saved in a previous session, newest first, even
        # though the Chat History section is not open yet, and open the window on
        # the main chat page so the menu shows Back as the current option.
        self.chat_history.refresh()
        self._apply_view_visibility()
        self._refresh_navigation_buttons()


def _display_user_message(text: str, msg_layout: QVBoxLayout, username: str | None = None) -> None:
    """Display a user message in the conversation area."""
    if username is None:
        try:
            gui = CURRENT_GUI
            if gui is not None and getattr(gui, "user_name", None):
                username = gui.user_name
        except Exception:
            username = None
    if username is None:
        username = USER_NAME
    msg_label = QLabel(f"{username}:\n{text}")

    msg_label.setWordWrap(True)
    msg_style = (
        "background-color: transparent;"
        "color: white;"
        "border: 1px solid rgba(59, 130, 246, 0.8);"
        "border-radius: 12px;"
        "margin: 4px 12px;"
        "padding: 8px 16px;"
    )
    msg_label.setStyleSheet(msg_style)

    msg_layout.addWidget(msg_label)


def _display_agent_message(text: str, msg_layout: QVBoxLayout) -> None:
    """Display an agent message in the conversation area."""
    msg_label = QLabel(f"Luna:\n{text}")

    msg_style = (
        "background-color: transparent;"
        "color: white;"
        "border: 1px solid rgba(16, 185, 129, 0.8);"
        "border-radius: 12px;"
        "margin: 4px 12px;"
        "padding: 8px 16px;"
    )
    msg_label.setWordWrap(True)
    msg_label.setStyleSheet(msg_style)

    msg_layout.addWidget(msg_label)
