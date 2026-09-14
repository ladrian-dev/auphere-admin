"""De quién viene el correo del alta — spec 006, R1.1 y research R8.

Visto en staging: el correo de alta salía de `Auphere <facturacion@auphere.com>`.
No por una decisión, sino porque `send_email` cae a `receipt_from_email` cuando
quien llama no pasa remitente, y `receipt_from_email` es el de los recibos.

**El primer correo que recibe alguien que no te conoce no puede venir de
«facturación».** Es incoherente —todavía no hay nada que facturar—, invita a
marcarlo como no deseado, y ensucia la reputación de la dirección que sí tiene
que llegar cuando haya recibos de verdad.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_api.config import get_settings
from nexus_api.services.signup import send_signup_mail

pytestmark = pytest.mark.asyncio


async def _capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def _fake(**kwargs: Any) -> bool:
        seen.update(kwargs)
        return True

    monkeypatch.setattr("nexus_api.services.email.send_email", _fake)
    return seen


class TestElRemitenteDelAlta:
    async def test_no_sale_de_facturacion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen = await _capture(monkeypatch)
        await send_signup_mail(email="maria@agencia.com", token="tok", locale="es")
        # **Se exige que esté puesto, no sólo que no diga «factur».** Sin esta
        # primera aserción el test pasaba por vacío: hoy `from_addr` ni se
        # manda, la cadena queda vacía y «factur» no aparece en la nada.
        assert "from_addr" in seen, "no pasa remitente: hereda el de recibos sin decirlo"
        remitente = str(seen["from_addr"] or "")
        assert "factur" not in remitente.lower(), (
            f"el alta sale de {remitente!r}: todavía no hay nada que facturar"
        )

    async def test_es_un_no_reply_explicito(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explícito y no heredado: si vuelve a heredar el de recibos, este
        test se pone rojo aunque el valor por defecto de aquel cambie."""
        seen = await _capture(monkeypatch)
        await send_signup_mail(email="maria@agencia.com", token="tok", locale="es")
        assert "no-reply@" in str(seen.get("from_addr") or "")

    async def test_el_de_recibos_sigue_siendo_el_de_recibos(self) -> None:
        """No se arregla una cosa rompiendo la de al lado: los recibos **sí**
        vienen de facturación, y eso está bien."""
        assert "factur" in get_settings().receipt_from_email.lower()

    async def test_el_aviso_de_cuenta_existente_usa_el_mismo_remitente(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Los dos correos del alta son el mismo momento para quien los recibe;
        que vinieran de sitios distintos delataría cuál le tocó."""
        seen = await _capture(monkeypatch)
        await send_signup_mail(email="maria@agencia.com", token=None, locale="es")
        assert "no-reply@" in str(seen.get("from_addr") or "")
