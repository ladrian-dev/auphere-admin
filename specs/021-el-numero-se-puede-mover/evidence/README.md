# Evidencia — spec 021

Una entrada por iteración. Cada una dice qué se midió, con qué, y qué salió.

| Iteración | Fichero | Estado |
|---|---|---|
| 1 · el índice | `iteracion-1.md` | cerrada 2026-09-29 |
| 2 · Meta y el modo de fallo | `iteracion-2.md` | cerrada 2026-09-29 (API); CE-004/005 y R4.2 en staging |
| 3 · la tarjeta | `iteracion-3.md` | cerrada 2026-09-29 |

## Puertas de cierre

| Puerta | Resultado |
|---|---|
| Licencias | `pnpm-lock.yaml` y `apps/api/uv.lock` con el **mismo** SHA-256 que en `locks-at-open.sha256`; `git diff origin/develop` sobre los locks vacío. Ninguna dependencia nueva |
| Medidor | `usage_events` igual antes y después de desvincular (T003) |
| Aislamiento | `tests/isolation/test_channel_number_scope.py` (T004): la fila ajena desvinculada ni bloquea ni se ve; la viva bloquea sin decir de quién es; 9 rutas sin `tenant_id`/`partner_id` |

## Quickstart — qué se recorrió

| Caso | Dónde | Estado |
|---|---|---|
| CE-001 · el número cambia de cliente | local, Meta simulado (T006) | ✅ B conecta lo que A soltó; la fila de A queda desvinculada con su historial |
| CE-002 · reconectar recupera la ficha | local (T007) | ✅ mismo `channel.id` |
| CE-003 · vivo en otro sitio → palabras | local (T008) | ✅ 409 `number_in_use`; nada dice de quién es |
| CE-006 · Meta caído | local (T012, T015) + tarjeta en el navegador | ✅ desvinculado igual; `unlink_pending` lista lo que faltó; reintentar lo vacía |
| CE-004 · Meta ya no lo tiene bajo nuestra app | **staging, número real** | ⚠️ 2026-09-29 21:28: desvinculado en la consola; Meta **rechazó `deregister`** (número en coexistencia) y `unsubscribe` no se intentó. La tarjeta lo dijo con «Falta terminar en Meta» y Reintentar (R3 cumplida). Corrección: coexistencia no da de baja (D5). Pendiente: reintentar y ver `unsubscribe` |
| CE-005 · el hermano sigue vivo | **staging, dos números en una WABA** | ⏳ pendiente |
| R4.2 · Meta retiene el número del dueño anterior | **staging, número real** | ⏳ pendiente: confirmar que llega como `number_held_by_previous_owner` |
| D5 · `deregister` en coexistencia | **staging, número real** | ✅ medido: Meta lo rechaza → no se pide. Ver `research.md` D5 |

En local no hay Meta: conectar un número de verdad necesita el Embedded
Signup, así que CE-001–003 se prueban con el cliente de Meta simulado, que es
lo que el quickstart prevé. Los cuatro pendientes necesitan el `+34653321693`
y el Business Manager, y se cierran con el owner delante.
