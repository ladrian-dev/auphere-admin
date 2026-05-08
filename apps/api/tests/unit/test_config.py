from nexus_api.config import Settings, get_settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    monkeypatch.setenv("NEXUS_LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.environment == "production"
    assert s.log_level == "DEBUG"


def test_settings_is_prod_flag(monkeypatch):
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
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
