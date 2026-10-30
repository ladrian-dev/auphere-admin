"""Quién envía correo de verdad y quién solo lo escribe en el registro — spec 051, R1.

Staging tenía la clave de Resend en su secreto y escribía a personas reales
desde el dominio de producción. El modo por entorno convierte «no enviar en
staging» en una decisión escrita, en vez de en la ausencia accidental de una
clave que alguien puede volver a poner.
"""

from __future__ import annotations

import pytest

from nexus_api.config import Settings
from tests.unit.test_config import _set_prod_secrets


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ("production", "resend"),
        ("prod", "resend"),
        ("staging", "access"),
        ("dev", "log"),
        ("ci", "log"),
    ],
)
def test_auto_se_resuelve_por_entorno(
    monkeypatch: pytest.MonkeyPatch, environment: str, expected: str
) -> None:
    monkeypatch.setenv("NEXUS_ENVIRONMENT", environment)
    monkeypatch.delenv("NEXUS_EMAIL_DELIVERY", raising=False)
    if environment in {"production", "prod"}:
        _set_prod_secrets(monkeypatch)
    assert Settings().email_mode == expected


def test_produccion_no_arranca_en_modo_registro(monkeypatch: pytest.MonkeyPatch) -> None:
    """R1.3: el enlace de restablecer la contraseña solo puede acabar en un
    registro porque producción nunca está en este modo."""
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    _set_prod_secrets(monkeypatch)
    monkeypatch.setenv("NEXUS_EMAIL_DELIVERY", "log")
    with pytest.raises(ValueError, match="NEXUS_EMAIL_DELIVERY"):
        Settings()


def test_staging_puede_enviar_si_se_le_pide(monkeypatch: pytest.MonkeyPatch) -> None:
    """R1.4: para probar una plantilla de verdad. El arranque lo deja dicho."""
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "staging")
    monkeypatch.setenv("NEXUS_EMAIL_DELIVERY", "resend")
    assert Settings().email_mode == "resend"


def test_staging_envia_solo_los_de_acceso(monkeypatch: pytest.MonkeyPatch) -> None:
    """Segunda revisión del owner: en staging llegan los correos que hacen
    falta para seguir operando, y nada más. Con la clave real, hay proveedor."""
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "staging")
    monkeypatch.delenv("NEXUS_EMAIL_DELIVERY", raising=False)
    monkeypatch.setenv("NEXUS_RESEND_API_KEY", "re_real_key")
    s = Settings()
    assert s.email_mode == "access"
    assert s.email_delivers is True


@pytest.mark.parametrize("mode", ["log", "access"])
def test_produccion_no_arranca_si_retiene_correos(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    _set_prod_secrets(monkeypatch)
    monkeypatch.setenv("NEXUS_EMAIL_DELIVERY", mode)
    with pytest.raises(ValueError, match="NEXUS_EMAIL_DELIVERY"):
        Settings()


def test_email_delivers_exige_modo_real_y_clave_real(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "staging")
    monkeypatch.setenv("NEXUS_EMAIL_DELIVERY", "resend")
    monkeypatch.setenv("NEXUS_RESEND_API_KEY", "dev-resend-key-change-me")
    assert Settings().email_delivers is False
    monkeypatch.setenv("NEXUS_RESEND_API_KEY", "re_real_key")
    assert Settings().email_delivers is True


def test_las_respuestas_van_a_soporte_y_nada_sale_de_no_reply() -> None:
    """R5: un correo firmado por «el equipo» que no admite respuesta se
    contradice."""
    s = Settings()
    assert s.email_reply_to == "support@auphere.com"
    assert "no-reply" not in s.notifications_from_email
    assert "notifications@auphere.com" in s.notifications_from_email
    assert "billing@auphere.com" in s.receipt_from_email


def test_el_arranque_dice_si_staging_envia_de_verdad(monkeypatch: pytest.MonkeyPatch) -> None:
    """R1.4: staging enviando a personas reales tiene que poder encontrarse."""
    import structlog

    from nexus_api.config import get_settings
    from nexus_api.services.email import log_delivery_mode

    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "staging", raising=False)
    monkeypatch.setattr(settings, "email_delivery", "resend", raising=False)
    with structlog.testing.capture_logs() as logs:
        log_delivery_mode("api")
    [event] = [e for e in logs if e["event"] == "email.delivery_mode"]
    assert event["log_level"] == "warning"
    assert event["mode"] == "resend"
    assert event["real_email_outside_production"] is True

    monkeypatch.setattr(settings, "email_delivery", "auto", raising=False)
    with structlog.testing.capture_logs() as logs:
        log_delivery_mode("api")
    [event] = [e for e in logs if e["event"] == "email.delivery_mode"]
    assert (event["log_level"], event["mode"]) == ("info", "access")
