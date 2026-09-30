# Iteración 2 — el agente lo usa, y solo cuando lo tiene (Historia 3)

**Cerrada en local el 2026-09-30.** La tarjeta real en un teléfono (CE-002)
espera al permiso `catalog_management` en el panel de Meta.

## Lo que cambió el diseño al escribirlo

- **Qué canal**: no hay variable de contexto de canal en el turno (solo tenant
  y cliente). La herramienta resuelve el canal por la **última conversación
  del cliente del turno**, y sin cliente (operador, Playground) por el primer
  número vivo con catálogo. Dos números de la misma cuenta comparten catálogo,
  así que en la práctica coincide.
- **«Enviar productos del catálogo» no es una herramienta nueva**: es
  `catalog.get_product` (la ficha con el `retailer_id`), que el agente manda
  con `response.send_interactive`, que sigue siendo genérica (botones, listas)
  y **no se gatea** por catálogo. Gatear la genérica habría escondido los
  botones a quien no tiene catálogo.
- **Sin catálogo, la capacidad no existe**: `capabilities_client` la omite
  (no la marca «no utilizable»). Un número desvinculado con catálogo no cuenta.
- **El registro y el catálogo de herramientas tienen tests de conteo** (58 →
  60, 29 → 31): son la guarda de que nada entra sin que alguien lo mire.

## Medido

| Caso | Resultado |
|---|---|
| Buscar | catálogo y token del canal, resueltos en el servidor; la salida no contiene ninguno de los dos |
| Límite | 10 como máximo; 50 → error de validación; `truncated` cuando el catálogo devolvió el máximo |
| Sin catálogo | `catalog_not_linked`, cero llamadas a Meta |
| Ficha | por `retailer_id`; ausente → `found: false` |
| Meta caído | `catalog_unavailable`, legible por el agente |
| Argumento colado (`access_token`) | rechazado por el modelo de entrada |
| Capacidades | sin catálogo no aparecen; con catálogo «Buscar en el catálogo» y «Enviar productos del catálogo», conector «Catálogo de Meta · connected», solo lectura, `always` |
| Envío sin catálogo | `products` se degrada a texto y se anota |

## Suites

| Suite | Resultado |
|---|---|
| `apps/channels` · `test_meta_client` | 25 ✅ |
| `apps/mcp` · `test_meta_catalog_tools_unit` (7) + `test_registry_unit` | 12 ✅ |
| `apps/worker` · `test_outbound_interactive` | 12 ✅ |
| API · capacidades (unit + integration), `tool_catalog`, aislamiento, `seed_templates` | 63 ✅ |
| ruff · mypy | limpios |

## Queda para staging

CE-002 con el número real: pedir «¿qué tenéis?» en el Playground y recibir
la tarjeta. Necesita `catalog_management` en el Embedded Signup.
