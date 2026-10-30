"""De quién viene y qué dice el correo del alta — spec 006 (R1.1, research R8)
y spec 051 (R2, R5).

Visto en staging: el correo de alta salía de `Auphere <facturacion@auphere.com>`.
No por una decisión, sino porque el envío caía al remitente de los recibos
cuando quien llamaba no pasaba otro.

**El primer correo que recibe alguien que no te conoce no puede venir de
«facturación».** Es incoherente —todavía no hay nada que facturar—, invita a
marcarlo como no deseado, y ensucia la reputación de la dirección que sí tiene
que llegar cuando haya recibos de verdad.

Desde la spec 051 el remitente no lo pasa quien llama: sale de la ficha del
tipo en ``CATALOG``. Y tampoco es un «no-reply»: las respuestas van a soporte,
y un remitente que dice «no respondas» firmado por «el equipo» se contradice.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from nexus_api.config import get_settings
from nexus_api.services.email import RESEND_URL
from nexus_api.services.email_catalog import CATALOG, EmailKind, console_link
from nexus_api.services.signup import send_signup_mail

pytestmark = pytest.mark.asyncio


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Recoge las llamadas a ``send_template`` en vez de enviar."""
    seen: list[dict[str, Any]] = []

    async def _fake(kind: EmailKind, **kwargs: Any) -> bool:
        seen.append({"kind": kind, **kwargs})
        return True

    monkeypatch.setattr("nexus_api.services.email.send_template", _fake)
    return seen


async def _payload(monkeypatch: pytest.MonkeyPatch, *, token: str | None) -> dict[str, Any]:
    """Lo que de verdad saldría hacia Resend: envío real contra un doble HTTP."""
    monkeypatch.setattr(get_settings(), "email_delivery", "resend", raising=False)
    monkeypatch.setattr(get_settings(), "resend_api_key", "re_una_clave_de_verdad", raising=False)
    with respx.mock() as mock:
        route = mock.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "m"}))
        assert await send_signup_mail(email="maria@agencia.com", token=token, locale="es")
    body: dict[str, Any] = json.loads(route.calls.last.request.content)
    return body


class TestElRemitenteDelAlta:
    async def test_la_ficha_no_es_la_de_los_cobros(self) -> None:
        """La ficha manda: si alguien la cambia a ``billing``, esto se pone rojo
        aunque el valor por defecto de las direcciones cambie."""
        assert CATALOG[EmailKind.SIGNUP_LINK].sender == "notifications"

    async def test_lo_que_sale_no_viene_de_facturacion_ni_de_un_no_reply(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = await _payload(monkeypatch, token="tok")
        remitente = str(body.get("from") or "")
        # **Se exige que esté puesto, no sólo que no diga «factur».** Sin esta
        # primera aserción el test pasaría por vacío.
        assert remitente, "el envío no lleva remitente"
        assert remitente == get_settings().notifications_from_email
        for prohibido in ("factur", "billing"):
            assert prohibido not in remitente.lower(), (
                f"el alta sale de {remitente!r}: todavía no hay nada que facturar"
            )
        for no_reply in ("no-reply", "noreply", "no_reply"):
            assert no_reply not in remitente.lower(), (
                f"el alta sale de {remitente!r}: pide no responder a un correo firmado por personas"
            )

    async def test_las_respuestas_van_a_soporte(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = await _payload(monkeypatch, token="tok")
        assert body["reply_to"] == get_settings().email_reply_to == "support@auphere.com"

    async def test_el_de_recibos_sigue_siendo_el_de_recibos(self) -> None:
        """No se arregla una cosa rompiendo la de al lado: los recibos **sí**
        vienen de facturación, y eso está bien."""
        assert "billing@" in get_settings().receipt_from_email.lower()

    async def test_el_aviso_de_cuenta_existente_usa_el_mismo_remitente(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Los dos correos del alta son el mismo momento para quien los recibe;
        que vinieran de sitios distintos delataría cuál le tocó (CE-004)."""
        assert CATALOG[EmailKind.SIGNUP_EXISTING].sender == CATALOG[EmailKind.SIGNUP_LINK].sender
        con_enlace = await _payload(monkeypatch, token="tok")
        ya_tiene = await _payload(monkeypatch, token=None)
        assert ya_tiene["from"] == con_enlace["from"]
        assert ya_tiene["reply_to"] == con_enlace["reply_to"]


class TestQueDiceElCorreoDelAlta:
    async def test_con_token_es_el_enlace_del_alta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen = _capture(monkeypatch)
        monkeypatch.setattr(get_settings(), "signup_token_ttl_hours", 24, raising=False)
        await send_signup_mail(email="maria@agencia.com", token="tok-123", locale="es")
        [call] = seen
        assert call["kind"] is EmailKind.SIGNUP_LINK
        assert call["to"] == "maria@agencia.com"
        assert call["locale"] == "es"
        assert call["subject"] == "Confirma tu correo para crear tu cuenta en Auphere"
        assert call["variables"] == {
            "EXPIRES_IN": "24 horas",
            "SIGNUP_URL": console_link("/signup/tok-123"),
        }
        assert call["variables"]["SIGNUP_URL"].startswith(("http://", "https://"))

    async def test_sin_token_es_ya_tienes_cuenta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen = _capture(monkeypatch)
        await send_signup_mail(email="maria@agencia.com", token=None, locale="es")
        [call] = seen
        assert call["kind"] is EmailKind.SIGNUP_EXISTING
        assert call["subject"] == "Ya tienes una cuenta en Auphere"
        assert call["variables"] == {
            "LOGIN_URL": console_link("/login"),
            "FORGOT_URL": console_link("/forgot"),
        }

    async def test_en_ingles(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen = _capture(monkeypatch)
        monkeypatch.setattr(get_settings(), "signup_token_ttl_hours", 24, raising=False)
        await send_signup_mail(email="maria@agencia.com", token="tok", locale="en")
        await send_signup_mail(email="maria@agencia.com", token=None, locale="en")
        link, existing = seen
        assert link["locale"] == existing["locale"] == "en"
        assert link["subject"] == "Confirm your email to create your Auphere account"
        assert link["variables"]["EXPIRES_IN"] == "24 hours"
        assert existing["subject"] == "You already have an Auphere account"

    @pytest.mark.parametrize(
        ("hours", "es", "en"), [(1, "1 hora", "1 hour"), (48, "48 horas", "48 hours")]
    )
    async def test_el_plazo_sale_de_la_configuracion(
        self, monkeypatch: pytest.MonkeyPatch, hours: int, es: str, en: str
    ) -> None:
        seen = _capture(monkeypatch)
        monkeypatch.setattr(get_settings(), "signup_token_ttl_hours", hours, raising=False)
        await send_signup_mail(email="maria@agencia.com", token="tok", locale="es")
        await send_signup_mail(email="maria@agencia.com", token="tok", locale="en")
        assert [c["variables"]["EXPIRES_IN"] for c in seen] == [es, en]

    async def test_un_idioma_que_no_es_ingles_sale_en_espanol(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec 051: la regla del alta pasa a ser la de la contraseña. Antes,
        cualquier valor distinto de ``es`` salía en inglés."""
        seen = _capture(monkeypatch)
        await send_signup_mail(email="maria@agencia.com", token=None, locale="fr")
        await send_signup_mail(email="maria@agencia.com", token=None, locale="en-US")
        assert [c["locale"] for c in seen] == ["es", "en"]
