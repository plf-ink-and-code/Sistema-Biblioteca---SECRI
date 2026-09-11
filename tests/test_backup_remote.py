"""Testes do envio off-site para o Google Drive (cliente Google mockado).

O upload real depende da credencial da Service Account e fica com o usuário
validar. Aqui garantimos a LÓGICA: opt-in por env, metadados corretos do
upload, e a rotação apagando só os excedentes `biblioteca-*` da pasta.
"""
from unittest.mock import MagicMock, patch

import pytest

import backup_remote
import backup


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("GDRIVE_CREDENTIALS_FILE", "GDRIVE_FOLDER_ID", "GDRIVE_KEEP"):
        monkeypatch.delenv(var, raising=False)
    yield


def _configure(monkeypatch, keep=None):
    monkeypatch.setenv("GDRIVE_CREDENTIALS_FILE", "/fake/creds.json")
    monkeypatch.setenv("GDRIVE_FOLDER_ID", "FOLDER123")
    if keep is not None:
        monkeypatch.setenv("GDRIVE_KEEP", str(keep))


class TestIsConfigured:
    def test_disabled_without_env(self):
        assert backup_remote.is_configured() is False

    def test_enabled_with_both_vars(self, monkeypatch):
        _configure(monkeypatch)
        assert backup_remote.is_configured() is True

    def test_disabled_with_only_credentials(self, monkeypatch):
        monkeypatch.setenv("GDRIVE_CREDENTIALS_FILE", "/fake/creds.json")
        assert backup_remote.is_configured() is False


def _fake_service():
    """Mock encadeável do cliente Drive: svc.files().create().execute()."""
    svc = MagicMock()
    return svc


class TestUpload:
    def test_upload_sends_to_configured_folder(self, monkeypatch, tmp_path):
        _configure(monkeypatch)
        f = tmp_path / "biblioteca-20260101-000000.db"
        f.write_bytes(b"sqlitedata")

        svc = _fake_service()
        svc.files().create().execute.return_value = {"id": "FILE_ID_1"}

        # MediaFileUpload é importado dentro da função a partir de
        # googleapiclient.http — patchamos na origem.
        with patch("googleapiclient.http.MediaFileUpload") as media:
            file_id = backup_remote.upload_to_drive(str(f), service=svc)

        assert file_id == "FILE_ID_1"
        media.assert_called_once()
        # Metadados: nome do arquivo e pasta pai corretos.
        _, kwargs = svc.files().create.call_args
        assert kwargs["body"]["name"] == "biblioteca-20260101-000000.db"
        assert kwargs["body"]["parents"] == ["FOLDER123"]


def _list_response(names):
    return {"files": [{"id": f"id-{n}", "name": n} for n in names]}


class TestRotateDrive:
    def test_removes_only_excess_newest_kept(self, monkeypatch):
        _configure(monkeypatch)
        svc = _fake_service()
        # API já devolve por name desc (mais recente primeiro).
        svc.files().list().execute.return_value = _list_response([
            "biblioteca-20260105-000000.db",
            "biblioteca-20260104-000000.db",
            "biblioteca-20260103-000000.db",
            "biblioteca-20260102-000000.db",
            "biblioteca-20260101-000000.db",
        ])

        removed = backup_remote.rotate_drive(keep=2, service=svc)

        assert removed == [
            "biblioteca-20260103-000000.db",
            "biblioteca-20260102-000000.db",
            "biblioteca-20260101-000000.db",
        ]
        assert svc.files().delete.call_count == 3

    def test_ignores_non_prefixed_files(self, monkeypatch):
        _configure(monkeypatch)
        svc = _fake_service()
        svc.files().list().execute.return_value = _list_response([
            "biblioteca-20260102-000000.db",
            "planilha-do-gestor.xlsx",   # não deve ser considerado nem apagado
            "biblioteca-20260101-000000.db",
        ])

        removed = backup_remote.rotate_drive(keep=1, service=svc)

        assert removed == ["biblioteca-20260101-000000.db"]
        assert "planilha-do-gestor.xlsx" not in removed
        assert svc.files().delete.call_count == 1

    def test_keep_zero_removes_all_prefixed(self, monkeypatch):
        _configure(monkeypatch)
        svc = _fake_service()
        svc.files().list().execute.return_value = _list_response([
            "biblioteca-20260102-000000.db",
            "biblioteca-20260101-000000.db",
        ])
        removed = backup_remote.rotate_drive(keep=0, service=svc)
        assert len(removed) == 2


class TestSendBackup:
    def test_noop_when_not_configured(self):
        # Sem env: não tenta importar libs Google nem chamar rede.
        assert backup_remote.send_backup("/qualquer/backup.db") is None

    def test_runs_upload_and_rotation_when_configured(self, monkeypatch, tmp_path):
        _configure(monkeypatch, keep=30)
        f = tmp_path / "biblioteca-20260101-000000.db"
        f.write_bytes(b"data")

        svc = _fake_service()
        with patch("backup_remote._build_service", return_value=svc), \
             patch("backup_remote.upload_to_drive", return_value="ID9") as up, \
             patch("backup_remote.rotate_drive", return_value=[]) as rot:
            result = backup_remote.send_backup(str(f))

        assert result == "ID9"
        up.assert_called_once()
        rot.assert_called_once()


class TestRunBackupIntegration:
    def test_run_backup_survives_drive_failure(self, monkeypatch, tmp_path):
        """Falha no envio ao Drive não derruba o backup local."""
        monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
        with patch("backup_remote.send_backup", side_effect=RuntimeError("drive down")):
            path = backup.run_backup()
        import os
        assert os.path.exists(path)  # backup local intacto apesar da falha remota
