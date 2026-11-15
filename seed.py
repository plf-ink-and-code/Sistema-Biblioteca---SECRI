from database import init_db, get_connection
from datetime import date, timedelta
import json
import os
import random

# Caminho do JSON gerado a partir dos PDFs (tools/extract_books.py + enrich_web.py).
# Pode ser sobrescrito pela variável de ambiente BOOKS_JSON.
BOOKS_JSON = os.environ.get(
    "BOOKS_JSON",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "livros.json"),
)


def load_books(path=BOOKS_JSON):
    """Lê livros.json e devolve lista de tuplas (title, author, category, year, copies).

    O schema de `books` exige author NOT NULL; quando o JSON traz author nulo,
    usamos 'Autor desconhecido'. category e year aceitam NULL (ficam None).
    copies: total de exemplares (default 1).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    books = []
    for b in data:
        title = (b.get("title") or "").strip()
        if not title:
            continue  # título é obrigatório
        author = (b.get("author") or "").strip() or "Autor desconhecido"
        category = (b.get("category") or "").strip() or None
        year = b.get("year")  # int ou None
        try:
            copies = int(b.get("copies") or 1)
        except (TypeError, ValueError):
            copies = 1
        if copies < 1:
            copies = 1
        books.append((title, author, category, year, copies))
    return books



PEOPLE = [
    ("Ana Silva", "ana.silva@edu.ufes.br"),
    ("Carlos Oliveira", "carlos.oliveira@edu.ufes.br"),
    ("Maria Santos", "maria.santos@edu.ufes.br"),
    ("Joao Pereira", "joao.pereira@edu.ufes.br"),
    ("Fernanda Costa", "fernanda.costa@edu.ufes.br"),
    ("Pedro Souza", "pedro.souza@edu.ufes.br"),
    ("Juliana Lima", "juliana.lima@edu.ufes.br"),
    ("Rafael Almeida", "rafael.almeida@edu.ufes.br"),
    ("Beatriz Ferreira", "beatriz.ferreira@edu.ufes.br"),
    ("Lucas Rodrigues", "lucas.rodrigues@edu.ufes.br"),
    ("Camila Martins", "camila.martins@edu.ufes.br"),
    ("Bruno Araujo", "bruno.araujo@edu.ufes.br"),
    ("Larissa Gomes", "larissa.gomes@edu.ufes.br"),
    ("Thiago Ribeiro", "thiago.ribeiro@edu.ufes.br"),
    ("Amanda Carvalho", "amanda.carvalho@edu.ufes.br"),
]


def populate():
    init_db()
    conn = get_connection()

    conn.execute("DELETE FROM loans")
    conn.execute("DELETE FROM books")
    conn.commit()

    books_data = load_books()
    for i, (title, author, category, year, copies) in enumerate(books_data, start=1):
        code = f"{i:03d}"
        conn.execute(
            "INSERT INTO books (title, author, category, year, copies, code) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, author, category, year, copies, code),
        )
    conn.commit()

    books = conn.execute("SELECT id, copies FROM books").fetchall()

    def _mk_loan(book_id, kind):
        person, email = random.choice(PEOPLE)
        if kind == "overdue":
            loan_date = (date.today() - timedelta(days=random.randint(15, 40))).isoformat()
            deadline = (date.today() - timedelta(days=random.randint(1, 10))).isoformat()
            conn.execute(
                "INSERT INTO loans (book_id, person, loan_date, deadline_date, email) "
                "VALUES (?, ?, ?, ?, ?)",
                (book_id, person, loan_date, deadline, email))
        elif kind == "active":
            loan_date = (date.today() - timedelta(days=random.randint(1, 3))).isoformat()
            deadline = (date.today() + timedelta(days=random.randint(7, 30))).isoformat()
            conn.execute(
                "INSERT INTO loans (book_id, person, loan_date, deadline_date, email) "
                "VALUES (?, ?, ?, ?, ?)",
                (book_id, person, loan_date, deadline, email))
        elif kind == "nodeadline":
            loan_date = (date.today() - timedelta(days=random.randint(1, 20))).isoformat()
            conn.execute(
                "INSERT INTO loans (book_id, person, loan_date, email) VALUES (?, ?, ?, ?)",
                (book_id, person, loan_date, email))

    # 30 empréstimos ATIVOS distribuídos (10 atrasados, 10 no prazo, 10 sem prazo),
    # respeitando o total de cópias por livro (não emprestar além do que existe).
    active_count = {}
    kinds = ["overdue"] * 10 + ["active"] * 10 + ["nodeadline"] * 10
    random.shuffle(kinds)
    pool = list(books)
    for kind in kinds:
        random.shuffle(pool)
        placed = False
        for bk in pool:
            if active_count.get(bk["id"], 0) < bk["copies"]:
                _mk_loan(bk["id"], kind)
                active_count[bk["id"]] = active_count.get(bk["id"], 0) + 1
                placed = True
                break
        if not placed:
            break

    # Reconcilia o booleano legado available: 0 se todas as cópias emprestadas.
    for bk in books:
        used = active_count.get(bk["id"], 0)
        avail = 0 if used >= bk["copies"] else 1
        conn.execute("UPDATE books SET available = ? WHERE id = ?", (avail, bk["id"]))

    # 50 empréstimos de HISTÓRICO (já devolvidos) em livros quaisquer.
    for bk in random.sample(books, min(50, len(books))):
        person, _ = random.choice(PEOPLE)
        loan_date = (date.today() - timedelta(days=random.randint(30, 90))).isoformat()
        return_date = (date.today() - timedelta(days=random.randint(1, 29))).isoformat()
        conn.execute(
            "INSERT INTO loans (book_id, person, loan_date, return_date) VALUES (?, ?, ?, ?)",
            (bk["id"], person, loan_date, return_date),
        )

    conn.commit()
    total = conn.execute("SELECT COUNT(*) as c FROM books").fetchone()["c"]
    exemplars = conn.execute("SELECT COALESCE(SUM(copies),0) as c FROM books").fetchone()["c"]
    active = conn.execute(
        "SELECT COUNT(*) as c FROM loans WHERE return_date IS NULL").fetchone()["c"]
    conn.close()
    print(f"Done: {total} books ({exemplars} exemplars, {active} active loans)")


if __name__ == "__main__":
    populate()
