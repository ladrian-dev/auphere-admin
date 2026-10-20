# Especificación: el consumo de toda la plataforma

**Rama**: `035-canales-y-conectores` (continúa) · **Creada**: 2026-10-19 · **Estado**: Implementada

**Entrada**: owner, 2026-10-19 — «No veo el consumo desde la vista de Admin… no mi consumo
sino el consumo de todos mis partners y clientes».

## Encabezado Auphere

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — panel de operador |
| **Garantías de aislamiento tocadas** | **1** — el libro de cada partner se lee con su GUC (`credit_burn_by_day`) y los mensajes de cada cliente con el suyo (`tenant_scoped_session`). Test en `tests/integration/test_admin_usage_overview.py` |
| **Nota de KB** | `[[ADR-044-el-dinero-es-exacto]]` (dos cifras, nunca una) |
| **Qué se mide** | Nada nuevo: se lee lo que ya mide el libro y `messages.cost_usd` |

## Origen

Hasta ahora el consumo solo se veía partner a partner, dentro de su ficha (Clientes y Dinero).
No había una vista con todos.

## Requisitos

1. La API DEBE exponer `GET /admin/usage` (`?month=true` o `?days=N`). Debe dar:
   - totales: gasto, coste interno, margen, mensajes, conversaciones y clientes con actividad;
   - una fila por partner: gasto, gasto fuera de clientes, coste interno, mensajes y saldo disponible;
   - una fila por cliente: gasto, coste interno, mensajes y conversaciones;
   - la serie por día.
2. El **gasto** DEBE salir del libro de cada partner a precio de venta. El **coste interno** DEBE salir de `messages.cost_usd` en decimal. Nunca se mezclan bajo un nombre.
3. Un partner o cliente que no se pueda leer DEBE nombrarse en `unreadable` sin tumbar el resto.
4. El panel DEBE tener «Consumo» en Gestionar, con:
   - periodos: este mes, 7, 30 y 90 días;
   - cuatro cifras y el gasto por día;
   - tablas por partner y por cliente, con buscador, que abren su ficha.

## Fuera de alcance

- Consumo por cliente dentro de su ficha, y exportar a CSV.
- Precalcular: hoy se lee en paralelo, hasta 8 a la vez.
