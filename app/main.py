"""Main application entry point for Luna."""

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from app.ui.luna import LunaGUI, WINDOW_ICON_PATH
from app.config import Config, DEFAULT_APP_NAME
import sys

def main() -> None:
    """Start the Luna application."""
    config = Config()
    print(f"Luna starting with configuration: name={config.name}, log_level={config.log_level}")

    # Launch the PySide6 GUI window
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(WINDOW_ICON_PATH))
    gui = LunaGUI()
    gui.show()
    sys.exit(app.exec())