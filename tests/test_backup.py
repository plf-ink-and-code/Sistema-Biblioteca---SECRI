import os
import sqlite3
import pytest
import database
import backup
import services


@pytest.fixture(autouse=True)
def _backup_dir(tmp_path, monkeypatch):
    d = str(tmp_path / "backups")
    monkeypatch.setenv("BACKUP_DIR", d)
    yield d


class TestCreateBackup:
    def test_creates_file(self):
        path = backup.create_backup("20260101-000000")
        assert os.path.exists(path)
        assert path.endswith("biblioteca-20260101-000000.db")

    def test_backup_is_consistent(self):
        # Dados no banco devem aparecer no backup
        services.add_book("Livro X", "Autor Y")
        path = backup.create_backup("20260101-010101")
        conn = sqlite3.connect(path)
        rows = conn.execute("SELECT title FROM books").fetchall()
        conn.close()
        assert ("Livro X",) in rows

    def test_run_backup_returns_path(self):
        path = backup.run_backup()
        assert os.path.exists(path)


class TestListBackups:
    def test_empty_initially(self):
        assert backup.list_backups() == []

    def test_sorted_oldest_first(self):
        backup.create_backup("20260101-000000")
        backup.create_backup("20260103-000000")
        backup.create_backup("20260102-000000")
        names = [os.path.basename(p) for p in backup.list_backups()]
        assert names == [
            "biblioteca-20260101-000000.db",
            "biblioteca-20260102-000000.db",
            "biblioteca-20260103-000000.db",
        ]


class TestRotate:
    def test_keeps_only_n_most_recent(self):
        for i in range(1, 6):
            backup.create_backup(f"2026010{i}-000000")
        removed = backup.rotate(keep=2)
        remaining = [os.path.basename(p) for p in backup.list_backups()]
        assert len(remaining) == 2
        assert remaining == [
            "biblioteca-20260104-000000.db",
            "biblioteca-20260105-000000.db",
        ]
        assert len(removed) == 3

    def test_keep_zero_removes_all(self):
        backup.create_backup("20260101-000000")
        backup.rotate(keep=0)
        assert backup.list_backups() == []

    def test_rotate_respects_env(self, monkeypatch):
        monkeypatch.setenv("BACKUP_KEEP", "1")
        backup.create_backup("20260101-000000")
        backup.create_backup("20260102-000000")
        backup.rotate()
        assert len(backup.list_backups()) == 1
