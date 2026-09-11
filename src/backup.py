"""Backup consistente do banco SQLite, com rotação.

Usa a API nativa `sqlite3.Connection.backup()`, que gera uma cópia consistente
mesmo com o banco em uso e em modo WAL — diferente de copiar o arquivo `.db`
com `cp`, que pode capturar um estado parcial.

Config via env:
    BACKUP_DIR       diretório dos backups (default: <data>/backups)
    BACKUP_KEEP      quantos backups manter (default: 7)
    BACKUP_INTERVAL  intervalo do job em segundos (default: 86400 = 24h)
"""
import os
import sqlite3
import glob
import logging
from datetime import datetime

import database
import backup_remote

logger = logging.getLogger("biblioteca.backup")

_PREFIX = "biblioteca-"
_SUFFIX = ".db"


def backup_dir() -> str:
    default = os.path.join(os.path.dirname(database.DB_PATH), "backups")
    return os.environ.get("BACKUP_DIR", default)


def _keep() -> int:
    return int(os.environ.get("BACKUP_KEEP", "7"))


def create_backup(timestamp: str | None = None) -> str:
    """Gera um backup consistente e retorna o caminho do arquivo criado."""
    os.makedirs(backup_dir(), exist_ok=True)
    stamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_path = os.path.join(backup_dir(), f"{_PREFIX}{stamp}{_SUFFIX}")

    src = sqlite3.connect(database.DB_PATH)
    try:
        dst = sqlite3.connect(dest_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dest_path


def list_backups() -> list[str]:
    """Backups existentes, do mais antigo para o mais recente (ordenável por nome)."""
    return sorted(glob.glob(os.path.join(backup_dir(), f"{_PREFIX}*{_SUFFIX}")))


def rotate(keep: int | None = None) -> list[str]:
    """Remove os backups mais antigos, mantendo os `keep` mais recentes.

    Retorna a lista de arquivos removidos.
    """
    keep = _keep() if keep is None else keep
    backups = list_backups()
    to_remove = backups[:-keep] if keep > 0 else backups
    for path in to_remove:
        try:
            os.remove(path)
        except OSError:
            pass
    return to_remove


def run_backup() -> str:
    """Cria um backup, aplica a rotação local e (se configurado) envia ao Drive.

    O envio off-site é opt-in (ver backup_remote). Uma falha no upload é logada
    mas NÃO derruba o backup local — a cópia local permanece íntegra.
    """
    path = create_backup()
    rotate()
    try:
        file_id = backup_remote.send_backup(path)
        if file_id:
            logger.info("backup enviado ao Drive (id=%s)", file_id)
    except Exception:
        logger.exception("envio do backup ao Google Drive falhou")
    return path
