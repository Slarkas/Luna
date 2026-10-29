"""Settings business logic extracted from LunaGUI."""

from __future__ import annotations


class SettingsController:
    """Handles settings-related business logic for the LUNA GUI."""

    def __init__(self, agent_service_factory=None, database_factory=None):
        """Create a controller.

        ``agent_service_factory`` and ``database_factory`` are optional callables.
        When omitted, dependencies are resolved through ``app.ui.luna`` to
        preserve existing behavior.
        """
        self._agent_service_factory = agent_service_factory
        self._database_factory = database_factory

    def _agent_service(self):
        if self._agent_service_factory is not None:
            return self._agent_service_factory()
        from app.agent.service import AgentService

        return AgentService()

    def _database(self):
        if self._database_factory is not None:
            return self._database_factory()
        from app.storage.database import Database

        return Database.get_instance()

    def is_api_connected(self) -> bool:
        """Return whether a model provider is configured and reachable."""
        try:
            return bool(self._agent_service().is_api_connected())
        except Exception:
            return False

    def apply_api_settings(self, **kwargs) -> None:
        """Apply API settings, ignoring failures."""
        try:
            self._agent_service().apply_api_settings(**kwargs)
        except Exception:
            pass

    def normalize_username_for_settings(self, current_name, *args, **kwargs) -> str:
        """Normalize a username coming from settings UI/callbacks."""
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
            name = current_name or "User"
        return name

    def normalize_username_for_change(self, current_name, *args, **kwargs):
        """Normalize a username change, returning None when it is empty."""
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
            return None
        return name

    def persist_user_name(self, name: str) -> None:
        """Persist a user name, never raising."""
        try:
            database = self._database()
            database.initialize()
            if hasattr(database, "set_user_name"):
                database.set_user_name(name)
            elif hasattr(database, "set_setting"):
                database.set_setting("user_name", name)
                database.set_setting("username", name)
        except Exception:
            pass
