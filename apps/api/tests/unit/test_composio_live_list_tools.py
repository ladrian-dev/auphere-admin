"""El cliente real de Composio lee las herramientas del esquema crudo.

``composio.tools.get()`` no devuelve los modelos del catálogo: devuelve las
herramientas ya envueltas para el proveedor por defecto (OpenAI), que son
diccionarios ``{"type": "function", "function": {"name": …}}``. Leerlos con
``getattr`` daba ``slug=""`` en todas, ``_drop_blank_tools`` las descartaba y
un Google Calendar o un Calendly recién conectados se quedaban sin ninguna
herramienta (producción, 2026-10-22: ``dropped_blank_tools`` 20 de 20 en los
dos). ``get_raw_composio_tools`` devuelve el modelo con ``slug`` y existe en
la versión del lock (0.13) y en la que resolvía la imagen (0.28).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from nexus_api.services.connectors.composio_client import LiveComposioClient


def _raw_tool(slug: str, *, tags: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        slug=slug,
        name=slug.replace("_", " ").title(),
        description=f"desc {slug}",
        input_parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        output_parameters={"type": "object"},
        scopes=["https://www.googleapis.com/auth/calendar"],
        tags=tags,
    )


class _Tools:
    def __init__(self) -> None:
        self.raw_calls: list[dict[str, Any]] = []

    def get(self, **_: Any) -> list[dict[str, Any]]:
        # Lo que devuelve el proveedor OpenAI del SDK: diccionarios.
        return [
            {"type": "function", "function": {"name": "GOOGLECALENDAR_LIST_EVENTS"}},
            {"type": "function", "function": {"name": "GOOGLECALENDAR_CREATE_EVENT"}},
        ]

    def get_raw_composio_tools(self, **kwargs: Any) -> list[SimpleNamespace]:
        self.raw_calls.append(kwargs)
        return [
            _raw_tool("GOOGLECALENDAR_LIST_EVENTS", tags=["readOnlyHint"]),
            _raw_tool("GOOGLECALENDAR_CREATE_EVENT", tags=[]),
        ]


def _client() -> tuple[LiveComposioClient, _Tools]:
    tools = _Tools()
    client = object.__new__(LiveComposioClient)
    client._client = SimpleNamespace(tools=tools)
    return client, tools


async def test_las_herramientas_llegan_con_su_slug() -> None:
    client, _ = _client()
    got = await client.list_tools(user_id="tenant-x", toolkit="googlecalendar")
    assert [t.slug for t in got] == ["GOOGLECALENDAR_LIST_EVENTS", "GOOGLECALENDAR_CREATE_EVENT"]
    assert got[0].description == "desc GOOGLECALENDAR_LIST_EVENTS"
    assert got[0].input_schema["properties"] == {"q": {"type": "string"}}
    assert got[0].scopes == ["https://www.googleapis.com/auth/calendar"]


async def test_las_etiquetas_de_lista_sirven_para_las_anotaciones() -> None:
    """Composio manda las etiquetas como lista; ``_derive_annotations`` las
    consulta como mapa (``"readOnlyHint" in tags`` y ``tags.get``)."""
    client, _ = _client()
    got = await client.list_tools(user_id="tenant-x", toolkit="googlecalendar")
    assert got[0].raw_tags == {"readOnlyHint": True}
    assert got[1].raw_tags == {}


async def test_pide_el_toolkit_y_respeta_el_limite() -> None:
    client, tools = _client()
    await client.list_tools(user_id="tenant-x", toolkit="calendly", limit=50)
    assert tools.raw_calls == [{"toolkits": ["calendly"], "limit": 50}]
