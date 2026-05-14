"""
database.py
-----------
DatabaseService: a tiny SQLite wrapper for AI Legal Shield.

All six required tables are created from zero on startup:
  users, uploaded_documents, document_chunks, questions, agent_runs, final_answers

No ORM, no migrations — just plain sqlite3 so it stays hackathon-simple.
"""

import re
import sqlite3
from datetime import datetime


class DatabaseService:
    def __init__(self, db_path):
        self.db_path = db_path

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def init(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id          TEXT PRIMARY KEY,
                    name        TEXT,
                    created_at  TEXT
                );

                CREATE TABLE IF NOT EXISTS uploaded_documents (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT,
                    filename    TEXT,
                    file_path   TEXT,
                    created_at  TEXT
                );

                CREATE TABLE IF NOT EXISTS document_chunks (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id  INTEGER,
                    chunk_index  INTEGER,
                    chunk_text   TEXT,
                    created_at   TEXT
                );

                CREATE TABLE IF NOT EXISTS questions (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id        TEXT,
                    question_text  TEXT,
                    mode           TEXT,
                    created_at     TEXT
                );

                CREATE TABLE IF NOT EXISTS agent_runs (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id       INTEGER,
                    agent_name        TEXT,
                    phase             TEXT,
                    iteration_number  INTEGER,
                    input_text        TEXT,
                    output_text       TEXT,
                    approved          INTEGER,
                    emergency_used    INTEGER,
                    created_at        TEXT
                );

                CREATE TABLE IF NOT EXISTS final_answers (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id        INTEGER,
                    final_answer       TEXT,
                    disclaimer         TEXT,
                    unresolved_issues  TEXT,
                    created_at         TEXT
                );
                """
            )

    @staticmethod
    def _now():
        return datetime.utcnow().isoformat(timespec="seconds")

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    def create_user(self, user_id, name):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (id, name, created_at) VALUES (?, ?, ?)",
                (user_id, name, self._now()),
            )

    # ------------------------------------------------------------------
    # Documents + chunks (RAG storage)
    # ------------------------------------------------------------------
    def add_document(self, user_id, filename, file_path):
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO uploaded_documents (user_id, filename, file_path, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, filename, file_path, self._now()),
            )
            return cur.lastrowid

    def add_chunk(self, document_id, chunk_index, chunk_text):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO document_chunks (document_id, chunk_index, chunk_text, created_at) "
                "VALUES (?, ?, ?, ?)",
                (document_id, chunk_index, chunk_text, self._now()),
            )

    def search_chunks(self, query, limit=5):
        """
        Very simple keyword-based RAG search (no vector DB needed for an MVP).
        Scores each stored chunk by how many query keywords it contains and
        returns the top `limit` chunk texts.
        """
        keywords = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        if not keywords:
            return []
        with self._connect() as conn:
            rows = conn.execute("SELECT chunk_text FROM document_chunks").fetchall()

        scored = []
        for row in rows:
            text = row["chunk_text"] or ""
            lowered = text.lower()
            score = sum(lowered.count(word) for word in keywords)
            if score > 0:
                scored.append((score, text))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [text for _, text in scored[:limit]]

    # ------------------------------------------------------------------
    # Questions
    # ------------------------------------------------------------------
    def add_question(self, user_id, question_text, mode):
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO questions (user_id, question_text, mode, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, question_text, mode, self._now()),
            )
            return cur.lastrowid

    # ------------------------------------------------------------------
    # Agent runs (one row per visible trace step)
    # ------------------------------------------------------------------
    def add_agent_run(self, question_id, agent_name, phase, iteration_number,
                      input_text, output_text, approved, emergency_used):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO agent_runs (question_id, agent_name, phase, "
                "iteration_number, input_text, output_text, approved, "
                "emergency_used, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    question_id,
                    agent_name,
                    phase,
                    iteration_number,
                    input_text,
                    output_text,
                    None if approved is None else int(bool(approved)),
                    int(bool(emergency_used)),
                    self._now(),
                ),
            )

    # ------------------------------------------------------------------
    # Final answers
    # ------------------------------------------------------------------
    def add_final_answer(self, question_id, final_answer, disclaimer, unresolved_issues):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO final_answers (question_id, final_answer, disclaimer, "
                "unresolved_issues, created_at) VALUES (?, ?, ?, ?, ?)",
                (question_id, final_answer, disclaimer, unresolved_issues, self._now()),
            )

    # ------------------------------------------------------------------
    # History (joins questions + their final answers)
    # ------------------------------------------------------------------
    def get_history(self, user_id, limit=20):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT q.id            AS question_id,
                       q.question_text AS question,
                       q.mode          AS mode,
                       q.created_at    AS created_at,
                       f.final_answer  AS final_answer,
                       f.unresolved_issues AS unresolved_issues
                FROM questions q
                LEFT JOIN final_answers f ON f.question_id = q.id
                WHERE q.user_id = ?
                ORDER BY q.id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
