"""Volver a donde ibas tras entrar con Google — spec 009, fallo 1.

**Este fichero existe por un fallo que se coló con la spec 009 entera escrita.**

El camino de correo y contraseña conservaba el destino (`LoginForm` recibe
`redirectTo`), así que era fácil suponer que el de Google también. No lo hacía:
los parámetros del callback los pone **Google**, que devuelve `code` y `state` y
nada más. El destino se perdía en el botón, y la aplicación de escritorio se
quedaba esperando en su puerto hasta caducar.

**El destino viaja dentro del `state` firmado**, que es donde RFC 6749 §10.12
dice que va: el callback no tiene sesión, y el `state` es lo único que llega
firmado por nosotros. Si viajara en la URL, cualquiera podría cambiarlo por el
suyo — que es un redirector abierto con pasos extra.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from nexus_api.config import get_settings
from nexus_api.services.oauth_state import sign_state, verify_state
from tests.conftest import mint_console_token

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _svc() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {mint_console_token(user_id='bff', partner_id=None, service=True)}"
    }


@pytest.fixture
def _google_on(monkeypatch: pytest.MonkeyPatch) -> Any:
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "123.apps.googleusercontent.com", raising=False)
    monkeypatch.setattr(s, "google_client_secret", "un-secreto", raising=False)
    monkeypatch.setattr(
        s, "google_redirect_uri", "https://console.auphere.com/auth/google/callback", raising=False
    )
    yield


SECRET = "un-secreto-de-prueba-que-no-se-usa-en-ningun-sitio"


def test_el_destino_de_vuelta_viaja_firmado_en_el_state() -> None:
    destino = "/desktop-auth?redirect_uri=http%3A%2F%2F127.0.0.1%3A5000%2F&state=abc"
    state, _ = sign_state(claims={"i": "login", "r": destino}, secret=SECRET)
    payload = verify_state(state=state, secret=SECRET)
    assert payload.claims["r"] == destino


def test_cambiar_el_destino_invalida_la_firma() -> None:
    """Lo que impide que esto sea un redirector abierto."""
    state, _ = sign_state(claims={"i": "login", "r": "/desktop-auth?x=1"}, secret=SECRET)
    cuerpo, firma = state.split(".", 1)
    # Se manipula el payload dejando la firma intacta.
    import base64
    import json

    crudo = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    crudo["r"] = "https://malo.example/"
    falso = base64.urlsafe_b64encode(json.dumps(crudo).encode()).decode().rstrip("=")

    from nexus_api.services.oauth_state import OAuthStateInvalid

    with pytest.raises(OAuthStateInvalid):
        verify_state(state=f"{falso}.{firma}", secret=SECRET)


def test_sin_destino_el_state_sigue_valiendo() -> None:
    """El camino normal —entrar en la consola, no en la app— no cambia."""
    state, _ = sign_state(claims={"i": "login"}, secret=SECRET)
    payload = verify_state(state=state, secret=SECRET)
    assert payload.claims.get("r") is None


class TestLasRutas:
    """**Lo que de verdad faltaba.** Los tres de arriba prueban el mecanismo del
    `state`, que ya existía; éstos prueban que `/start` lo usa y que el callback
    lo devuelve. Sin ellos, el mecanismo funciona y la función no."""

    async def test_start_mete_el_destino_en_el_state(self, client: Any, _google_on: Any) -> None:
        destino = "/desktop-auth?redirect_uri=http%3A%2F%2F127.0.0.1%3A5000%2F&state=abc"
        r = await client.post(
            "/console/auth/google/start",
            headers=_svc(),
            json={"intent": "login", "return_to": destino},
        )
        assert r.status_code == 200, r.text
        # El `state` de la URL de Google tiene que llevarlo dentro, firmado.
        state = parse_qs(urlparse(r.json()["authorization_url"]).query)["state"][0]
        payload = verify_state(state=state, secret=get_settings().connector_consent_secret)
        assert payload.claims["r"] == destino

    async def test_start_rechaza_un_destino_que_no_es_una_ruta(
        self, client: Any, _google_on: Any
    ) -> None:
        """Si aceptara `https://malo.example/`, el callback se convertiría en un
        redirector abierto con la firma **a favor** del atacante."""
        for malo in ("https://malo.example/", "//malo.example/", "/\\malo.example"):
            r = await client.post(
                "/console/auth/google/start",
                headers=_svc(),
                json={"intent": "login", "return_to": malo},
            )
            assert r.status_code == 422, f"{malo} → {r.status_code}"

    async def test_sin_destino_start_sigue_funcionando(self, client: Any, _google_on: Any) -> None:
        r = await client.post(
            "/console/auth/google/start", headers=_svc(), json={"intent": "login"}
        )
        assert r.status_code == 200, r.text
