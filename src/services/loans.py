from database import get_db
from datetime import date


def active_loan_count(conn, book_id):
    """Nº de empréstimos ativos (não devolvidos) de um livro."""
    return conn.execute(
        "SELECT COUNT(*) AS c FROM loans WHERE book_id = ? AND return_date IS NULL",
        (book_id,),
    ).fetchone()["c"]


def available_count(book_id):
    """Exemplares disponíveis = copies - empréstimos ativos (nunca < 0)."""
    with get_db() as conn:
        book = conn.execute("SELECT copies FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            raise ValueError("Livro não encontrado")
        return max(0, book["copies"] - active_loan_count(conn, book_id))


def _sync_available(conn, book_id):
    """Reconcilia o booleano legado `available` a partir da contagem de cópias."""
    book = conn.execute("SELECT copies FROM books WHERE id = ?", (book_id,)).fetchone()
    if not book:
        return
    avail = 1 if active_loan_count(conn, book_id) < book["copies"] else 0
    conn.execute("UPDATE books SET available = ? WHERE id = ?", (avail, book_id))


def loan_book(book_id, person, deadline_date=None, email=None):
    with get_db() as conn:
        book = conn.execute("SELECT copies FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            raise ValueError("Livro não encontrado")
        if active_loan_count(conn, book_id) >= book["copies"]:
            raise ValueError("Não há exemplares disponíveis (todas as cópias emprestadas)")
        conn.execute(
            "INSERT INTO loans (book_id, person, loan_date, deadline_date, email) "
            "VALUES (?, ?, ?, ?, ?)",
            (book_id, person, date.today().isoformat(), deadline_date, email or None))
        _sync_available(conn, book_id)


def return_book(book_id):
    """Registra a devolução de UM exemplar do livro.

    Fecha o empréstimo ativo mais antigo (se houver) e reconcilia a
    disponibilidade. Retorna True se havia empréstimo em aberto fechado;
    False se não havia nenhum ativo (estado apenas reconciliado).
    """
    with get_db() as conn:
        loan = conn.execute(
            "SELECT id FROM loans WHERE book_id = ? AND return_date IS NULL "
            "ORDER BY loan_date ASC, id ASC LIMIT 1",
            (book_id,)).fetchone()
        closed = False
        if loan:
            conn.execute("UPDATE loans SET return_date = ? WHERE id = ?",
                         (date.today().isoformat(), loan["id"]))
            closed = True
        _sync_available(conn, book_id)
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


def books_with_status(books=None, category=None, initial=None):
    """Retorna livros anotados com disponibilidade por cópias e empréstimo ativo.

    Agora um livro pode ter VÁRIOS empréstimos ativos (copies > 1). Agregamos
    por livro:
      - active     = nº de empréstimos ativos
      - available_count = copies - active
      - status: "Disponível" (há exemplar livre), "Esgotado" (0 livres) ou
        "Atrasado" (há exemplar livre? não — se algum ativo está vencido e
        não há exemplar livre, marca atraso). Mostramos person/email do
        empréstimo ativo mais recente (referência).

    Filtros no SQL:
      - category: igualdade.
      - initial: inicial do título. "0-9" = começa com dígito; letra = LIKE 'X%'.
    """
    today = date.today().isoformat()
    sql = """
        SELECT b.id, b.code, b.title, b.author, b.category, b.copies,
               COUNT(l.id) AS active,
               SUM(CASE WHEN l.deadline_date IS NOT NULL AND l.deadline_date < ?
                        THEN 1 ELSE 0 END) AS overdue_active,
               MAX(l.loan_date) AS last_loan_date
        FROM books b
        LEFT JOIN loans l
          ON l.book_id = b.id AND l.return_date IS NULL
    """
    params = [today]
    where = []
    if category is not None:
        where.append("b.category = ?")
        params.append(category)
    if initial is not None:
        if initial == "0-9":
            where.append("substr(b.title,1,1) GLOB '[0-9]'")
        else:
            where.append("b.title LIKE ?")
            params.append(f"{initial}%")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " GROUP BY b.id ORDER BY b.title"

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        # pessoa/email do empréstimo ativo mais recente (p/ exibição)
        ref = {}
        if rows:
            ref_rows = conn.execute(
                "SELECT book_id, person, email FROM loans "
                "WHERE return_date IS NULL ORDER BY loan_date ASC, id ASC"
            ).fetchall()
            for rr in ref_rows:
                ref[rr["book_id"]] = (rr["person"] or "", rr["email"] or "")

    result = []
    index = {} if books is not None else None
    for r in rows:
        copies = r["copies"] or 1
        active = r["active"] or 0
        avail = max(0, copies - active)
        if avail > 0:
            status = "Disponível"
        elif r["overdue_active"]:
            status = "Atrasado"
        else:
            status = "Esgotado"
        person, email = ref.get(r["id"], ("", ""))
        item = {
            "id": r["id"], "code": r["code"] or "", "title": r["title"],
            "author": r["author"], "category": r["category"] or "",
            "copies": copies, "available_count": avail, "active": active,
            "copies_label": f"{avail}/{copies}",
            "person": person if active else "", "email": email if active else "",
            "status": status,
        }
        if index is None:
            result.append(item)
        else:
            index[r["id"]] = item

    if index is None:
        return result
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
