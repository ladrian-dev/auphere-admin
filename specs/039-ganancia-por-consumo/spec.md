# Especificación: la ganancia de Auphere por consumo

**Rama**: `035-canales-y-conectores` (continúa) · **Creada**: 2026-10-19 · **Estado**: Implementada

**Entrada**: owner, 2026-10-19 — «Necesito poder ver cuál es nuestra ganancia por consumo:
el porcentaje que se le cobra al cliente por el consumo de los agentes y, en dinero, cuánto
es nuestra ganancia real».

## Encabezado Auphere

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — panel de operador |
| **Garantías de aislamiento tocadas** | **1** — `usage_records` (RLS por cliente) se lee con el GUC de cada cliente. Test en `tests/integration/test_admin_usage_overview.py` |
| **Nota de KB** | `[[ADR-044-el-dinero-es-exacto]]` |
| **Qué se mide** | Nada nuevo |

## Corrección

La vista Consumo (spec 038) y la pestaña Clientes del partner sumaban `messages.cost_usd`
como «coste interno». Ese campo es el precio que **Meta** pone al mensaje, no lo que nos
cuesta el modelo (`db/models/usage_record.py`). Ahora el coste sale de
`usage_records.cost_usd`.

## Requisitos

1. **Venta.** Son los débitos del libro de cada partner.
2. **Coste.** Es `usage_records.cost_usd` de los turnos cobrados: `source` channel y companion.
3. **Pruebas.** Los turnos con `source` qa van aparte: los paga Auphere y no se cobran.
4. **Fórmulas.**
   - Ganancia = venta − coste.
   - Margen = ganancia ÷ venta.
   - «Se cobra sobre el coste» = venta ÷ coste − 1, junto al multiplicador fijado (`QUOTA_TARGET_MULTIPLIER`, 2,2×).
   - Ganancia neta = ganancia − pruebas.
5. **Eventos sin precio.** Un evento con `cost_usd` NULL se cuenta y se avisa. Nunca se lee como cero.
6. **Desglose.** Las cifras salen en total, por partner, por cliente y por día.
