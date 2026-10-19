
"""Shared SQLite database for the Luna application."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path


def _get_default_db_path() -> Path:
    """Return Luna's persistent database path on Windows."""
    appdata = os.environ.get("APPDATA")

    if appdata:
        base_path = Path(appdata)
    else:
        # Safe absolute fallback if APPDATA is unavailable.
        base_path = Path.home() / "AppData" / "Roaming"

    return base_path / "Luna" / "luna.db"


_DEFAULT_DB_PATH = _get_default_db_path()


class Database:
    """Shared database connection with basic conversation operations."""

    _instance: Database | None = None
    _instance_lock = threading.Lock()

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = (
            Path(db_path) if db_path is not None else _DEFAULT_DB_PATH
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()
        self._connect()

    def _connect(self) -> None:
        """Open the persistent SQLite connection."""
        connection = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        self._connection = connection

    @classmethod
    def get_instance(cls) -> Database:
        """Return the shared production database instance."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def db_path(self) -> Path:
        """Return the database file path."""
        return self._db_path

    def _require_connection(self) -> sqlite3.Connection:
        """Return the active connection or raise a clear error."""
        if self._connection is None:
            raise RuntimeError(
                "Database connection is closed. Reconnect before use."
            )
        return self._connection

    def initialize(self, create_tables: bool = True) -> None:
        """Create the conversation tables if they do not already exist."""
        with self._lock:
            connection = self._require_connection()

            if create_tables:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id INTEGER NOT NULL,
                        role TEXT NOT NULL
                            CHECK (role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (conversation_id)
                            REFERENCES conversations(id)
                            ON DELETE CASCADE
                            ON UPDATE CASCADE
                    );
                    """
                )

            connection.commit()

    def create_conversation(self, title: str) -> int:
        """Create a conversation and return its ID."""
        if not title or not title.strip():
            raise ValueError("Conversation title cannot be empty.")

        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                "INSERT INTO conversations (title) VALUES (?)",
                (title.strip(),),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
    ) -> int:
        """Add a message and return its ID."""
        if role not in ("user", "assistant"):
            raise ValueError("Role must be 'user' or 'assistant'.")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Message content cannot be empty.")

        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content)
                VALUES (?, ?, ?)
                """,
                (conversation_id, role, content),
            )
            connection.execute(
                """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (conversation_id,),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def get_messages_for_conversation(
        self,
        conversation_id: int,
    ) -> list[dict]:
        """Return a conversation's messages in creation order."""
        with self._lock:
            connection = self._require_connection()
            rows = connection.execute(
                """
                SELECT id, conversation_id, role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                """,
                (conversation_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_conversations(self) -> list[dict]:
        """Return conversations, each including its messages."""
        with self._lock:
            connection = self._require_connection()
            rows = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()

            conversations = []
            for row in rows:
                conversation = dict(row)
                conversation["messages"] = (
                    self.get_messages_for_conversation(conversation["id"])
                )
                conversations.append(conversation)

            return conversations

    def delete_conversation(self, conversation_id: int) -> None:
        """Delete a conversation and its messages."""
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
            )
            connection.commit()

    def get_connection(self) -> sqlite3.Connection:
        """Return the active connection for database queries."""
        return self._require_connection()

    def close(self) -> None:
        """Close the database connection safely."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
