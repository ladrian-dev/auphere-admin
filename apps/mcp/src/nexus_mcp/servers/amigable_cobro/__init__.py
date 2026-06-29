"""Amigable Cobro MCP server.

Read-only ``billing.*`` tools over the Amigable Cobro REST API
(accounts-receivable). Auth is per-tenant: ``X-Entity-ID`` + Bearer token
resolved from ``tenant_connectors`` (slug ``amigable_cobro``). Powers the
cobranza_v1 vertical. See ``clients/mouna.md`` in the KB.
"""
