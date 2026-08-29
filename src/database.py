import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "biblioteca.db"))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                category TEXT,
                year INTEGER,
                available INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                person TEXT NOT NULL,
                loan_date TEXT NOT NULL,
                return_date TEXT,
                deadline_date TEXT,
                FOREIGN KEY (book_id) REFERENCES books(id)
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                turma TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                username TEXT,
                action TEXT NOT NULL,
                detail TEXT
            );
        """)
        for col in ("deadline_date TEXT", "email TEXT", "notified_at TEXT"):
            try:
                conn.execute(f"ALTER TABLE loans ADD COLUMN {col}")
            except Exception:
                pass

        # Remove coluna órfã de bancos antigos (SQLite >= 3.35 suporta DROP COLUMN)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(loans)").fetchall()]
        if "deadline_days" in cols:
            try:
                conn.execute("ALTER TABLE loans DROP COLUMN deadline_days")
            except Exception:
                pass

        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_loans_book_id ON loans(book_id);
            CREATE INDEX IF NOT EXISTS idx_loans_active ON loans(book_id, return_date);
            CREATE INDEX IF NOT EXISTS idx_loans_overdue ON loans(return_date, deadline_date);
            CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
            CREATE INDEX IF NOT EXISTS idx_books_category ON books(category);
        """)
