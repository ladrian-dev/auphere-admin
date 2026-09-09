"""La fuente HTTP del catálogo — Requisito 5.1 y 5.3.

Habla con la API por HTTP: la edición corre en la máquina del partner y no comparte
proceso con el plano de control. Todo lo que pueda fallar en esa llamada tiene que
acabar en `CatalogUnavailable`, porque la alternativa —servir un catálogo a medias—
es exactamente lo que R5.3 prohíbe.
"""

from __future__ import annotations

import json

import pytest

from auphere_edition.catalog import CatalogUnavailable
from auphere_edition.catalog_source import http_catalog_source


def opener_returning(payload, status=200):
    class _Response:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _open(request, timeout=None):
        return _Response()

    return _open


def test_it_maps_the_declared_shape():
    src = http_catalog_source(
        "https://api.example", token="t", opener=opener_returning(
            {"tools": [
                {"name": "console.clients.list", "reaches_network": False},
                {"name": "connector.web.fetch", "reaches_network": True},
            ]}
        )
    )
    tools = {t.name: t.reaches_network for t in src()}
    assert tools == {"console.clients.list": False, "connector.web.fetch": True}


def test_an_undeclared_reach_stays_undeclared():
    """No se rellena con `False`: `None` es lo que hace que R14.2 muerda."""
    src = http_catalog_source(
        "https://api.example", token="t",
        opener=opener_returning({"tools": [{"name": "connector.raro"}]}),
    )
    assert next(iter(src())).reaches_network is None


def test_a_network_failure_is_catalog_unavailable():
    def boom(request, timeout=None):
        raise OSError("sin red")

    src = http_catalog_source("https://api.example", token="t", opener=boom)
    with pytest.raises(CatalogUnavailable):
        src()


def test_a_malformed_document_is_catalog_unavailable():
    """Un cuerpo que no tiene la forma acordada no es un catálogo vacío."""
    src = http_catalog_source(
        "https://api.example", token="t", opener=opener_returning({"cosas": []})
    )
    with pytest.raises(CatalogUnavailable):
        src()


def test_an_entry_without_a_name_invalidates_the_document():
    src = http_catalog_source(
        "https://api.example", token="t",
        opener=opener_returning({"tools": [{"reaches_network": False}]}),
    )
    with pytest.raises(CatalogUnavailable):
        src()
