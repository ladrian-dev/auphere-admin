# Iteración 2 — desvincular deshace en Meta, sin quedarse a medias

**API cerrada el 2026-09-29.** Lo que solo se puede ver con un número real
(CE-004, CE-005, y el error exacto de Meta para R4.2) queda para staging.

## Lo que cambió el diseño al escribirlo

- **Dos sesiones propias, no dos transacciones en `scope.session`.** El
  `client_scope` envuelve el endpoint entero en una sola `session.begin()`;
  commitear a mitad rompería el contexto. Se abren dos sesiones con
  `tenant_scoped_session`, como ya hace `AgentLoader`. Mismo scope, misma RLS.
- **Sin credencial, nada que deshacer.** Un canal sin credencial de canal ni
  de tenant nunca estuvo atado a nuestra app; dejar `deregister` pendiente para
  siempre sería un reintento que no puede terminar. Se anota `skipped`.
- **`agent_enabled` mentía.** Leía `config.agent_enabled` y decía «atiende» de
  un canal desvinculado. Ahora respeta el estado (constitución §V).

## Medido

| Caso | Resultado |
|---|---|
| Meta caído | 200 · `disconnected` · `unlink_pending = [deregister, unsubscribe]` · `agent_enabled = false` · tras fallar `deregister` no se intenta `unsubscribe` |
| Último de la WABA | `deregister` → `unsubscribe` · `config_encrypted` a `null` · `tenant_credentials` borrada · sin pendientes |
| Hermano vivo | solo `deregister` · el hermano `active` · credencial del tenant intacta |
| Reintento | segundo POST termina `unsubscribe` sin repetir `deregister`; tercer POST sin pendientes no toca Meta |
| Auditoría | `after.meta == {"done": ["deregister"], "pending": ["unsubscribe"]}` |
| Proceso muere antes de Meta | el endpoint revienta **y** la fila ya está `disconnected` con todo pendiente |
| Medidor | `usage_events` igual antes y después |

## Suites

| Suite | Resultado |
|---|---|
| `test_endpoint_console_channels` (34 + 7 nuevos) · `_whatsapp` · `isolation/test_channel_number_scope` | **47** ✅ |
| ruff check · format | limpios |

## Pendiente en staging (T025)

- CE-004: consultar en Meta que el número ya no está bajo nuestra app.
- CE-005: dos números en una WABA; desvincular uno no toca al otro.
- R4.2: comprobar qué devuelve Meta cuando el número sigue en otra cuenta, y
  que llega como `number_held_by_previous_owner` y no como 400 genérico.
- D5: `deregister` sobre un número en coexistencia no rompe la app del móvil.
