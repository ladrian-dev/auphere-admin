"""De dónde sale la IP que cuenta el limitador — spec 006, Requisito 7.1.

**Por qué este test existe.** `api/console/auth.py` documenta dos cubos de
ritmo independientes, uno por correo y otro por IP, y dice que el segundo
*«frena el barrido de muchas cuentas desde una»*. La IP salía de
`request.client.host`, y detrás del BFF eso es **la IP de Vercel para todo el
mundo**: el cubo «por IP» era en realidad un único cubo global.

Con un formulario de login eso ya era malo. Con un formulario de alta abierto,
que además manda correo, es el vector entero.

Lo que se vigila aquí, en una frase: **que la IP venga de la cabecera que sólo
pone el BFF, y que cuando no venga el sistema lo diga en vez de fingir.**
"""

from __future__ import annotations

from nexus_api.core.client_ip import (
    CLIENT_IP_HEADER,
    SHARED_BUCKET,
    resolve_client_ip,
    storable_client_ip,
)


class TestLaCabeceraManda:
    def test_una_ipv4_valida_se_usa_tal_cual(self) -> None:
        assert resolve_client_ip("203.0.113.7") == "203.0.113.7"

    def test_una_ipv6_valida_tambien(self) -> None:
        assert resolve_client_ip("2001:db8::1") == "2001:db8::1"

    def test_se_recortan_los_espacios(self) -> None:
        assert resolve_client_ip("  203.0.113.7  ") == "203.0.113.7"


class TestSinCabeceraSeDiceQueNoLaHay:
    def test_ausente_cae_al_cubo_unico(self) -> None:
        assert resolve_client_ip(None) == SHARED_BUCKET

    def test_vacia_cae_al_cubo_unico(self) -> None:
        assert resolve_client_ip("") == SHARED_BUCKET
        assert resolve_client_ip("   ") == SHARED_BUCKET

    def test_el_cubo_unico_no_puede_parecer_una_ip(self) -> None:
        # Si el marcador fuera algo como "0.0.0.0", una petición con esa IP
        # real compartiría cubo con todas las que no traen cabecera. El
        # marcador tiene que ser inconfundible.
        assert not SHARED_BUCKET.replace(".", "").replace(":", "").isalnum() or not any(
            c.isdigit() for c in SHARED_BUCKET
        )


class TestUnValorQueNoEsIpNoSeCree:
    """Lo importante no es rechazar basura: es **no confiar** en ella.

    Un valor que no parsea como IP se trata como ausente. Si se aceptara tal
    cual, cualquiera que alcanzase la API podría mandar una cadena distinta en
    cada petición y estrenar un cubo de ritmo cada vez — que es exactamente
    tener el limitador apagado.
    """

    def test_texto_arbitrario_se_trata_como_ausente(self) -> None:
        assert resolve_client_ip("no-soy-una-ip") == SHARED_BUCKET

    def test_una_lista_estilo_x_forwarded_for_se_trata_como_ausente(self) -> None:
        # Esta cabecera la pone el BFF y lleva UNA ip. Si llega una lista, o
        # alguien la está falsificando o el BFF está mal: en los dos casos, no.
        assert resolve_client_ip("203.0.113.7, 70.41.3.18") == SHARED_BUCKET

    def test_un_octeto_imposible_se_trata_como_ausente(self) -> None:
        assert resolve_client_ip("999.999.999.999") == SHARED_BUCKET

    def test_no_se_puede_estrenar_cubo_con_cada_peticion(self) -> None:
        basura = [f"pwned-{i}" for i in range(50)]
        assert {resolve_client_ip(v) for v in basura} == {SHARED_BUCKET}


def test_el_nombre_de_la_cabecera_es_nuestro_no_x_forwarded_for() -> None:
    """`X-Forwarded-For` lo puede poner cualquiera que alcance la API, y obliga
    a adivinar cuántos proxies hay delante. Una cabecera propia, dentro de una
    petición ya firmada con el token de servicio, no la falsifica un tercero."""
    assert CLIENT_IP_HEADER.lower() == "x-nexus-client-ip"


class TestLaIpQueSeGuardaNoEsLaQueSeCuenta:
    """Dos usos, dos funciones, y mezclarlos rompe el login.

    En `console/auth.py` la misma variable alimentaba el limitador **y**
    `ConsoleSession.ip`, que es una columna `INET`. El marcador del cubo único
    no es una IP: guardarlo reventaría el `INSERT` y dejaría a nadie entrar.
    Para almacenar, lo correcto es `NULL`.
    """

    def test_una_ip_real_se_guarda(self) -> None:
        assert storable_client_ip("203.0.113.7") == "203.0.113.7"

    def test_sin_cabecera_se_guarda_nulo_no_el_marcador(self) -> None:
        assert storable_client_ip(None) is None
        assert storable_client_ip("") is None

    def test_basura_se_guarda_nulo(self) -> None:
        assert storable_client_ip("no-soy-una-ip") is None

    def test_nunca_devuelve_el_marcador_del_cubo(self) -> None:
        entradas = [None, "", "   ", "basura", "999.999.999.999", "1.2.3.4, 5.6.7.8"]
        assert SHARED_BUCKET not in {storable_client_ip(v) for v in entradas}
