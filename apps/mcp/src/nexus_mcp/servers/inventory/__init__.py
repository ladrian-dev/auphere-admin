"""Inventory MCP server — ``inventory.*`` tools over a product catalogue.

The tools are the stable contract; **where the rows come from is not**.
Two backends implement the same row shape and the same
``search_products(query) -> (rows, truncated)`` call:

- ``servers.amigable_venta`` — the Amigable Venta POS REST API.
- ``servers.catalogo_local`` — a catalogue held in Postgres, loaded from a
  spreadsheet. Used while the upstream API has no data.

Which one answers is decided per tenant by which connector is installed
(see ``_resolve_backend``), so swapping the source is an operator action,
not a code change. Powers the ``inventario_v1`` vertical.
"""
