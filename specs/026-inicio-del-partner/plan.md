# Implementation Plan: el Inicio le dice al partner qué hacer hoy

**Branch**: `026-inicio-del-partner` | **Date**: 2026-10-02 | **Spec**: [spec.md](spec.md)

## Summary

`GET /console/home` gana bloques nuevos sin perder los que ya lee el
Companion (`console.get_quota` usa `/console/home`): **attention** (lo que
falla, ordenado por gravedad, con su arreglo), **to_review** (escaladas,
pagos por revisar, sin responder), **conversations_trend** (7 días contra los
7 anteriores, serie diaria total y por cliente), **credit** (disponible,
gasto de 7 días, días de autonomía, clientes en riesgo) y **portfolio** (una
fila por cliente). La actividad reciente sale de `GET /console/audit`, que ya
existe. La página del Inicio se rehace con esos bloques y desaparece
«Calculado en X ms». `@nexus/ui` gana `Sparkline` y la variación en `Metric`.

**Iteración 1** (esta entrega): todo lo anterior con las lecturas por cliente
que ya hace `tenant_snapshots` (más subconsultas, misma concurrencia).
**Iteración 2**: tabla `tenant_daily_stats`, selector de periodo, resueltas
por el agente, ventas y tiempo de respuesta. **Iteración 3**: avisos
`channel.degraded` y `template.rejected`.

## Technical Context

**Language/Version**: Python 3.14 · TypeScript 5 / Next.js 16
**Primary Dependencies**: FastAPI · SQLAlchemy async · recharts (ya en `@nexus/ui`) — **ninguna nueva**
**Storage**: sin migración en la iteración 1
**Testing**: pytest (`tests/unit/test_endpoint_console_home_usage.py` y uno nuevo), vitest, a11y de `/`
**Performance Goals**: el Inicio por debajo de 1 s p95 con 24 clientes (medido con `scripts/dev_seed_console_volume.py`)
**Constraints**: toda cifra con acción o fuera (CP-08) · sin `tenant_id` ni costes (C8/C9) · permisos por bloque · trabajo en desarrollo y staging

## Constitution Check

| # | Principio | ¿Cumple? | Prueba |
|---|---|---|---|
| I | Aislamiento | ☑ | Lecturas por cliente bajo su RLS; lo de cartera filtrado por `partner_id`. Test de aislamiento entre partners en el Inicio |
| II | Superficie | ☑ | `0` |
| III | Lo leído es dato | ☑ | Solo cifras y nombres de cliente |
| IV | Acción con aprobación | ☑ | Solo lectura |
| V | Estados honestos | ☑ | Sin variación inventada, bloques que fallan lo dicen, vacío diseñado |
| VI | Por API `console.*` | ☑ | Un endpoint, el Companion lo puede leer |
| VII | Test primero | ☑ | Cada bloque nace con su test |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | KB | ☑ | Auditoría UX §3.2 y CP-08 |

## Decisiones

- **D1 · Gravedad** (orden de `attention`): `out_of_quota` 1, `no_active_agent` 2, `whatsapp_disconnected` 3, `needs_reauth` 3, `quality_red` 4, `failed_messages` 5, `template_rejected` 6, `draft_unpublished` 7, `provisioning` 8. Cada tipo tiene su enlace (`href`) al arreglo.
- **D2 · Escaladas «sin atender»**: conversaciones `ESCALATED` cuyo último mensaje del cliente es de los últimos 7 días. `ESCALATED` no se limpia nunca en el código, así que sin la ventana contarían para siempre.
- **D3 · Plantilla rechazada**: `whatsapp_template_status` no es por tenant (va por WABA). El snapshot devuelve las WABA del cliente y una sola consulta de plataforma busca rechazos de los últimos 7 días.
- **D4 · Crédito**: disponible de `read_wallet`; gasto de 7 días de `usage_ledger` por cliente en una consulta con el partner en sesión (`credit_burn` nuevo en `metering/wallet.py`); días = disponible ÷ gasto medio diario, nulo sin gasto. En riesgo: clientes cuyo `remaining` ÷ gasto diario del cliente < días hasta fin de mes.
- **D5 · Serie diaria**: conversaciones por día UTC de los últimos 14 días por cliente, en la misma sesión del snapshot. Se enseñan 7 y se comparan con los 7 anteriores.
- **D6 · Compatibilidad**: los bloques antiguos siguen en la respuesta (Companion), la página deja de usarlos.

## Project Structure

```text
apps/api/src/nexus_api/services/console_home.py        # snapshot ampliado + serie diaria
apps/api/src/nexus_api/metering/wallet.py               # credit_burn
apps/api/src/nexus_api/api/console/home.py              # bloques nuevos
apps/api/src/nexus_api/api/console/schemas_home_usage.py
packages/ui/src/components/sparkline.tsx                # nuevo
packages/ui/src/components/metric.tsx                   # delta + trend
apps/console/src/app/(console)/page.tsx                 # Inicio nuevo
apps/console/src/components/home/*                      # bloques
apps/console/src/lib/backend/home-usage.ts              # tipos
apps/console/src/i18n/lanes/home-usage.ts               # textos
```
