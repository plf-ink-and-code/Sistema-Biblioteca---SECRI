"""Benchmark das operações que a UI dispara.

Popula um banco SQLite temporário com volume configurável e cronometra as
operações mais chamadas (listagem com status, filtros, busca, dashboard,
overdue, active_loan). Uso:

    PYTHONPATH=src python tests/benchmark.py [N_BOOKS]

Rodar via Docker (padrão do projeto):

    docker run --rm -v $(pwd):/app -w /app python:3.11-slim sh -c \
      "PYTHONPATH=/app/src python tests/benchmark.py 5000"
"""
import os
import sys
import time
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import database

# Banco temporário isolado
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
database.DB_PATH = _tmp.name

import services  # noqa: E402  (importa depois de fixar DB_PATH)


def timeit(label, fn, repeat=1):
    # warmup
    fn()
    start = time.perf_counter()
    for _ in range(repeat):
        result = fn()
    elapsed = (time.perf_counter() - start) / repeat
    n = len(result) if hasattr(result, "__len__") else "-"
    print(f"  {label:<32} {elapsed*1000:8.2f} ms   (rows={n})")
    return elapsed


def seed(n_books):
    print(f"Seeding {n_books} livros...")
    cats = ["Romance", "Conto", "Ficção", "História", "Ciência", "Poesia"]
    # inserção em lote numa única transação
    with database.get_db() as conn:
        for i in range(n_books):
            conn.execute(
                "INSERT INTO books (title, author, category, year, code, available) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                (f"Livro {i:05d}", f"Autor {i % 500}", cats[i % len(cats)],
                 2000 + (i % 25), f"{i:05d}"),
            )
    # empresta ~40%, dos quais alguns atrasados
    book_ids = [b["id"] for b in services.list_books()]
    n_loans = int(n_books * 0.4)
    past = (date.today() - timedelta(days=5)).isoformat()
    future = (date.today() + timedelta(days=10)).isoformat()
    with database.get_db() as conn:
        for idx, bid in enumerate(book_ids[:n_loans]):
            deadline = past if idx % 3 == 0 else future
            conn.execute(
                "INSERT INTO loans (book_id, person, loan_date, deadline_date, email) "
                "VALUES (?, ?, ?, ?, ?)",
                (bid, f"Aluno {idx % 300}", date.today().isoformat(), deadline,
                 f"aluno{idx % 300}@x.com"),
            )
            conn.execute("UPDATE books SET available = 0 WHERE id = ?", (bid,))
    print(f"  {n_loans} empréstimos ativos (~1/3 atrasados)\n")


def main():
    n_books = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    database.init_db()
    seed(n_books)

    all_books = services.list_books()
    romance = services.filter_by_category("Romance")
    sample_loaned = next(b["id"] for b in all_books if not b["available"])

    print("Operações (média de 5 execuções):")
    timeit("list_books", services.list_books, repeat=5)
    timeit("books_with_status (todos)", services.books_with_status, repeat=5)
    timeit("books_with_status (subset ids)",
           lambda: services.books_with_status(romance), repeat=5)
    timeit("books_with_status (category SQL)",
           lambda: services.books_with_status(category="Romance"), repeat=5)
    timeit("filter_by_category", lambda: services.filter_by_category("Romance"), repeat=5)
    timeit("search_books('Livro 001')",
           lambda: services.search_books("Livro 001"), repeat=5)
    timeit("overdue_loans", services.overdue_loans, repeat=5)
    timeit("dashboard_stats", services.dashboard_stats, repeat=5)
    timeit("active_loan (1 livro)", lambda: services.active_loan(sample_loaned), repeat=20)
    timeit("top_loaned_books", services.top_loaned_books, repeat=5)
    timeit("top_borrowers", services.top_borrowers, repeat=5)

    os.unlink(database.DB_PATH)


if __name__ == "__main__":
    main()
