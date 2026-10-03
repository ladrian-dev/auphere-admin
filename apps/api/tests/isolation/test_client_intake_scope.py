"""Garantía de aislamiento — el alta de un cliente (spec 019).

Esta spec **reordena** el alta: la plantilla pasa delante, el paso de canal
desaparece y el Companion entra a redactar el borrador. No añade ninguna ruta,
y por eso mismo conviene la barrida: lo que no cambia de código puede cambiar
de significado cuando cambia quién lo llama.

Dos afirmaciones, una por tarea:

- **T004** — ninguna de las rutas que el alta usa deja que el llamante diga a
  qué partner o a qué tenant apunta. El destino sale del token, no del cuerpo.
- **T005** — el camino por el que el Companion *propone* no puede escribir. Es
  la capa 2 del aislamiento (CO-02 §5) y R5.4 la declara intacta; sin este test
  la declaración es una intención.

Lo que ya está cubierto en otro sitio **no se repite aquí**:
``test_console_scope.py`` barre estructuralmente todo ``/console/*``, y
``test_companion_action_guarantees.py`` fija que ``console.apply`` es la única
herramienta que escribe y que ninguna propuesta acepta un ``tenant_id``. Este
fichero añade el ángulo que aquéllos no pueden saber: **cuáles son las rutas
del alta** y **qué significa crear un cliente** dentro de este catálogo.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.routing import APIRoute

from nexus_api.companion.tools.catalog import ALL_TOOLS
from nexus_api.companion.tools.proposals import APPLY_ROUTES
from nexus_api.main import app
from nexus_api.services.partner_clients import provision_partner_client

pytestmark = [pytest.mark.isolation]

#: Las rutas que el alta recorre, en orden: leer el catálogo, comprobar que la
#: referencia está libre, crear, y escribir el agente desde la plantilla.
#: Escritas a mano a propósito — si el alta empieza a llamar a otra, esta lista
#: deja de describirla y alguien tiene que venir a mirar.
RUTAS_DEL_ALTA = [
    ("get", "/console/seed-templates"),
    ("get", "/console/clients/{ref}"),
    ("post", "/console/clients"),
    ("post", "/console/clients/{ref}/agent/from-seed"),
]

PROHIBIDOS = {"tenant_id", "partner_id", "tenant", "partner"}


def test_las_rutas_del_alta_estan_montadas() -> None:
    """Si una deja de existir, el resto del fichero pasaría por vacío."""
    montadas = {
        (m.lower(), r.path) for r in app.routes if isinstance(r, APIRoute) for m in r.methods
    }
    faltan = [ruta for ruta in RUTAS_DEL_ALTA if ruta not in montadas]
    assert not faltan, f"el alta llama a rutas que no existen: {faltan}"


def test_ninguna_ruta_del_alta_acepta_un_destino() -> None:
    """El partner sale del token y el tenant lo crea el servidor.

    Se lee del OpenAPI publicado y no de los internos de FastAPI: el esquema
    es lo que un llamante ve, y no cambia de forma entre versiones de pydantic.
    """
    spec = app.openapi()
    for metodo, path in RUTAS_DEL_ALTA:
        op = spec["paths"][path][metodo]
        nombres = {p["name"] for p in op.get("parameters", [])}
        assert not (nombres & PROHIBIDOS), f"{metodo} {path} acepta {nombres & PROHIBIDOS}"
        ref = (
            op.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )
        if not ref:
            continue
        modelo = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
        campos = set(modelo.get("properties", {}))
        assert not (campos & PROHIBIDOS), (
            f"{metodo} {path} acepta en el cuerpo {campos & PROHIBIDOS}"
        )


def test_crear_un_cliente_recibe_el_partner_ya_resuelto() -> None:
    """``provision_partner_client`` toma el **objeto** partner, no su id.

    La diferencia no es de estilo: un ``partner_id: UUID`` es un argumento que
    alguien puede rellenar desde el cuerpo de una petición, y un ``Partner`` ya
    cargado solo puede venir de quien lo autenticó. La firma es el sitio donde
    esa distinción se puede fijar.
    """
    firma = inspect.signature(provision_partner_client)
    assert "partner" in firma.parameters
    assert "partner_id" not in firma.parameters
    assert "tenant_id" not in firma.parameters


def test_ninguna_herramienta_alcanza_la_creacion_por_su_cuenta() -> None:
    """La capa 2, dicha desde esta spec.

    El Companion redacta el borrador del alta leyendo ``console.list_templates``
    y proponiendo; **crear** sigue siendo un clic del partner.

    La ruta sola no basta para afirmarlo: ``console.list_clients`` apunta a
    ``/console/clients`` igual que la creación, y es una lectura — lo que las
    separa es el método. Y «todas leen con GET» tampoco es cierto: hay dos que
    salen con POST y ninguna de las dos escribe configuración.

      - ``companion.run_playground_turn`` prueba un turno en el Playground
        (clase ``trial``): gasta, pero no deja nada puesto.
      - ``shell_local`` ejecuta en la máquina del partner (spec 003, clase
        ``machine``) y pregunta siempre.

    Escritas a mano: si aparece una tercera, este test se pone rojo en vez de
    encogerse en silencio.
    """
    con_post = sorted(t.name for t in ALL_TOOLS if t.method != "GET")
    assert con_post == ["companion.run_playground_turn", "shell_local"], con_post

    creacion = APPLY_ROUTES["client"][1]
    alcanzan = sorted(t.name for t in ALL_TOOLS if t.path == creacion)
    assert alcanzan == ["console.list_clients"], (
        f"alguien más apunta a {creacion}: {alcanzan}. Si es una lectura nueva, "
        "añádela aquí a conciencia; si escribe, no debería existir"
    )
    assert next(t for t in ALL_TOOLS if t.name == "console.list_clients").method == "GET"


def test_crear_un_cliente_se_aplica_por_la_puerta_que_pregunta() -> None:
    """El ``kind`` «client» aplica exactamente la ruta del alta, y la única
    herramienta que puede aplicarlo exige confirmación.

    Las dos mitades importan. Que la ruta sea ésa evita que «crear un cliente»
    signifique otra cosa mañana; que la puerta pregunte es lo que mantiene el
    clic del lado del partner.
    """
    assert APPLY_ROUTES["client"] == ("POST", "/console/clients")
    aplicadoras = [t for t in ALL_TOOLS if t.tool_class == "mutates"]
    assert [t.name for t in aplicadoras] == ["console.apply"]
    assert aplicadoras[0].permission_policy == "always_ask"
