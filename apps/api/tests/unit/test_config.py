import pytest

from nexus_api.config import _DEV_FERNET_KEY, Settings, get_settings


def _set_prod_secrets(monkeypatch):
    """Set non-placeholder values for the secrets guarded in production so a
    prod-environment Settings() construction passes ``_forbid_dev_secrets_in_prod``."""
    monkeypatch.setenv("NEXUS_META_APP_SECRET", "real-app-secret")
    monkeypatch.setenv("NEXUS_META_WEBHOOK_VERIFY_TOKEN", "real-verify-token")
    monkeypatch.setenv("NEXUS_FERNET_KEY", "prod-fernet-key-override")
    monkeypatch.setenv("NEXUS_EMBED_JWT_SECRET", "real-embed-jwt-secret-32-bytes-long!")


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    monkeypatch.setenv("NEXUS_LOG_LEVEL", "DEBUG")
    _set_prod_secrets(monkeypatch)
    s = Settings()
    assert s.environment == "production"
    assert s.log_level == "DEBUG"


def test_settings_is_prod_flag(monkeypatch):
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    _set_prod_secrets(monkeypatch)
    s = Settings()
    assert s.is_prod is True
    assert s.is_dev is False


def test_settings_is_dev_default(monkeypatch):
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "dev")
    s = Settings()
    assert s.is_dev is True
    assert s.is_prod is False


def test_settings_prod_synonym_works(monkeypatch):
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "prod")
    _set_prod_secrets(monkeypatch)
    s = Settings()
    assert s.is_prod is True


def test_get_settings_caches():
    a = get_settings()
    b = get_settings()
    assert a is b


def test_settings_admin_token_required_for_prod(monkeypatch):
    monkeypatch.setenv("NEXUS_ADMIN_TOKEN", "explicit-secret")
    s = Settings()
    assert s.admin_token == "explicit-secret"


def test_prod_rejects_placeholder_meta_app_secret(monkeypatch):
    """The production guard must refuse to boot with the dev ``change-me``
    Meta app secret / verify token / dev Fernet key still in place."""
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    # meta_app_secret + verify_token left at dev defaults. The session
    # conftest seeds a random valid NEXUS_FERNET_KEY, so pin it back to the
    # dev placeholder here to exercise the fernet branch of the guard too.
    monkeypatch.setenv("NEXUS_FERNET_KEY", _DEV_FERNET_KEY)
    with pytest.raises(ValueError) as exc:
        Settings()
    msg = str(exc.value)
    assert "NEXUS_META_APP_SECRET" in msg
    assert "NEXUS_META_WEBHOOK_VERIFY_TOKEN" in msg
    assert "NEXUS_FERNET_KEY" in msg
    # ADR-028: the embed JWT secret joined the guard — a prod deploy that
    # forgets it must not silently mint tokens with the public default.
    assert "NEXUS_EMBED_JWT_SECRET" in msg


def test_prod_boots_with_real_secrets(monkeypatch):
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    _set_prod_secrets(monkeypatch)
    s = Settings()  # must not raise
    assert s.is_prod is True


def test_dev_tolerates_placeholder_secrets(monkeypatch):
    """The guard only fires in production — dev keeps the convenient defaults."""
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "dev")
    s = Settings()
    assert "change-me" in s.meta_app_secret
