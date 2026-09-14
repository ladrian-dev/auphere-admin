"""Cuando el correo NO sale, no se puede decir que salió — spec 006, R1.1.

Encontrado en staging, no en el repositorio. El dominio no estaba verificado en
el proveedor, que devolvió `403 The auphere.com domain is not verified`, y la
API respondió **202 «revisa tu correo»** igual. La persona lee que hay un enlace
esperando, no llega nada, y el único rastro es una línea de log.

**La respuesta sigue sin delatar qué correos existen.** Que el proveedor rechace
no depende de la dirección: le pasa a todas por igual, así que fallar en voz
alta no abre el oráculo que `CE-004` cierra — y este fichero lo comprueba
pidiendo las dos altas y exigiendo la misma respuesta.

Hay una distinción que sí importa:

- **Sin proveedor configurado** (desarrollo) → 202. No es una avería, es una
  decisión de despliegue: ese entorno no manda correo y nunca prometió hacerlo.
- **Con proveedor configurado que rechaza** → 502. Eso es una avería, y
  callársela convierte el alta en un callejón sin salida silencioso.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_api.config import get_settings
from tests.conftest import mint_console_token

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _svc(ip: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {mint_console_token(user_id='bff', partner_id=None, service=True)}",
        "X-Nexus-Client-IP": ip,
    }


@pytest.fixture(autouse=True)
def _signup_on(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(get_settings(), "signup_enabled", True, raising=False)
    yield


def _provider_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proveedor configurado que dice que no — el 403 real de staging."""
    monkeypatch.setattr(get_settings(), "resend_api_key", "re_una_clave_de_verdad", raising=False)

    async def _fake(**_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr("nexus_api.services.email.send_email", _fake)


def _no_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entorno sin correo: el propio `send_email` avisa y devuelve False."""
    monkeypatch.setattr(get_settings(), "resend_api_key", "", raising=False)

    async def _fake(**_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr("nexus_api.services.email.send_email", _fake)


class TestUnCorreoQueNoSaleNoSeAnunciaComoEnviado:
    async def test_el_proveedor_rechaza_y_la_api_no_dice_que_lo_mando(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _provider_refuses(monkeypatch)
        r = await client.post(
            "/console/signup",
            json={"email": f"nadie-{uuid.uuid4().hex[:8]}@agencia.com"},
            headers=_svc("203.0.113.40"),
        )
        assert r.status_code != 202, "202 aquí es prometer un enlace que no existe"
        assert r.status_code == 502

    async def test_fallar_en_voz_alta_no_delata_que_correos_existen(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**La prueba que sostiene que este cambio es seguro.**

        Si el fallo dependiera de la dirección, contarlo abriría el oráculo. No
        depende: el proveedor rechaza igual a todas.
        """
        from nexus_api.services import console_identity

        ya = f"ya-{uuid.uuid4().hex[:8]}@agencia.com"
        await console_identity.create_account(
            db_session, email=ya, password="una-contrasena-larga", display_name=None
        )
        await db_session.commit()
        _provider_refuses(monkeypatch)

        r_ya = await client.post(
            "/console/signup", json={"email": ya}, headers=_svc("203.0.113.41")
        )
        r_nuevo = await client.post(
            "/console/signup",
            json={"email": f"nuevo-{uuid.uuid4().hex[:8]}@agencia.com"},
            headers=_svc("203.0.113.42"),
        )
        assert r_ya.status_code == r_nuevo.status_code
        assert r_ya.json() == r_nuevo.json(), "el cuerpo delata si el correo existe"

    async def test_sin_proveedor_configurado_sigue_siendo_202(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un entorno sin correo no es un entorno averiado. Si esto diera 502,
        el desarrollo local no podría ni abrir el formulario."""
        _no_provider(monkeypatch)
        r = await client.post(
            "/console/signup",
            json={"email": f"dev-{uuid.uuid4().hex[:8]}@agencia.com"},
            headers=_svc("203.0.113.43"),
        )
        assert r.status_code == 202
