"""Testes do modelo de múltiplos exemplares (copies) e do filtro alfabético A-Z."""
import pytest
import services


class TestCopiesModel:
    def test_add_book_default_copies_one(self):
        services.add_book("Livro Único", "Autor")
        b = services.list_books()[0]
        assert b["copies"] == 1
        assert services.available_count(b["id"]) == 1

    def test_add_book_with_copies(self):
        services.add_book("Com Cópias", "Autor", copies=5)
        b = services.list_books()[0]
        assert b["copies"] == 5
        assert services.available_count(b["id"]) == 5

    def test_add_book_invalid_copies_coerced(self):
        services.add_book("Zero", "Autor", copies=0)
        services.add_book("Neg", "Autor", copies=-3)
        services.add_book("Texto", "Autor", copies="abc")
        for b in services.list_books():
            assert b["copies"] == 1

    def test_loan_decrements_availability(self):
        services.add_book("Três", "Autor", copies=3)
        bid = services.list_books()[0]["id"]
        services.loan_book(bid, "Aluno A")
        assert services.available_count(bid) == 2
        services.loan_book(bid, "Aluno B")
        assert services.available_count(bid) == 1

    def test_loan_until_exhausted_then_block(self):
        services.add_book("Dois", "Autor", copies=2)
        bid = services.list_books()[0]["id"]
        services.loan_book(bid, "A")
        services.loan_book(bid, "B")
        assert services.available_count(bid) == 0
        with pytest.raises(ValueError):
            services.loan_book(bid, "C")  # esgotado

    def test_return_increments_availability(self):
        services.add_book("Devolve", "Autor", copies=2)
        bid = services.list_books()[0]["id"]
        services.loan_book(bid, "A")
        services.loan_book(bid, "B")
        assert services.available_count(bid) == 0
        closed = services.return_book(bid)
        assert closed is True
        assert services.available_count(bid) == 1

    def test_return_when_none_active_is_false(self):
        services.add_book("Sem Empréstimo", "Autor", copies=1)
        bid = services.list_books()[0]["id"]
        assert services.return_book(bid) is False
        assert services.available_count(bid) == 1

    def test_edit_preserves_copies_when_none(self):
        services.add_book("Mantém", "Autor", copies=7)
        bid = services.list_books()[0]["id"]
        services.edit_book(bid, "Mantém!", "Autor", copies=None)
        assert services.get_book(bid)["copies"] == 7

    def test_edit_updates_copies(self):
        services.add_book("Muda", "Autor", copies=2)
        bid = services.list_books()[0]["id"]
        services.edit_book(bid, "Muda", "Autor", copies=9)
        assert services.get_book(bid)["copies"] == 9

    def test_edit_invalid_copies_coerced_to_one(self):
        services.add_book("Corrige", "Autor", copies=4)
        bid = services.list_books()[0]["id"]
        services.edit_book(bid, "Corrige", "Autor", copies=0)
        assert services.get_book(bid)["copies"] == 1
        services.edit_book(bid, "Corrige", "Autor", copies="xyz")
        assert services.get_book(bid)["copies"] == 1

    def test_single_copy_behaves_like_before(self):
        services.add_book("Clássico", "Autor", copies=1)
        bid = services.list_books()[0]["id"]
        services.loan_book(bid, "A")
        with pytest.raises(ValueError):
            services.loan_book(bid, "B")
        services.return_book(bid)
        services.loan_book(bid, "C")  # ok de novo


class TestBooksWithStatusCopies:
    def test_status_disponivel_partial(self):
        services.add_book("Parcial", "Autor", copies=3)
        bid = services.list_books()[0]["id"]
        services.loan_book(bid, "A")
        row = next(r for r in services.books_with_status() if r["id"] == bid)
        assert row["status"] == "Disponível"
        assert row["available_count"] == 2
        assert row["copies"] == 3
        assert row["copies_label"] == "2/3"

    def test_status_esgotado(self):
        services.add_book("Esgota", "Autor", copies=1)
        bid = services.list_books()[0]["id"]
        services.loan_book(bid, "A")
        row = next(r for r in services.books_with_status() if r["id"] == bid)
        assert row["status"] == "Esgotado"
        assert row["available_count"] == 0

    def test_status_atrasado(self):
        from datetime import date, timedelta
        services.add_book("Atrasa", "Autor", copies=1)
        bid = services.list_books()[0]["id"]
        past = (date.today() - timedelta(days=5)).isoformat()
        services.loan_book(bid, "A", deadline_date=past)
        row = next(r for r in services.books_with_status() if r["id"] == bid)
        assert row["status"] == "Atrasado"


class TestAlphabeticalFilter:
    def _seed(self):
        services.add_book("Abelha", "X")
        services.add_book("Arara", "X")
        services.add_book("Baleia", "X")
        services.add_book("Cobra", "X")
        services.add_book("1984", "Orwell")
        services.add_book("300", "Frank Miller")

    def test_list_by_initial_letter(self):
        self._seed()
        titles = [b["title"] for b in services.list_by_initial("A")]
        assert titles == ["Abelha", "Arara"]

    def test_list_by_initial_case_insensitive(self):
        self._seed()
        assert len(services.list_by_initial("a")) == 2

    def test_list_by_initial_digits(self):
        self._seed()
        titles = sorted(b["title"] for b in services.list_by_initial("0-9"))
        assert titles == ["1984", "300"]

    def test_list_by_initial_empty(self):
        self._seed()
        assert services.list_by_initial("Z") == []

    def test_books_with_status_initial_filter(self):
        self._seed()
        rows = services.books_with_status(initial="B")
        assert [r["title"] for r in rows] == ["Baleia"]

    def test_books_with_status_initial_digits(self):
        self._seed()
        rows = services.books_with_status(initial="0-9")
        assert sorted(r["title"] for r in rows) == ["1984", "300"]

    def test_books_with_status_initial_and_category(self):
        services.add_book("Arroz", "X", category="Culinária")
        services.add_book("Aviao", "X", category="Técnico")
        rows = services.books_with_status(category="Culinária", initial="A")
        assert [r["title"] for r in rows] == ["Arroz"]
