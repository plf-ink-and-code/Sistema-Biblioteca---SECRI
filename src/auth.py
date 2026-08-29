"""Autenticação simples de admin único, com PBKDF2 e rate limiting.

Credenciais vêm de variáveis de ambiente (12-factor):

    ADMIN_USER      usuário admin        (default: admin)
    ADMIN_PASSWORD  senha em texto puro  (default: admin123 — só para DEV!)
    AUTH_SECRET     segredo p/ cookies de sessão + salt do PBKDF2

Rate limiting (por usuário, em memória):
    LOGIN_MAX_ATTEMPTS   tentativas antes do bloqueio (default: 5)
    LOGIN_COOLDOWN_SECS  duração do bloqueio em segundos (default: 300)

NOTA DE SEGURANÇA: `admin123` é uma senha fraca, adequada apenas para testes
locais. Defina `ADMIN_PASSWORD` e `AUTH_SECRET` por variável de ambiente antes
de qualquer uso real.
"""
import hashlib
import hmac
import os
import threading
import time

DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin123"  # apenas DEV — sobrescreva via ADMIN_PASSWORD

_PBKDF2_ITERATIONS = 120_000
_PBKDF2_ALGO = "sha256"

# Estado do rate limiter: {username: [timestamps de tentativas falhas]}
_attempts_lock = threading.Lock()
_failed_attempts: dict[str, list[float]] = {}


# ----------------------------- config helpers ------------------------------
def admin_user() -> str:
    return os.environ.get("ADMIN_USER", DEFAULT_USER)


def _admin_password() -> str:
    return os.environ.get("ADMIN_PASSWORD", DEFAULT_PASSWORD)


def auth_secret() -> str:
    """Segredo para assinar cookies de sessão (e salt do PBKDF2).

    Usa AUTH_SECRET se definido; senão deriva das credenciais do admin
    (estável, suficiente para DEV). Defina AUTH_SECRET em produção.
    """
    return os.environ.get("AUTH_SECRET") or _sha256(admin_user() + ":" + _admin_password())


def _max_attempts() -> int:
    return int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))


def _cooldown_secs() -> int:
    return int(os.environ.get("LOGIN_COOLDOWN_SECS", "300"))


# --------------------------------- hashing ---------------------------------
def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> bytes:
    """Deriva a senha com PBKDF2-HMAC-SHA256 (KDF lento, resistente a brute force).

    O salt é derivado de AUTH_SECRET para ser estável entre reinícios sem
    precisar persistir estado (admin único configurado por env).
    """
    salt = hashlib.sha256(auth_secret().encode("utf-8")).digest()
    return hashlib.pbkdf2_hmac(_PBKDF2_ALGO, password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)


# ------------------------------ rate limiting ------------------------------
def _now() -> float:
    return time.monotonic()


def seconds_until_unblocked(username: str) -> int:
    """Segundos restantes de bloqueio para o usuário (0 se não bloqueado)."""
    with _attempts_lock:
        return _seconds_until_unblocked_locked(username)


def _seconds_until_unblocked_locked(username: str) -> int:
    cooldown = _cooldown_secs()
    now = _now()
    times = [t for t in _failed_attempts.get(username, []) if now - t < cooldown]
    _failed_attempts[username] = times
    if len(times) >= _max_attempts():
        oldest = min(times)
        return max(0, int(cooldown - (now - oldest)) + 1)
    return 0


def _record_failure(username: str) -> None:
    with _attempts_lock:
        _failed_attempts.setdefault(username, []).append(_now())


def _reset(username: str) -> None:
    with _attempts_lock:
        _failed_attempts.pop(username, None)


def reset_attempts(username: str) -> None:
    """Limpa o histórico de tentativas (uso em testes / após sucesso)."""
    _reset(username)


# ---------------------------- session lifetime -----------------------------
def session_max_age_secs() -> int:
    hours = float(os.environ.get("SESSION_MAX_AGE_HOURS", "8"))
    return int(hours * 3600)


def is_session_valid(login_at, now: float) -> bool:
    """True se a sessão iniciada em `login_at` (epoch) ainda não expirou."""
    if not login_at:
        return False
    return (now - float(login_at)) < session_max_age_secs()


# --------------------------------- verify ----------------------------------
def verify_credentials(username: str, password: str) -> bool:
    """Retorna True se usuário e senha conferem (time-safe + PBKDF2).

    Respeita o rate limiting: se o usuário está bloqueado, retorna False sem
    checar a senha. Sucesso zera o contador; falha registra a tentativa.
    """
    if not username or password is None:
        return False
    if seconds_until_unblocked(username) > 0:
        return False

    user_ok = hmac.compare_digest(_sha256(username), _sha256(admin_user()))
    pass_ok = hmac.compare_digest(hash_password(password), hash_password(_admin_password()))

    if user_ok and pass_ok:
        _reset(username)
        return True
    _record_failure(username)
    return False
