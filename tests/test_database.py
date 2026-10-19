
"""Unit tests for Luna's SQLite database module."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.storage.database import Database


class TestDatabase(unittest.TestCase):
    """Tests for database initialization and basic operations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="luna_db_test_")
        self.db_path = Path(self.temp_dir.name) / "test_luna.db"
        self.db = None

    def tearDown(self):
        if self.db is not None:
            self.db.close()
        self.temp_dir.cleanup()

    def get_db(self):
        """Create and initialize an isolated test database."""
        self.db = Database(db_path=self.db_path)
        self.db.initialize()
        return self.db

    def test_initialization_creates_tables(self):
        db = self.get_db()

        self.assertTrue(db.db_path.exists())

        with sqlite3.connect(str(db.db_path)) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

        self.assertIn("conversations", tables)
        self.assertIn("messages", tables)

    def test_foreign_key_constraint_exists(self):
        db = self.get_db()

        with sqlite3.connect(str(db.db_path)) as conn:
            foreign_keys = conn.execute(
                "PRAGMA foreign_key_list(messages)"
            ).fetchall()

        self.assertTrue(
            any(
                row[2] == "conversations"
                and row[3] == "conversation_id"
                and row[6].upper() == "CASCADE"
                for row in foreign_keys
            ),
            "messages must reference conversations with ON DELETE CASCADE",
        )

    def test_create_conversation(self):
        db = self.get_db()

        conversation_id = db.create_conversation("My Test Conversation")

        self.assertIsInstance(conversation_id, int)
        self.assertGreater(conversation_id, 0)

        conversations = db.get_all_conversations()
        self.assertTrue(
            any(item["id"] == conversation_id for item in conversations)
        )

    def test_add_message(self):
        db = self.get_db()
        conversation_id = db.create_conversation("Test Conversation")

        user_message_id = db.add_message(
            conversation_id, "user", "Hello!"
        )
        assistant_message_id = db.add_message(
            conversation_id, "assistant", "Hi there!"
        )

        self.assertIsInstance(user_message_id, int)
        self.assertIsInstance(assistant_message_id, int)
        self.assertGreater(user_message_id, 0)
        self.assertGreater(assistant_message_id, 0)

        with self.assertRaises(sqlite3.IntegrityError):
            db.add_message(999999, "user", "Invalid conversation")

    def test_get_messages_for_conversation(self):
        db = self.get_db()
        conversation_id = db.create_conversation("Test Conversation")

        expected_roles = ["user", "assistant", "user", "assistant"]

        for index, role in enumerate(expected_roles):
            db.add_message(conversation_id, role, f"Message {index}")

        messages = db.get_messages_for_conversation(conversation_id)

        self.assertEqual(len(messages), 4)
        self.assertEqual(
            [message["role"] for message in messages],
            expected_roles,
        )
        self.assertEqual(
            [message["content"] for message in messages],
            [f"Message {index}" for index in range(4)],
        )

    def test_get_all_conversations(self):
        db = self.get_db()
        expected_titles = ["Conv 1", "Conv 2", "Conv 3"]

        for index, title in enumerate(expected_titles):
            conversation_id = db.create_conversation(title)
            db.add_message(conversation_id, "user", f"User message {index}")
            db.add_message(
                conversation_id, "assistant", f"Assistant message {index}"
            )

        conversations = db.get_all_conversations()

        self.assertEqual(len(conversations), 3)
        self.assertEqual(
            {conversation["title"] for conversation in conversations},
            set(expected_titles),
        )

        for conversation in conversations:
            self.assertGreaterEqual(len(conversation["messages"]), 2)

    def test_delete_cascade(self):
        db = self.get_db()
        conversation_id = db.create_conversation("Cascading Test")

        for index in range(5):
            db.add_message(conversation_id, "user", f"Test message {index}")

        # Use the database connection so foreign-key enforcement is enabled.
        connection = db.get_connection()
        connection.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        connection.commit()

        remaining_conversations = connection.execute(
            "SELECT COUNT(*) FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()[0]

        remaining_messages = connection.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()[0]

        self.assertEqual(remaining_conversations, 0)
        self.assertEqual(remaining_messages, 0)


if __name__ == "__main__":
    unittest.main()
