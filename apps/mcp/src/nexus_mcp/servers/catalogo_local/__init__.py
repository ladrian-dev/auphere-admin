"""Local catalogue MCP backend.

Serves the same rows as the Amigable Venta client, but from the
``local_catalog_products`` table instead of an HTTP API. Exists so a tenant
can run the inventory agent on a catalogue imported from a spreadsheet —
either because the upstream API is unavailable, or because the business
does not have one.
"""
