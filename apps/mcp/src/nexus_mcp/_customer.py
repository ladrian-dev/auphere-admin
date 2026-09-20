"""De quién es el turno — el segundo eje del aislamiento.

`_db.py` resuelve **el negocio** (RLS por tenant). Este módulo resuelve **la
persona**, que es el eje que la RLS no puede cubrir: dos clientes finales de la
misma barbería son filas legítimas del mismo tenant, y la consulta que devuelve
una devuelve la otra.

La regla es la misma que la del tenant y por la misma razón, escrita en
`core/tenant_context.py`: el cliente del turno se fija en servidor «so
customer-facing tools can resolve "the person I'm talking to" WITHOUT trusting
an LLM-supplied identifier … making cross-customer lookups impossible».

Una herramienta de cara al cliente que acepte `customer_id` como argumento
rompe eso, porque un argumento lo rellena el modelo, y al modelo lo escribe
quien manda el mensaje. `nexus_mcp/base.py` ya prohíbe los campos extra «so the
LLM cannot smuggle ``tenant_id`` or other ambient state through arguments»: el
cliente **es** ambient state.

Cubierto por `apps/api/tests/isolation/test_35_customer_scope_within_tenant.py`.
"""

from __future__ import annotations

import uuid

from nexus_api.core.tenant_context import get_current_customer

from nexus_mcp.base import ToolError


def current_customer_or_refuse(what: str) -> uuid.UUID:
    """El cliente del turno, o un error que el modelo pueda leer.

    Un turno sin cliente resuelto es de operador, o una regresión del runtime.
    En los dos casos, seguir adelante contra «todo el negocio» es la respuesta
    equivocada.
    """
    customer_id: uuid.UUID | None = get_current_customer()
    if customer_id is None:
        raise ToolError(
            f"no hay cliente resuelto en este turno, así que no se puede {what}. "
            "Pide a la persona que escriba desde su propio canal."
        )
    return customer_id


__all__ = ["current_customer_or_refuse"]
