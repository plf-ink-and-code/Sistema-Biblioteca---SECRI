from database import get_db
from datetime import date


def loan_book(book_id, person, deadline_date=None, email=None):
    with get_db() as conn:
        book = conn.execute("SELECT available FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            raise ValueError("Livro não encontrado")
        if not book["available"]:
            raise ValueError("Livro já está alugado")
        conn.execute("INSERT INTO loans (book_id, person, loan_date, deadline_date, email) VALUES (?, ?, ?, ?, ?)",
                     (book_id, person, date.today().isoformat(), deadline_date, email or None))
        conn.execute("UPDATE books SET available = 0 WHERE id = ?", (book_id,))


def return_book(book_id):
    """Registra a devolução de um livro.

    Fecha o empréstimo ativo (se houver) e marca o livro como disponível.
    Retorna True se havia um empréstimo em aberto que foi fechado; False se o
    livro já estava disponível (nenhum empréstimo ativo) — nesse caso o estado
    do livro é apenas reconciliado para `available = 1`, sem falhar.
    """
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE loans SET return_date = ? WHERE book_id = ? AND return_date IS NULL",
            (date.today().isoformat(), book_id))
        closed = cur.rowcount > 0
        conn.execute("UPDATE books SET available = 1 WHERE id = ?", (book_id,))
    return closed


def loan_history(book_id):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM loans WHERE book_id = ? ORDER BY loan_date DESC", (book_id,)).fetchall()
        return [dict(r) for r in rows]


def active_loan(book_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM loans WHERE book_id = ? AND return_date IS NULL", (book_id,)).fetchone()
        return dict(row) if row else None


def is_overdue(book_id):
    loan = active_loan(book_id)
    if not loan or not loan.get("deadline_date"):
        return False
    return date.today() > date.fromisoformat(loan["deadline_date"])


def renew_loan(book_id, new_deadline_date):
    with get_db() as conn:
        loan = conn.execute("SELECT id FROM loans WHERE book_id=? AND return_date IS NULL",
                            (book_id,)).fetchone()
        if not loan:
            raise ValueError("Nenhum empréstimo ativo para este livro")
        conn.execute("UPDATE loans SET deadline_date=?, notified_at=NULL WHERE id=?",
                     (new_deadline_date, loan["id"]))


def overdue_loans():
    with get_db() as conn:
        rows = conn.execute("""SELECT l.*, b.title FROM loans l JOIN books b ON l.book_id = b.id
            WHERE l.return_date IS NULL AND l.deadline_date IS NOT NULL AND l.deadline_date < ?""",
            (date.today().isoformat(),)).fetchall()
        return [dict(r) for r in rows]


def books_with_status(books=None, category=None):
    """Retorna livros já anotados com person/email/status do empréstimo ativo.

    Faz um único JOIN (books LEFT JOIN empréstimo ativo) em vez de uma query
    por linha, eliminando o N+1 que travava o event loop no refresh da UI.

    - `category`: filtra no próprio SQL (evita escanear a tabela inteira).
    - `books`: lista já filtrada (ex.: resultado de busca); usa esses ids.
      Se ambos forem None, retorna todos.
    """
    today = date.today().isoformat()
    sql = """
        SELECT b.id, b.code, b.title, b.author, b.category, b.available,
               l.person AS loan_person, l.email AS loan_email,
               l.deadline_date AS loan_deadline
        FROM books b
        LEFT JOIN loans l
          ON l.book_id = b.id AND l.return_date IS NULL
    """
    params = ()
    if category is not None:
        sql += " WHERE b.category = ?"
        params = (category,)
    sql += " ORDER BY b.title"

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()

    result = []
    index = {} if books is not None else None
    for r in rows:
        if r["available"]:
            status, person, email = "Disponível", "", ""
        else:
            deadline = r["loan_deadline"]
            status = "Atrasado" if (deadline and today > deadline) else "Alugado"
            person = r["loan_person"] or ""
            email = r["loan_email"] or ""
        item = {
            "id": r["id"], "code": r["code"] or "", "title": r["title"],
            "author": r["author"], "category": r["category"] or "",
            "person": person, "email": email, "status": status,
        }
        if index is None:
            result.append(item)
        else:
            index[r["id"]] = item

    if index is None:
        return result
    # Preserva a ordem/filtro da lista recebida
    return [index[b["id"]] for b in books if b["id"] in index]


def top_loaned_books(limit=10):
    with get_db() as conn:
        rows = conn.execute("""SELECT b.title, b.author, COUNT(l.id) as total
            FROM loans l JOIN books b ON l.book_id = b.id
            GROUP BY l.book_id ORDER BY total DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]


def top_borrowers(limit=10):
    with get_db() as conn:
        rows = conn.execute("""SELECT person, COUNT(id) as total
            FROM loans GROUP BY person ORDER BY total DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]
