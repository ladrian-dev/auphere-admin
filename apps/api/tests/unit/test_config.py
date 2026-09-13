import pytest

from nexus_api.config import _DEV_FERNET_KEY, Settings, get_settings


def _set_prod_secrets(monkeypatch):
    """Set non-placeholder values for the secrets guarded in production so a
    prod-environment Settings() construction passes ``_forbid_dev_secrets_in_prod``."""
    monkeypatch.setenv("NEXUS_META_APP_SECRET", "real-app-secret")
    monkeypatch.setenv("NEXUS_META_WEBHOOK_VERIFY_TOKEN", "real-verify-token")
    monkeypatch.setenv("NEXUS_FERNET_KEY", "prod-fernet-key-override")
    monkeypatch.setenv("NEXUS_EMBED_JWT_SECRET", "real-embed-jwt-secret-32-bytes-long!")
    monkeypatch.setenv("NEXUS_CONNECTOR_CONSENT_SECRET", "real-consent-secret-at-least-32-chars!!")
    # Firma las credenciales de dispositivo de la beta 2 (Requisito 6.3): un
    # despliegue de producción sin esto no arranca, y esta lista **es** la
    # especificación de lo que un despliegue necesita.
    monkeypatch.setenv("NEXUS_DEVICE_TOKEN_SECRET", "real-device-secret-at-least-32-chars!!")
    monkeypatch.setenv("NEXUS_COMPOSIO_API_KEY", "real-composio-key")
    monkeypatch.setenv("NEXUS_COMPOSIO_WEBHOOK_SECRET", "real-composio-webhook-secret")
    monkeypatch.setenv("NEXUS_PUBLIC_API_BASE_URL", "https://api.auphere.com")
    monkeypatch.setenv("NEXUS_ADMIN_PANEL_BASE_URL", "https://admin.auphere.com")
    # La consola es a donde el proveedor devuelve al partner tras pagar: esta
    # lista **es** la especificación de lo que un despliegue necesita.
    monkeypatch.setenv("NEXUS_CONSOLE_BASE_URL", "https://consola.auphere.com")
    monkeypatch.setenv("NEXUS_ADMIN_TOKEN", "real-admin-token")


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
    assert "NEXUS_CONNECTOR_CONSENT_SECRET" in msg
    # ADR-028: the embed JWT secret joined the guard — a prod deploy that
    # forgets it must not silently mint tokens with the public default.


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


def test_prod_rejects_the_silent_defaults_from_the_aws_cutover(monkeypatch):
    """Regresión del 2026-08-19.

    Las cuatro claves de abajo no llegaron a las task definitions de AWS. La
    API arrancó igual —todas tienen default— y se llevó por delante el
    catálogo de conectores (cliente Composio falso) y el cierre del OAuth
    (callback a localhost). Sin un solo error. El guard existe para que ese
    despliegue no vuelva a arrancar.
    """
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    _set_prod_secrets(monkeypatch)
    for k in (
        "NEXUS_COMPOSIO_API_KEY",
        "NEXUS_COMPOSIO_WEBHOOK_SECRET",
        "NEXUS_PUBLIC_API_BASE_URL",
        "NEXUS_ADMIN_PANEL_BASE_URL",
    ):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValueError) as exc:
        Settings()
    msg = str(exc.value)
    assert "NEXUS_COMPOSIO_API_KEY" in msg
    assert "NEXUS_COMPOSIO_WEBHOOK_SECRET" in msg
    assert "NEXUS_PUBLIC_API_BASE_URL" in msg
    assert "NEXUS_ADMIN_PANEL_BASE_URL" in msg


def test_prod_rejects_the_payment_return_url_pointing_at_localhost(monkeypatch):
    """El mismo fallo del 2026-08-19, ahora en la ruta de cobro.

    ``console_base_url`` es la URL a la que el proveedor devuelve al partner
    después de pagar, y el ``return_url`` del portal. Sus dos hermanas
    —``public_api_base_url`` y ``admin_panel_base_url``— ya están en el guard;
    esta se quedó fuera. Sin ella, un despliegue que olvide la variable arranca
    limpio, cobra de verdad (el webhook es servidor a servidor y activa la
    suscripción) y manda al partner que acaba de pagar a un ``localhost`` de su
    propia máquina: el dinero entra y el acuse se pierde.
    """
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    _set_prod_secrets(monkeypatch)
    monkeypatch.delenv("NEXUS_CONSOLE_BASE_URL", raising=False)
    with pytest.raises(ValueError) as exc:
        Settings()
    assert "NEXUS_CONSOLE_BASE_URL" in str(exc.value)


def test_prod_rejects_the_placeholder_admin_token(monkeypatch):
    """El ``admin_token`` cierra las 20+ rutas de ``/admin``, ``impersonate``
    incluida. Con el valor de fábrica, cualquiera que lea este repositorio
    tiene el Bearer del panel de operador en producción. El test hermano
    ``test_settings_admin_token_required_for_prod`` solo comprueba que la
    variable se lee: no ejerce el guard.
    """
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    _set_prod_secrets(monkeypatch)
    monkeypatch.delenv("NEXUS_ADMIN_TOKEN", raising=False)
    with pytest.raises(ValueError) as exc:
        Settings()
    assert "NEXUS_ADMIN_TOKEN" in str(exc.value)
