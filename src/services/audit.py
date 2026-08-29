from database import get_db
from datetime import datetime


def log_action(action, detail=None, username="system"):
    """Registra uma ação no audit log."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO audit_log (ts, username, action, detail) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), username, action, detail),
        )


def list_audit(limit=100):
    """Retorna as ações mais recentes (mais nova primeiro)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
