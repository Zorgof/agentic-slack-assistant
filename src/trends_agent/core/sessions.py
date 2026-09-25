"""Conversation memory: one SQLite-backed session per conversation (e.g. Slack thread)."""

from pathlib import Path

from agents import SQLiteSession


class SessionStore:
    """Creates Agents SDK sessions stored in a single SQLite file."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, session_id: str) -> SQLiteSession:
        return SQLiteSession(session_id=session_id, db_path=self._db_path)
