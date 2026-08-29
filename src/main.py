import sys
import os
import time
import logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db
from gui.app import setup_pages
from nicegui import app, ui
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
import auth
import notifier
import backup
from nicegui import run

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("biblioteca")

# Rotas acessíveis sem login
UNRESTRICTED = {"/login", "/health"}


class AuthMiddleware(BaseHTTPMiddleware):
    """Redireciona para /login quem não está autenticado.

    Libera a própria /login, o /health (usado pelo healthcheck do Docker) e os
    assets internos do NiceGUI (/_nicegui...), sem os quais a página de login
    não renderiza.
    """
    async def dispatch(self, request, call_next):
        path = request.url.path
        authenticated = app.storage.user.get("authenticated", False)
        if authenticated and not auth.is_session_valid(
                app.storage.user.get("login_at"), time.time()):
            app.storage.user.clear()
            authenticated = False
        if not authenticated:
            if path not in UNRESTRICTED and not path.startswith("/_nicegui"):
                return RedirectResponse("/login")
        return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


app.add_middleware(AuthMiddleware)


async def _check_overdue_job():
    """Verificação periódica de atrasos, rodando no servidor (não por cliente).

    O SMTP é síncrono, então roda em thread via run.io_bound para não travar
    o event loop.
    """
    try:
        sent = await run.io_bound(notifier.send_student_notifications)
        if sent:
            logger.info("overdue job: %s notificação(ões) enviada(s)", sent)
    except Exception:
        logger.exception("overdue job falhou")


async def _backup_job():
    """Backup periódico do SQLite com rotação, em thread (I/O bloqueante)."""
    try:
        path = await run.io_bound(backup.run_backup)
        logger.info("backup criado: %s", path)
    except Exception:
        logger.exception("backup job falhou")


@app.on_startup
def _start_jobs():
    interval = int(os.environ.get("OVERDUE_CHECK_INTERVAL", "3600"))
    app.timer(interval, _check_overdue_job)
    backup_interval = int(os.environ.get("BACKUP_INTERVAL", "86400"))
    app.timer(backup_interval, _backup_job)


init_db()
setup_pages()
ui.run(host="0.0.0.0", port=8080, title="Biblioteca SECRI", dark=True,
       reload=False, storage_secret=auth.auth_secret())
