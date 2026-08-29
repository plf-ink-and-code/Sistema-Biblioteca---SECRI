import pytest
import auth


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Limpa o estado do rate limiter entre testes (é global em memória)."""
    auth._failed_attempts.clear()
    yield
    auth._failed_attempts.clear()


class TestVerifyCredentials:
    def test_default_admin_ok(self, monkeypatch):
        monkeypatch.delenv("ADMIN_USER", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        assert auth.verify_credentials("admin", "admin123") is True

    def test_wrong_password(self, monkeypatch):
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        assert auth.verify_credentials("admin", "errada") is False

    def test_wrong_user(self, monkeypatch):
        monkeypatch.delenv("ADMIN_USER", raising=False)
        assert auth.verify_credentials("root", "admin123") is False

    def test_empty_username(self):
        assert auth.verify_credentials("", "admin123") is False

    def test_none_password(self):
        assert auth.verify_credentials("admin", None) is False

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("ADMIN_USER", "gestor")
        monkeypatch.setenv("ADMIN_PASSWORD", "s3nh4-forte!")
        assert auth.verify_credentials("gestor", "s3nh4-forte!") is True
        assert auth.verify_credentials("admin", "admin123") is False

    def test_case_sensitive(self, monkeypatch):
        monkeypatch.delenv("ADMIN_USER", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        assert auth.verify_credentials("Admin", "admin123") is False
        assert auth.verify_credentials("admin", "ADMIN123") is False


class TestRateLimiting:
    def test_blocks_after_max_attempts(self, monkeypatch):
        monkeypatch.delenv("ADMIN_USER", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "3")
        monkeypatch.setenv("LOGIN_COOLDOWN_SECS", "300")
        for _ in range(3):
            assert auth.verify_credentials("admin", "errada") is False
        # Agora bloqueado — mesmo com a senha CORRETA
        assert auth.seconds_until_unblocked("admin") > 0
        assert auth.verify_credentials("admin", "admin123") is False

    def test_success_resets_counter(self, monkeypatch):
        monkeypatch.delenv("ADMIN_USER", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "5")
        auth.verify_credentials("admin", "errada")
        auth.verify_credentials("admin", "errada")
        assert auth.verify_credentials("admin", "admin123") is True
        assert auth.seconds_until_unblocked("admin") == 0

    def test_not_blocked_below_threshold(self, monkeypatch):
        monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "5")
        for _ in range(4):
            auth.verify_credentials("admin", "errada")
        assert auth.seconds_until_unblocked("admin") == 0

    def test_reset_attempts_helper(self, monkeypatch):
        monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "2")
        auth.verify_credentials("admin", "errada")
        auth.verify_credentials("admin", "errada")
        assert auth.seconds_until_unblocked("admin") > 0
        auth.reset_attempts("admin")
        assert auth.seconds_until_unblocked("admin") == 0


class TestPasswordHashing:
    def test_pbkdf2_deterministic(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET", "fixo")
        assert auth.hash_password("abc") == auth.hash_password("abc")

    def test_pbkdf2_differs_by_password(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET", "fixo")
        assert auth.hash_password("abc") != auth.hash_password("abd")

    def test_pbkdf2_salt_from_secret(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET", "secret-a")
        h_a = auth.hash_password("mesma-senha")
        monkeypatch.setenv("AUTH_SECRET", "secret-b")
        h_b = auth.hash_password("mesma-senha")
        assert h_a != h_b  # salt diferente => hash diferente

    def test_returns_bytes(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET", "x")
        assert isinstance(auth.hash_password("p"), bytes)


class TestSession:
    def test_valid_recent_session(self):
        import time
        now = time.time()
        assert auth.is_session_valid(now - 60, now) is True

    def test_expired_session(self, monkeypatch):
        import time
        monkeypatch.setenv("SESSION_MAX_AGE_HOURS", "1")
        now = time.time()
        assert auth.is_session_valid(now - 3700, now) is False

    def test_none_login_at_invalid(self):
        import time
        assert auth.is_session_valid(None, time.time()) is False

    def test_custom_max_age(self, monkeypatch):
        monkeypatch.setenv("SESSION_MAX_AGE_HOURS", "0.01")  # 36s
        assert auth.session_max_age_secs() == 36


class TestConfigHelpers:
    def test_admin_user_default(self, monkeypatch):
        monkeypatch.delenv("ADMIN_USER", raising=False)
        assert auth.admin_user() == "admin"

    def test_admin_user_override(self, monkeypatch):
        monkeypatch.setenv("ADMIN_USER", "chefe")
        assert auth.admin_user() == "chefe"

    def test_auth_secret_uses_env(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET", "meu-segredo")
        assert auth.auth_secret() == "meu-segredo"

    def test_auth_secret_derived_when_absent(self, monkeypatch):
        monkeypatch.delenv("AUTH_SECRET", raising=False)
        monkeypatch.delenv("ADMIN_USER", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        secret = auth.auth_secret()
        assert isinstance(secret, str) and len(secret) == 64  # sha256 hex
