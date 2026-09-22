"""El código de emparejamiento no existe — spec 012, Requisito 6.1.

**Esto se comprueba buscando, no confiando en haberlo borrado.** R6.1 afirma que
algo *no* está, y esa clase de requisito solo se prueba barriendo: un fichero
que se quedó, un endpoint que sigue registrado o una constante duplicada en otro
lenguaje no aparecen en ningún test de comportamiento, porque nadie los llama.

Es la lección que dejó `test_37_customer_axis_contract.py`: aquel barrido
encontró el mismo defecto en un servidor donde nadie había mirado, y lo encontró
**porque recorría** en vez de enumerar los sitios conocidos.

Lo que se retira es la ceremonia, no sus propiedades. Uso único, hash, rechazo
indistinguible y techo de intentos siguen aplicando al registro por sesión
(R7) — eso lo prueban sus tests, no éste.
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = [pytest.mark.isolation]

REPO = pathlib.Path(__file__).resolve().parents[4]

#: Lo que no puede quedar en ningún sitio del producto.
#:
#: **La segunda tanda la trajo un fallo del propio barrido.** La primera lista
#: eran nombres de símbolos, y por eso dejó viva la otra punta del cable: el
#: escritorio seguía trayendo un cliente de ``POST /device/pair`` —endpoint que
#: ya no existe— con su clase de error y sus dos códigos, porque ningún símbolo
#: de la lista aparecía en ese fichero. Se caza con la **ruta**, no con el
#: nombre: la ruta es lo que R6.1 dice que no existe, y es la única cadena que
#: los dos extremos comparten obligatoriamente.
GONE = (
    "DevicePairingCodeRepository",
    "DevicePairingCode",
    "PairingCodeOut",
    "issuePairingCode",
    "issuePairingCodeAction",
    "app:workstation.pair",
    "/device/pair",
    "PairingFailed",
    "pairing_code_invalid",
    "pairing_rate_limited",
    # La etiqueta del botón, no la palabra. Dos comentarios dejan constancia de
    # que `introducir_codigo` se retiró, y esa constancia es lo que quiere el
    # §IX; lo que no puede quedar es la **clave de i18n**, porque una clave con
    # texto detrás es un botón que alguien puede volver a pintar sin darse
    # cuenta de que no lleva a ninguna parte.
    "workstation.action.introducir_codigo",
)

#: El alfabeto tenía **tres** copias sin constante compartida —dos en TypeScript
#: y una en Python—, que es justo la forma que tiene un resto de sobrevivir a una
#: búsqueda parcial. No desaparece, porque los códigos de sesión de la spec 009
#: lo siguen usando; lo que desaparece es la duplicación.
ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"

#: Dónde se busca. Las migraciones quedan fuera a propósito: la que creó la
#: tabla es historia y no se reescribe, y la que la borra tiene que nombrarla.
ROOTS = (
    "apps/api/src",
    "apps/console/src",
    "apps/desktop/src",
)

SUFFIXES = {".py", ".ts", ".tsx", ".yaml", ".yml"}


def _files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for root in ROOTS:
        base = REPO / root
        assert base.is_dir(), f"{root} no existe: ¿se movió el árbol?"
        out.extend(p for p in base.rglob("*") if p.suffix in SUFFIXES and p.is_file())
    return out


def test_the_sweep_actually_sweeps_something() -> None:
    """Un barrido sobre una lista vacía pasa siempre."""
    files = _files()
    assert len(files) > 300, f"solo {len(files)} ficheros; el barrido no está mirando el árbol"


@pytest.mark.parametrize("needle", GONE)
def test_no_trace_of_the_pairing_code_survives(needle: str) -> None:
    hits: list[str] = []
    for path in _files():
        try:
            if needle in path.read_text(encoding="utf-8"):
                hits.append(str(path.relative_to(REPO)))
        except (UnicodeDecodeError, OSError):
            continue
    assert not hits, f"queda «{needle}» en: {hits}"


def test_the_alphabet_lives_in_exactly_one_place() -> None:
    """Una sola definición, y en el módulo que la posee.

    El barrido descubrió que ``core/pairing_codes.py`` **no era del
    emparejamiento**: los códigos de sesión de la spec 009 usaban el mismo
    generador, y borrarlo habría roto el inicio de sesión. Se quedó, renombrado
    a lo que hace —``one_time_codes``— en vez de a quién lo estrenó.
    """
    owners = [
        str(p.relative_to(REPO))
        for p in _files()
        if ALPHABET in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert owners == ["apps/api/src/nexus_api/core/one_time_codes.py"], (
        f"el alfabeto vive en {owners}; tiene que vivir en un solo sitio"
    )
