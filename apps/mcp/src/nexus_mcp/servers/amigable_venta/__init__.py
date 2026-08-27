"""Amigable Venta backend — REST client for the Amigable Venta POS API.

Read-only access to a business's product catalogue and stock. Auth is
per-tenant: a single ``Authorization: Bearer amk_…`` API key resolved from
``tenant_connectors`` (slug ``amigable_venta``).

The ``inventory.*`` tools that consume this client live in
``servers.inventory`` — this package is one of two interchangeable
backends behind them.
"""
