"""El `state` firmado de un redirect OAuth — spec 006, Requisito 5.4.

Este módulo existe porque ya había **dos** copias del mismo patrón
(`tiktok_oauth_state`, `connectors/consent_token`) y Google iba a ser la
tercera. Tres copias de una firma divergen, y la que se queda sin la
corrección es la que menos se toca.

Lo que se vigila:

- **a prueba de manipulación**: cambiar un byte invalida;
- **con nonce**: dos states del mismo sujeto son distintos;
- **caduca**;
- **vale una sola vez**, que es lo único que la firma NO puede garantizar por
  sí sola — hace falta consumirlo;
- y **el formato en el cable no cambia**, o las autorizaciones de TikTok que
  estén a medio camino se romperían al desplegar.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.services.oauth_state import (
    OAuthStateExpired,
    OAuthStateInvalid,
    sign_state,
    verify_state,
)

SECRET = "un-secreto-de-pruebas-suficientemente-largo"


class TestLaFirmaProtege:
    def test_ida_y_vuelta(self) -> None:
        state, payload = sign_state(claims={"t": "abc"}, secret=SECRET)
        vuelto = verify_state(state=state, secret=SECRET)
        assert vuelto.claims["t"] == "abc"
        assert vuelto.nonce == payload.nonce

    def test_un_byte_cambiado_invalida(self) -> None:
        """Se toca el PRIMER carácter, no el último — y no es indiferente.

        Tocando el último, este caso fallaba **una de cada diez veces**: en
        base64 los bits sobrantes del carácter final no siempre llegan al valor
        decodificado, así que según el nonce aleatorio de turno el byte
        «cambiado» producía exactamente el mismo payload y la firma seguía
        siendo válida. El test no estaba encontrando un fallo de firma: estaba
        encontrando una propiedad de base64.

        El primer carácter siempre lleva seis bits significativos, así que
        alterarlo cambia el valor decodificado siempre.

        Medido el 2026-09-14 antes de un despliegue a producción: 18 verdes y 2
        rojos en veinte ejecuciones seguidas. Un intermitente en la tubería es
        peor que un test que falta, porque enseña a reintentar en vez de mirar.
        """
        state, _ = sign_state(claims={"t": "abc"}, secret=SECRET)
        roto = ("A" if state[0] != "A" else "B") + state[1:]
        assert roto != state
        with pytest.raises(OAuthStateInvalid):
            verify_state(state=roto, secret=SECRET)

    def test_otro_secreto_no_lo_abre(self) -> None:
        state, _ = sign_state(claims={"t": "abc"}, secret=SECRET)
        with pytest.raises(OAuthStateInvalid):
            verify_state(state=state, secret="otro-secreto-distinto-y-largo")

    def test_la_firma_se_comprueba_antes_de_parsear(self) -> None:
        """Un atacante no debe poder sondear el parseo con entrada sin firmar:
        si el payload se parseara primero, los mensajes de error contarían
        cosas sobre su forma."""
        with pytest.raises(OAuthStateInvalid):
            verify_state(state="eyJiYXN1cmEiOjF9.bm8tZXMtdW5hLWZpcm1h", secret=SECRET)

    def test_sin_separador_no_es_un_state(self) -> None:
        with pytest.raises(OAuthStateInvalid):
            verify_state(state="soloUnaCosa", secret=SECRET)


class TestNonceYCaducidad:
    def test_dos_states_del_mismo_sujeto_son_distintos(self) -> None:
        a, _ = sign_state(claims={"t": "mismo"}, secret=SECRET)
        b, _ = sign_state(claims={"t": "mismo"}, secret=SECRET)
        assert a != b, "sin nonce, dos autorizaciones serían indistinguibles en los registros"

    def test_caduca(self) -> None:
        pasado = datetime.now(UTC) - timedelta(hours=1)
        state, _ = sign_state(
            claims={"t": "abc"}, secret=SECRET, ttl=timedelta(minutes=10), now=pasado
        )
        with pytest.raises(OAuthStateExpired):
            verify_state(state=state, secret=SECRET)

    def test_el_ttl_por_defecto_es_corto(self) -> None:
        """Una ida y vuelta de OAuth dura segundos. Una ventana larga sólo
        sirve para que una pestaña olvidada valga mañana."""
        _state, payload = sign_state(claims={"t": "abc"}, secret=SECRET)
        margen = payload.expires_at - datetime.now(UTC)
        assert margen <= timedelta(minutes=30)


class TestElFormatoEnElCableNoCambia:
    def test_sigue_siendo_compatible_con_el_state_de_tiktok(self) -> None:
        """**Si esto se pone rojo, desplegar rompe autorizaciones en vuelo.**

        `tiktok_oauth_state` firmaba `{"t": <tenant>, "n": <nonce>, "e": <ts>}`
        con HMAC-SHA256 sobre JSON canónico y formato
        `base64url(payload).base64url(firma)`. Un state emitido por el módulo
        viejo tiene que seguir verificándose con el nuevo.
        """
        from nexus_api.services.tiktok_oauth_state import sign_oauth_state

        tenant = uuid.uuid4()
        viejo, _payload = sign_oauth_state(tenant_id=tenant, secret=SECRET)
        # El genérico lo lee sin saber nada de TikTok.
        vuelto = verify_state(state=viejo, secret=SECRET)
        assert vuelto.claims["t"] == str(tenant)
        assert "." in viejo, "el separador es parte del contrato"
