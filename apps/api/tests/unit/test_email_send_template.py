"""Enviar un correo es enviar una plantilla — spec 051, R1, R2, R5, R6 y R7.

``send_template`` es el único sitio que habla con Resend. Estas pruebas fijan
lo que sale (y lo que no) en cada modo: en ``log`` nada toca la red y el
registro lleva los enlaces de acción; en ``resend`` el cuerpo es una plantilla
con sus variables escapadas, sin HTML propio y sin enlaces en el registro.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
import structlog

from nexus_api.config import get_settings
from nexus_api.services.email import RESEND_URL, send_template
from nexus_api.services.email_catalog import EmailKind, lines_variable

pytestmark = pytest.mark.asyncio

_RESET = "https://consola.auphere.test/reset/tok-123"


def _mode(monkeypatch: pytest.MonkeyPatch, mode: str, key: str = "re_real_key") -> None:
    monkeypatch.setattr(get_settings(), "email_delivery", mode, raising=False)
    monkeypatch.setattr(get_settings(), "resend_api_key", key, raising=False)


def _events(logs: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [e for e in logs if e.get("event") == name]


class TestEnModoRegistroNadaSale:
    async def test_no_toca_la_red_y_deja_los_enlaces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mode(monkeypatch, "log")
        with respx.mock(assert_all_called=False) as mock, structlog.testing.capture_logs() as logs:
            route = mock.post(RESEND_URL)
            ok = await send_template(
                EmailKind.PASSWORD_RESET,
                to="maria@agencia.com",
                subject="Restablece tu contraseña de Auphere",
                variables={"RESET_URL": _RESET},
            )
        assert ok is True, "R1.2: para quien llama, el correo salió"
        assert not route.called
        [event] = _events(logs, "email.suppressed")
        assert event["kind"] == "password_reset"
        assert event["template"] == "auphere-password-reset-es"
        assert event["to"] == ["maria@agencia.com"]
        assert event["subject"] == "Restablece tu contraseña de Auphere"
        assert event["links"] == {"RESET_URL": _RESET}

    async def test_solo_registra_las_variables_de_enlace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """El texto de una consulta o un importe no hacen falta para completar
        un flujo, y registrarlos mete datos personales sin propósito."""
        _mode(monkeypatch, "log")
        with structlog.testing.capture_logs() as logs:
            await send_template(
                EmailKind.CHARGE_CONFIRM,
                to="facturas@agencia.com",
                subject="Confirma el pago de US$10.00 con tu banco",
                variables={
                    "PARTNER_NAME": "Agencia Norte",
                    "AMOUNT": "US$10.00",
                    "CONCEPT": "el consumo del mes",
                    "CONFIRM_URL": "https://invoice.stripe.com/i/abc",
                },
                partner_id="p-1",
            )
        [event] = _events(logs, "email.suppressed")
        assert event["links"] == {"CONFIRM_URL": "https://invoice.stripe.com/i/abc"}
        assert "Agencia Norte" not in json.dumps(event["links"])
        assert event["partner_id"] == "p-1"
        assert event["owner"] == "partner"


class TestEnModoRealSaleUnaPlantilla:
    async def test_el_cuerpo_es_una_plantilla_con_sus_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mode(monkeypatch, "resend")
        with respx.mock() as mock, structlog.testing.capture_logs() as logs:
            route = mock.post(RESEND_URL).mock(
                return_value=httpx.Response(200, json={"id": "msg-1"})
            )
            ok = await send_template(
                EmailKind.CLIENT_INVITE,
                to=["ana@cliente.com"],
                subject="Ya puedes acceder a la consola de <b>Café & Té</b>",
                variables={
                    "CLIENT_NAME": "<b>Café & Té</b>",
                    "EXPIRES_ON": "6 de noviembre de 2026",
                    "ACCEPT_URL": "https://consola.auphere.test/invite/t?a=1&b=2",
                },
                client_ref="cafe-te",
            )
        assert ok is True
        body = json.loads(route.calls.last.request.content)
        assert body["template"]["id"] == "auphere-client-invite-es"
        variables = body["template"]["variables"]
        assert variables["CLIENT_NAME"] == "&lt;b&gt;Café &amp; Té&lt;/b&gt;"
        assert variables["ACCEPT_URL"] == "https://consola.auphere.test/invite/t?a=1&amp;b=2"
        assert "html" not in body and "text" not in body
        assert body["from"] == get_settings().notifications_from_email
        assert body["reply_to"] == "support@auphere.com"
        # El asunto no es HTML: viaja tal cual.
        assert body["subject"] == "Ya puedes acceder a la consola de <b>Café & Té</b>"
        assert {"name": "kind", "value": "client_invite"} in body["tags"]
        assert route.calls.last.request.headers["Authorization"] == "Bearer re_real_key"
        [event] = _events(logs, "email.sent")
        assert "links" not in event, "R1.5: en envío real, los enlaces no van al registro"
        assert event["message_id"] == "msg-1"
        assert event["client_ref"] == "cafe-te"

    async def test_los_cobros_salen_de_billing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mode(monkeypatch, "resend")
        with respx.mock() as mock:
            route = mock.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "m"}))
            await send_template(
                EmailKind.CHARGE_CONFIRM,
                to="f@a.com",
                subject="s",
                variables={"PARTNER_NAME": "A", "AMOUNT": "1", "CONCEPT": "c", "CONFIRM_URL": "u"},
                partner_id="p",
            )
        assert json.loads(route.calls.last.request.content)["from"] == (
            get_settings().receipt_from_email
        )

    async def test_las_lineas_no_se_escapan_dos_veces(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mode(monkeypatch, "resend")
        with respx.mock() as mock:
            route = mock.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "m"}))
            await send_template(
                EmailKind.INTERNAL_ALERT,
                to="ops@auphere.test",
                subject="[Auphere] x",
                variables={
                    "HEADING": "h",
                    "DETAIL": lines_variable(["a & b", "c"]),
                    "KIND": "dlq",
                },
            )
        sent = json.loads(route.calls.last.request.content)["template"]["variables"]
        assert sent["DETAIL"] == "a &amp; b<br>c"

    async def test_en_ingles_usa_su_plantilla(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mode(monkeypatch, "resend")
        with respx.mock() as mock:
            route = mock.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "m"}))
            await send_template(
                EmailKind.PASSWORD_RESET,
                to="a@b.com",
                subject="Reset your Auphere password",
                variables={"RESET_URL": _RESET},
                locale="en",
            )
            await send_template(
                EmailKind.INTERNAL_ALERT,
                to="ops@auphere.test",
                subject="[Auphere] x",
                variables={"HEADING": "h", "DETAIL": "d", "KIND": "k"},
                locale="en",
            )
        ids = [json.loads(c.request.content)["template"]["id"] for c in route.calls]
        assert ids == ["auphere-password-reset-en", "auphere-internal-alert-es"]

    async def test_una_respuesta_explicita_gana(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """La petición de borrado responde a quien la pidió (R5.1)."""
        _mode(monkeypatch, "resend")
        with respx.mock() as mock:
            route = mock.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "m"}))
            await send_template(
                EmailKind.INTERNAL_ALERT,
                to="seguridad@auphere.test",
                subject="[Auphere] Petición de borrado de cuenta: ana@x.com",
                variables={"HEADING": "h", "DETAIL": "d", "KIND": "k"},
                reply_to="ana@x.com",
            )
        assert json.loads(route.calls.last.request.content)["reply_to"] == "ana@x.com"

    async def test_un_valor_demasiado_largo_se_recorta(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mode(monkeypatch, "resend")
        with respx.mock() as mock:
            route = mock.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "m"}))
            ok = await send_template(
                EmailKind.INTERNAL_ALERT,
                to="ops@auphere.test",
                subject="s",
                variables={"HEADING": "h", "DETAIL": "x&" * 1500, "KIND": "k"},
            )
        assert ok is True
        detail = json.loads(route.calls.last.request.content)["template"]["variables"]["DETAIL"]
        assert len(detail) <= 2000
        assert detail.endswith("…")
        assert not detail.removesuffix("…").endswith("&am"), "no corta una entidad por la mitad"


class TestEnStagingSoloSalenLosDeAcceso:
    async def test_un_correo_de_acceso_sale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mode(monkeypatch, "access")
        with respx.mock() as mock:
            route = mock.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "m"}))
            ok = await send_template(
                EmailKind.PASSWORD_RESET, to="a@b.com", subject="s", variables={"RESET_URL": _RESET}
            )
        assert ok is True
        assert route.called

    async def test_lo_automatico_se_queda_en_el_registro(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mode(monkeypatch, "access")
        with respx.mock(assert_all_called=False) as mock, structlog.testing.capture_logs() as logs:
            route = mock.post(RESEND_URL)
            ok = await send_template(
                EmailKind.WALLET_EMPTY,
                to="ops@a.com",
                subject="s",
                variables={"PARTNER_NAME": "A", "PERIOD": "p", "BILLING_URL": "u"},
                partner_id="p",
            )
        assert ok is True
        assert not route.called
        assert _events(logs, "email.suppressed")


class TestLoQueNoSaleSeDice:
    async def test_variables_de_menos_o_de_mas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mode(monkeypatch, "resend")
        with respx.mock(assert_all_called=False) as mock, structlog.testing.capture_logs() as logs:
            route = mock.post(RESEND_URL)
            ok = await send_template(
                EmailKind.PASSWORD_RESET,
                to="a@b.com",
                subject="s",
                variables={"RESET": _RESET},
            )
        assert ok is False
        assert not route.called
        [event] = _events(logs, "email.variables_mismatch")
        assert event["missing"] == ["RESET_URL"]
        assert event["unexpected"] == ["RESET"]

    async def test_resend_rechaza(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mode(monkeypatch, "resend")
        with respx.mock() as mock, structlog.testing.capture_logs() as logs:
            mock.post(RESEND_URL).mock(
                return_value=httpx.Response(422, json={"message": "template not published"})
            )
            ok = await send_template(
                EmailKind.PASSWORD_RESET, to="a@b.com", subject="s", variables={"RESET_URL": _RESET}
            )
        assert ok is False
        [event] = _events(logs, "email.send_failed")
        assert event["status"] == 422
        assert event["kind"] == "password_reset"
        assert event["template"] == "auphere-password-reset-es"
        assert "template not published" in event["body"]

    async def test_sin_clave_real_no_envia(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mode(monkeypatch, "resend", key="dev-resend-key-change-me")
        with respx.mock(assert_all_called=False) as mock, structlog.testing.capture_logs() as logs:
            route = mock.post(RESEND_URL)
            ok = await send_template(
                EmailKind.PASSWORD_RESET, to="a@b.com", subject="s", variables={"RESET_URL": _RESET}
            )
        assert ok is False
        assert not route.called
        assert _events(logs, "email.not_configured")

    async def test_un_correo_sin_negocio_lo_dice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mode(monkeypatch, "log")
        with structlog.testing.capture_logs() as logs:
            await send_template(
                EmailKind.PASSWORD_RESET, to="a@b.com", subject="s", variables={"RESET_URL": _RESET}
            )
        [event] = _events(logs, "email.suppressed")
        assert event["owner"] == "none"
        assert "partner_id" not in event
