import database


class TestInitDb:
    def test_creates_tables(self):
        conn = database.get_connection()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = [t["name"] for t in tables]
        assert "books" in names
        assert "loans" in names
        conn.close()

    def test_idempotent(self):
        database.init_db()
        database.init_db()  # não deve dar erro

    def test_migrations_add_columns(self):
        conn = database.get_connection()
        info = conn.execute("PRAGMA table_info(loans)").fetchall()
        col_names = [c["name"] for c in info]
        assert "email" in col_names
        assert "notified_at" in col_names
        assert "deadline_date" in col_names
        conn.close()

    def test_foreign_keys_on(self):
        conn = database.get_connection()
        fk = conn.execute("PRAGMA foreign_keys").fetchone()
        assert fk[0] == 1
        conn.close()

    def test_get_db_rolls_back_on_error(self):
        import pytest
        # Insere um livro e força exceção: a transação deve ser revertida
        with pytest.raises(RuntimeError):
            with database.get_db() as conn:
                conn.execute("INSERT INTO books (title, author) VALUES ('X', 'Y')")
                raise RuntimeError("boom")
        conn = database.get_connection()
        count = conn.execute("SELECT COUNT(*) AS c FROM books").fetchone()["c"]
        conn.close()
        assert count == 0  # rollback funcionou

    def test_indexes_created(self):
        conn = database.get_connection()
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        names = [r["name"] for r in rows]
        assert "idx_loans_book_id" in names
        assert "idx_loans_active" in names
        assert "idx_loans_overdue" in names
        conn.close()

    def test_deadline_days_removed(self):
        # Simula banco antigo: recria a coluna órfã e roda init_db de novo
        conn = database.get_connection()
        try:
            conn.execute("ALTER TABLE loans ADD COLUMN deadline_days INTEGER")
            conn.commit()
        except Exception:
            pass
        conn.close()
        database.init_db()  # deve dropar a coluna
        conn = database.get_connection()
        cols = [c["name"] for c in conn.execute("PRAGMA table_info(loans)").fetchall()]
        assert "deadline_days" not in cols
        conn.close()
