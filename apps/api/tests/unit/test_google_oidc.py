"""La verificación del `id_token` de Google — spec 006, Requisito 5.

**El criterio que sostiene todo lo demás es `email_verified`.** Google emite un
`id_token` con un correo para cualquier cuenta, verificada o no. Si no se mira
esa bandera, cualquiera puede crear una cuenta de Google con el correo de otra
persona, no verificarlo, y llegar aquí con una identidad ajena. Por eso el test
del `email_verified` es el primero del fichero y no un caso límite.

Lo demás son las cuatro comprobaciones que un `id_token` necesita siempre:
emisor, audiencia, caducidad y firma. Se prueban con una clave propia generada
en la prueba, no contra Google: lo que se vigila es **nuestro verificador**.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from nexus_api.services.google_oidc import (
    EmailNotVerified,
    GoogleIdentityError,
    pkce_pair,
    verify_id_token,
)

CLIENT_ID = "123456.apps.googleusercontent.com"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(key: Any = _KEY, **overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1087654321098765432",
        "email": "maria@agencia.com",
        "email_verified": True,
        "exp": now + 600,
        "iat": now,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


def _verify(token: str, **kw: Any) -> Any:
    """El verificador, con la clave pública inyectada en vez de ir al JWKS."""
    return verify_id_token(
        token, client_id=CLIENT_ID, key_resolver=lambda _t: _KEY.public_key(), **kw
    )


class TestElCorreoSinVerificarNoVale:
    def test_email_verified_false_se_rechaza(self) -> None:
        with pytest.raises(EmailNotVerified):
            _verify(_token(email_verified=False))

    def test_email_verified_ausente_se_rechaza(self) -> None:
        """Ausente no es «probablemente sí». Un proveedor que deja de mandar la
        bandera no debe convertirse en un proveedor que verifica."""
        payload = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "sub": "1",
            "email": "x@y.com",
            "exp": int(time.time()) + 600,
        }
        with pytest.raises(EmailNotVerified):
            _verify(jwt.encode(payload, _KEY, algorithm="RS256"))

    def test_la_cadena_texto_false_tampoco_cuela(self) -> None:
        """Google ha mandado históricamente `"true"`/`"false"` como texto en
        algunos flujos. `"false"` es una cadena no vacía y sería *verdadera*
        en una comprobación ingenua."""
        with pytest.raises(EmailNotVerified):
            _verify(_token(email_verified="false"))

    def test_el_correo_verificado_pasa(self) -> None:
        identidad = _verify(_token())
        assert identidad.email == "maria@agencia.com"
        assert identidad.subject == "1087654321098765432"


class TestLasCuatroComprobacionesDeSiempre:
    def test_otro_emisor_se_rechaza(self) -> None:
        with pytest.raises(GoogleIdentityError):
            _verify(_token(iss="https://accounts.evil.com"))

    def test_los_dos_emisores_legitimos_de_google_valen(self) -> None:
        """Google usa `accounts.google.com` y `https://accounts.google.com`.
        Aceptar sólo uno rompería en producción de forma intermitente."""
        for iss in ("accounts.google.com", "https://accounts.google.com"):
            assert _verify(_token(iss=iss)).subject

    def test_otra_audiencia_se_rechaza(self) -> None:
        """Un `id_token` emitido para OTRA aplicación es válido y está firmado
        por Google: sin comprobar `aud`, serviría para entrar aquí."""
        with pytest.raises(GoogleIdentityError):
            _verify(_token(aud="otra-app.apps.googleusercontent.com"))

    def test_caducado_se_rechaza(self) -> None:
        # Más allá de la tolerancia de reloj: con 10 s no bastaba, y eso es
        # correcto — un margen pequeño existe para el desfase entre máquinas.
        with pytest.raises(GoogleIdentityError):
            _verify(_token(exp=int(time.time()) - 300))

    def test_hay_tolerancia_de_reloj_pero_es_pequena(self) -> None:
        """Un margen para el desfase entre relojes es correcto; uno grande
        convierte «caducado» en una sugerencia. Se fija el techo aquí para que
        nadie lo suba a una hora sin que nada se entere."""
        import inspect

        from nexus_api.services.google_oidc import verify_id_token as fn

        defecto = inspect.signature(fn).parameters["leeway_seconds"].default
        assert 0 < defecto <= 60, f"tolerancia de {defecto}s: demasiado"
        # Y dentro del margen, un token recién caducado sigue valiendo.
        assert _verify(_token(exp=int(time.time()) - 5)).subject

    def test_firmado_con_otra_clave_se_rechaza(self) -> None:
        with pytest.raises(GoogleIdentityError):
            _verify(
                jwt.encode({"iss": "https://accounts.google.com"}, _OTHER_KEY, algorithm="RS256")
            )

    def test_sin_firma_se_rechaza(self) -> None:
        """`alg: none` es el ataque clásico contra un verificador perezoso.

        **El token va COMPLETO a propósito.** Con uno al que le falten claims,
        esta prueba pasaría por el motivo equivocado —la lista de obligatorios—
        y seguiría verde aunque alguien añadiera `none` a los algoritmos
        aceptados. Lo descubrió una comprobación por mutación.
        """
        now = int(time.time())
        completo = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "sub": "1087654321098765432",
            "email": "maria@agencia.com",
            "email_verified": True,
            "exp": now + 600,
            "iat": now,
        }
        with pytest.raises(GoogleIdentityError):
            _verify(jwt.encode(completo, key="", algorithm="none"))

    def test_confusion_de_algoritmos_hs256_se_rechaza(self) -> None:
        """**El ataque que la lista de algoritmos existe para parar.**

        La clave pública de Google es pública. Si el verificador aceptara
        HS256, un atacante podría firmar un token con esa clave pública **como
        secreto compartido** y el verificador lo daría por bueno: el mismo
        material sirve de clave pública para RS256 y de secreto HMAC.

        El token se forja **a mano**, no con ``jwt.encode``: pyjwt se niega a
        crear un HS256 con una clave asimétrica, lo cual está muy bien pero no
        es lo que hace un atacante. Lo que aquí se prueba es *nuestro*
        verificador, no la prudencia de la librería al escribir.

        `alg: none` no prueba esto — pyjwt ya lo rechaza por su cuenta cuando
        se le pasa una clave. Lo descubrió una comprobación por mutación.
        """
        import hashlib
        import hmac as _hmac
        import json as _json

        from cryptography.hazmat.primitives import serialization

        pem = _KEY.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        def b64(raw: bytes) -> bytes:
            import base64 as _b64

            return _b64.urlsafe_b64encode(raw).rstrip(b"=")

        now = int(time.time())
        header = b64(_json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        payload = b64(
            _json.dumps(
                {
                    "iss": "https://accounts.google.com",
                    "aud": CLIENT_ID,
                    "sub": "1087654321098765432",
                    "email": "victima@agencia.com",
                    "email_verified": True,
                    "exp": now + 600,
                }
            ).encode()
        )
        firmable = header + b"." + payload
        firma = b64(_hmac.new(pem, firmable, hashlib.sha256).digest())
        forjado = (firmable + b"." + firma).decode("ascii")

        with pytest.raises(GoogleIdentityError):
            _verify(forjado)


class TestPkce:
    def test_el_reto_no_es_el_verificador(self) -> None:
        """Si el `code_challenge` fuera el verificador en claro, PKCE no
        protegería de nada: quien intercepte el redirect tendría los dos."""
        verifier, challenge = pkce_pair()
        assert verifier != challenge
        assert len(verifier) >= 43, "RFC 7636 pide entre 43 y 128 caracteres"

    def test_dos_pares_son_distintos(self) -> None:
        assert pkce_pair()[0] != pkce_pair()[0]

    def test_el_reto_es_s256_del_verificador(self) -> None:
        import base64
        import hashlib

        verifier, challenge = pkce_pair()
        esperado = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        assert challenge == esperado
