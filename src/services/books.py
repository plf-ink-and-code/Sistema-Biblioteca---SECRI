from database import get_db


def add_book(title, author, category=None, year=None, code=None, copies=1):
    try:
        copies = int(copies or 1)
    except (TypeError, ValueError):
        copies = 1
    if copies < 1:
        copies = 1
    with get_db() as conn:
        conn.execute(
            "INSERT INTO books (title, author, category, year, code, copies) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, author, category or None, year or None, code or None, copies))


def remove_book(book_id):
    with get_db() as conn:
        conn.execute("DELETE FROM loans WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM books WHERE id = ?", (book_id,))


def edit_book(book_id, title, author, category=None, year=None, code=None, copies=None):
    with get_db() as conn:
        if copies is None:
            conn.execute(
                "UPDATE books SET title=?, author=?, category=?, year=?, code=? WHERE id=?",
                (title, author, category or None, year or None, code or None, book_id))
        else:
            try:
                copies = int(copies)
            except (TypeError, ValueError):
                copies = 1
            if copies < 1:
                copies = 1
            conn.execute(
                "UPDATE books SET title=?, author=?, category=?, year=?, code=?, copies=? "
                "WHERE id=?",
                (title, author, category or None, year or None, code or None, copies, book_id))


def get_book(book_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return dict(row) if row else None


def list_books():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM books ORDER BY title").fetchall()
        return [dict(r) for r in rows]


def list_by_initial(initial):
    """Lista livros cujo TÍTULO começa com a inicial dada.

    - "0-9": títulos que começam com dígito.
    - letra (A..Z): case-insensitive (SQLite LIKE já é case-insensitive p/ ASCII).
    """
    with get_db() as conn:
        if initial == "0-9":
            rows = conn.execute(
                "SELECT * FROM books WHERE substr(title,1,1) GLOB '[0-9]' ORDER BY title"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM books WHERE title LIKE ? ORDER BY title", (f"{initial}%",)
            ).fetchall()
        return [dict(r) for r in rows]


def search_books(term):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR category LIKE ? ORDER BY title",
                            (f"%{term}%", f"%{term}%", f"%{term}%")).fetchall()
        return [dict(r) for r in rows]


def filter_by_category(category):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM books WHERE category = ? ORDER BY title", (category,)).fetchall()
        return [dict(r) for r in rows]


def list_categories():
    with get_db() as conn:
        rows = conn.execute("SELECT DISTINCT category FROM books WHERE category IS NOT NULL ORDER BY category").fetchall()
        return [r["category"] for r in rows]
