"""Preguntar si Google está disponible **no puede crear nada** (spec 006, R5.6).

Este fichero existe por un fallo real. El botón «Continuar con Google» decidía
si pintarse llamando a ``/console/auth/google/start``, que es el endpoint que
**empieza** un inicio de sesión: acuña un par PKCE y lo guarda en Redis con
diez minutos de vida. Como el botón preguntaba al montar y volvía a llamar al
pulsar, cada visita a ``/login`` —que es una página pública— dejaba una clave
en Redis que nadie iba a consumir jamás.

No era una fuga de seguridad; era una pregunta implementada con un verbo que
escribe. La corrección es un endpoint que sólo responde.

**La aserción que de verdad vigila esto es la de Redis, no la del cuerpo.**
Un `available` correcto seguiría siendo correcto si mañana alguien lo
implementara otra vez sobre ``/start``. Lo que no sobreviviría a eso es
«después de preguntar, Redis sigue vacío».
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_api.config import get_settings
from tests.conftest import mint_console_token

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_PKCE_KEYS = "oauth:pkce:*"


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


@pytest.fixture
def _google_off(monkeypatch: pytest.MonkeyPatch) -> Any:
    s = get_settings()
    for name in ("google_client_id", "google_client_secret", "google_redirect_uri"):
        monkeypatch.setattr(s, name, "", raising=False)
    yield


class TestPreguntarNoEscribe:
    async def test_preguntar_no_deja_nada_en_redis(
        self, client: Any, fake_redis: Any, _google_on: Any
    ) -> None:
        """**El test de esta corrección.** Se pone rojo si alguien vuelve a
        implementar la disponibilidad sobre un endpoint que acuña PKCE."""
        assert await fake_redis.keys(_PKCE_KEYS) == []

        r = await client.get("/console/auth/google/available", headers=_svc())

        assert r.status_code == 200
        assert await fake_redis.keys(_PKCE_KEYS) == [], (
            "preguntar si Google está disponible ha acuñado un PKCE que nadie consumirá"
        )

    async def test_el_contraste_start_si_escribe(
        self, client: Any, fake_redis: Any, _google_on: Any
    ) -> None:
        """La otra mitad de la pinza: si ``/start`` dejara de escribir, el test
        de arriba pasaría por vacuidad y no vigilaría nada."""
        r = await client.post(
            "/console/auth/google/start", json={"intent": "login"}, headers=_svc()
        )

        assert r.status_code == 200
        assert len(await fake_redis.keys(_PKCE_KEYS)) == 1

    async def test_preguntar_diez_veces_sigue_sin_dejar_nada(
        self, client: Any, fake_redis: Any, _google_on: Any
    ) -> None:
        """`/login` es pública: lo que importa no es una visita, es el goteo."""
        for _ in range(10):
            assert (
                await client.get("/console/auth/google/available", headers=_svc())
            ).status_code == 200
        assert await fake_redis.keys(_PKCE_KEYS) == []


class TestLaRespuesta:
    async def test_configurado_es_disponible(self, client: Any, _google_on: Any) -> None:
        r = await client.get("/console/auth/google/available", headers=_svc())
        assert r.json() == {"available": True}

    async def test_sin_configurar_no_es_un_error(self, client: Any, _google_off: Any) -> None:
        """**200 con `false`, no 503.** Preguntar «¿hay Google?» y que no lo
        haya es una respuesta, no un fallo: el alta con contraseña sigue
        funcionando (CE-006) y la consola necesita distinguir «no hay» de «no
        se pudo preguntar»."""
        r = await client.get("/console/auth/google/available", headers=_svc())
        assert r.status_code == 200
        assert r.json() == {"available": False}

    async def test_google_a_medias_no_es_disponible(
        self, client: Any, monkeypatch: pytest.MonkeyPatch, _google_on: Any
    ) -> None:
        """Con dos de tres, el botón NO debe pintarse: el canje fallaría con un
        error del proveedor que no se parece a la causa."""
        monkeypatch.setattr(get_settings(), "google_client_secret", "", raising=False)
        r = await client.get("/console/auth/google/available", headers=_svc())
        assert r.json() == {"available": False}


class TestSigueDetrasDelTokenDeServicio:
    async def test_sin_token_401(self, client: Any, _google_on: Any) -> None:
        """ADR-032: el borde BFF ↔ API nunca es anónimo, tampoco para una
        pregunta barata."""
        r = await client.get("/console/auth/google/available")
        assert r.status_code == 401
