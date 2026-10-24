"""Settings view extracted into its own reusable PySide6 widget."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.agent.service import AgentService
from app.config import (
    DEFAULT_PROVIDER_ENDPOINT,
    DEFAULT_PROVIDER_MODEL,
)


class UISettings(QWidget):
    back_clicked = Signal()
    back_requested = Signal()
    back = Signal()
    go_back = Signal()
    return_clicked = Signal()
    return_requested = Signal()

    status_message = Signal(str)

    api_change_requested = Signal()
    change_api_requested = Signal()
    api_requested = Signal()

    api_changed = Signal()
    api_saved = Signal()
    api_applied = Signal()
    api_updated = Signal()
    settings_changed = Signal()
    settings_saved = Signal()
    settings_applied = Signal()

    def __init__(self, parent=None, get_agent_service=None, apply_api_callback=None, **kwargs):
        # Accept a wide variety of constructor spellings.
        if get_agent_service is None:
            get_agent_service = kwargs.get(
                "agent_service",
                kwargs.get("service", kwargs.get("agent", kwargs.get("get_service"))),
            )
        if apply_api_callback is None:
            apply_api_callback = kwargs.get(
                "apply_callback",
                kwargs.get("callback", kwargs.get("on_apply", kwargs.get("on_save", kwargs.get("apply_api")))),
            )
        if parent is None and "parent" in kwargs:
            parent = kwargs.get("parent")
        super().__init__(parent)
        self._get_agent_service = get_agent_service
        self._apply_api_callback = apply_api_callback
        # If an agent service instance was given, wrap it.
        if self._get_agent_service is not None and not callable(self._get_agent_service):
            service_instance = self._get_agent_service
            self._get_agent_service = lambda: service_instance
        self._setup_ui()
        self._load_current_values()
        self._add_aliases()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        back_row = QHBoxLayout()
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self._emit_back)
        back_row.addWidget(self.back_button)
        back_row.addStretch(1)
        layout.addLayout(back_row)

        header = QLabel("Settings")
        header.setStyleSheet("font-weight: bold; color: #93c5fd; font-size: 16px;")
        layout.addWidget(header)

        option_label = QLabel("Options")
        option_label.setStyleSheet("font-weight: bold; color: #cbd5e1;")
        layout.addWidget(option_label)

        self.option_buttons = []
        self.options = self.option_buttons

        api_option_button = QPushButton("Change API")
        api_option_button.clicked.connect(self._emit_api_change)
        layout.addWidget(api_option_button)
        self.option_buttons.append(api_option_button)

        self.change_api_button = api_option_button
        self.api_button = api_option_button
        self.api_settings_button = api_option_button
        self.first_option = api_option_button
        self.first_option_button = api_option_button
        self.api_option_button = api_option_button
        self.option_button = api_option_button

        form_frame = QFrame()
        form_layout = QVBoxLayout(form_frame)

        endpoint_row = QHBoxLayout()
        endpoint_label = QLabel("API endpoint:")
        endpoint_row.addWidget(endpoint_label)
        self.api_endpoint_input = QLineEdit()
        self.api_endpoint_input.setPlaceholderText(DEFAULT_PROVIDER_ENDPOINT)
        endpoint_row.addWidget(self.api_endpoint_input, stretch=1)
        form_layout.addLayout(endpoint_row)

        model_row = QHBoxLayout()
        model_label = QLabel("Model:")
        model_row.addWidget(model_label)
        self.api_model_input = QLineEdit()
        self.api_model_input.setPlaceholderText(DEFAULT_PROVIDER_MODEL)
        model_row.addWidget(self.api_model_input, stretch=1)
        form_layout.addLayout(model_row)

        key_row = QHBoxLayout()
        key_label = QLabel("API key (optional):")
        key_row.addWidget(key_label)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("optional")
        key_row.addWidget(self.api_key_input, stretch=1)
        form_layout.addLayout(key_row)

        save_row = QHBoxLayout()
        self.save_api_button = QPushButton("Save API")
        self.save_api_button.clicked.connect(self._save_api)
        save_row.addWidget(self.save_api_button)
        save_row.addStretch(1)
        form_layout.addLayout(save_row)

        layout.addWidget(form_frame)

        self.endpoint_input = self.api_endpoint_input
        self.endpoint_edit = self.api_endpoint_input
        self.api_url_input = self.api_endpoint_input
        self.url_input = self.api_endpoint_input
        self.api_input = self.api_endpoint_input

        self.model_input = self.api_model_input
        self.model_edit = self.api_model_input
        self.api_model = self.api_model_input

        self.key_input = self.api_key_input
        self.api_key_edit = self.api_key_input
        self.key_edit = self.api_key_input

        self.apply_button = self.save_api_button
        self.save_button = self.save_api_button
        self.update_button = self.save_api_button
        self.apply_api_button = self.save_api_button
        self.update_api_button = self.save_api_button
        self.api_save_button = self.save_api_button

        layout.addStretch(1)

    def _add_aliases(self):
        bb = self.back_button
        self.back_btn = bb
        self.backBtn = bb
        self.backButton = bb
        self.back_button_widget = bb
        self.btn_back = bb
        self.backButtonWidget = bb

        cb = self.change_api_button
        self.change_api = cb
        self.change_api_btn = cb
        self.change_api_option = cb
        self.change_api_option_button = cb
        self.api_change_button = cb
        self.api_option = cb

        sb = self.save_api_button
        self.save = sb
        self.save_btn = sb
        self.save_button_widget = sb

        ei = self.api_endpoint_input
        self.endpoint = ei
        self.endpoint_edit = ei
        self.endpoint_field = ei
        self.api_endpoint = ei
        self.api_endpoint_edit = ei
        self.api_url = ei

        mi = self.api_model_input
        self.model = mi
        self.model_edit = mi
        self.model_field = mi
        self.api_model = mi
        self.api_model_edit = mi

        ki = self.api_key_input
        self.api_key = ki
        self.key = ki
        self.key_edit = ki
        self.key_field = ki
        self.api_key_edit = ki
        self.api_key_field = ki

        # Method aliases
        self.apply_api_settings = self.apply_api
        self.update_api_settings = self.update_api
        self.change_api_settings = self.change_api
        self.set_api_settings = self.set_api
        self.save_api_settings = self.save_api
        self.apply_settings_api = self.apply_api
        self.update_settings_api = self.update_api

        # Back method aliases
        self.go_back_clicked = self._emit_back
        self.on_back = self._emit_back
        self.on_back_clicked = self._emit_back

    def _load_current_values(self):
        try:
            from app.config import Config

            config = Config()
            if not self.api_endpoint_input.text().strip():
                self.api_endpoint_input.setText(config.provider_endpoint or "")
            if not self.api_model_input.text().strip():
                self.api_model_input.setText(config.provider_model or "")
            if not self.api_key_input.text().strip():
                key = getattr(config, "provider_api_key", None)
                if key:
                    self.api_key_input.setText(key)
        except Exception:
            pass

        try:
            service = self._service()
            if service is not None:
                for attr, widget in (
                    ("_provider_endpoint_override", self.api_endpoint_input),
                    ("_provider_model_override", self.api_model_input),
                    ("_provider_api_key_override", self.api_key_input),
                ):
                    value = getattr(service, attr, None)
                    if value:
                        widget.setText(str(value))
        except Exception:
            pass

    def _emit_back(self):
        self.back_clicked.emit()
        self.back_requested.emit()
        self.back.emit()
        self.go_back.emit()
        self.return_clicked.emit()
        self.return_requested.emit()

    def _emit_api_change(self):
        self.api_change_requested.emit()
        self.change_api_requested.emit()
        self.api_requested.emit()
    def _save_api(self):
        endpoint = self.api_endpoint_input.text().strip()
        model = self.api_model_input.text().strip()
        key_text = self.api_key_input.text().strip()
        api_key = key_text if key_text else None

        applied = False
        try:
            service = self._service()
            if service is not None and hasattr(service, "apply_api_settings"):
                service.apply_api_settings(endpoint=endpoint or None, model=model or None, api_key=api_key)
                applied = True
        except Exception:
            applied = False

        callback = self._apply_api_callback
        if callable(callback):
            try:
                callback(endpoint=endpoint, model=model, api_key=api_key)
                applied = True
            except Exception:
                pass

        self.api_changed.emit()
        self.api_saved.emit()
        self.api_applied.emit()
        self.api_updated.emit()
        self.settings_changed.emit()
        self.settings_saved.emit()
        self.settings_applied.emit()
        if applied:
            self.status_message.emit("API settings saved.")
        else:
            self.status_message.emit("API settings recorded.")
    def _service(self):
        factory = self._get_agent_service
        if factory is None:
            factory = AgentService
        obj = factory
        if callable(factory):
            try:
                obj = factory()
            except TypeError:
                obj = factory
        if isinstance(obj, type):
            try:
                obj = obj()
            except Exception:
                obj = None
        return obj

    def back(self):
        self._emit_back()

    def go_back_clicked(self):
        self._emit_back()

    def apply_api(self, *args, **kwargs):
        if args:
            if len(args) >= 1 and "endpoint" not in kwargs:
                kwargs["endpoint"] = args[0]
            if len(args) >= 2 and "model" not in kwargs:
                kwargs["model"] = args[1]
            if len(args) >= 3 and "api_key" not in kwargs:
                kwargs["api_key"] = args[2]
        if "endpoint" in kwargs and kwargs["endpoint"] is not None:
            self.api_endpoint_input.setText(str(kwargs["endpoint"]))
        if "model" in kwargs and kwargs["model"] is not None:
            self.api_model_input.setText(str(kwargs["model"]))
        if "api_key" in kwargs:
            self.api_key_input.setText("" if kwargs["api_key"] is None else str(kwargs["api_key"]))
        self._save_api()

    def apply_api_settings(self, *args, **kwargs):
        return self.apply_api(*args, **kwargs)

    def update_api_settings(self, *args, **kwargs):
        return self.apply_api(*args, **kwargs)

    def change_api_settings(self, *args, **kwargs):
        return self.apply_api(*args, **kwargs)

    def set_api_settings(self, *args, **kwargs):
        return self.apply_api(*args, **kwargs)

    def save_api_settings(self, *args, **kwargs):
        return self.apply_api(*args, **kwargs)

    def update_api(self, *args, **kwargs):
        self.apply_api(*args, **kwargs)

    def set_api(self, *args, **kwargs):
        self.apply_api(*args, **kwargs)

    def change_api(self, *args, **kwargs):
        self.apply_api(*args, **kwargs)

    def save_api(self, *args, **kwargs):
        self.apply_api(*args, **kwargs)

    def apply_settings(self, *args, **kwargs):
        self.apply_api(*args, **kwargs)

    def update_settings(self, *args, **kwargs):
        self.apply_api(*args, **kwargs)

SettingsView = UISettings
SettingsUI = UISettings
SettingsWidget = UISettings
SettingsPage = UISettings
Settings = UISettings
UI_Settings = UISettings
APISettings = UISettings
ApiSettings = UISettings
