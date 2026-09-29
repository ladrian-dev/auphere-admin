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
| CE-001 · el número cambia de cliente | local (T006) · **staging, número real** | ✅ 2026-09-29 22:26: el owner conectó el `+34653321693` en otro cliente (`QA-f1-generica`) tras soltarlo en `Prueba WhatsApp 016`: Embedded Signup → «conectado. El cliente ya está activo y atendiendo»; tarjeta «Activo». Sin aprobación de nadie (R4.1) |
| CE-002 · reconectar recupera la ficha | local (T007) · **staging, número real** | ✅ el owner lo volvió a conectar en `Prueba WhatsApp 016`: la tarjeta es la misma (Creado: 23 sept), no una nueva |
| CE-003 · vivo en otro sitio → palabras | local (T008) | ✅ 409 `number_in_use`; nada dice de quién es |
| CE-006 · Meta caído | local (T012, T015) + tarjeta en el navegador | ✅ desvinculado igual; `unlink_pending` lista lo que faltó; reintentar lo vacía |
| CE-004 · Meta ya no lo tiene bajo nuestra app | **staging, número real** | ✅ 2026-09-29 — primer intento (21:28): Meta rechazó `deregister` (número en coexistencia), la tarjeta dijo «Falta terminar en Meta» con Reintentar (R3). Tras la corrección D5 (`7070426`), **Reintentar** → «Terminado en Meta.»: solo `unsubscribe`, aceptado; tarjeta limpia |
| CE-005 · el hermano sigue vivo | **staging, dos números en una WABA** | ⚪ sin segundo número real; queda cubierto por T014 (Meta simulado): con hermano vivo solo `deregister`, credencial del tenant intacta. Se cierra con número real cuando haya dos |
| R4.2 · Meta retiene el número del dueño anterior | **staging, número real** | ⚪ no se dio el caso: tras desuscribir, Meta dejó conectar en el otro cliente a la primera. El código sigue reservado al rechazo del `register` (`PhoneRegisterRefused`); se verá el día que Meta lo rechace |
| D5 · `deregister` en coexistencia | **staging, número real** | ✅ medido: Meta lo rechaza → no se pide. Ver `research.md` D5 |

En local no hay Meta: conectar un número de verdad necesita el Embedded
Signup, así que CE-001–003 se prueban con el cliente de Meta simulado, que es
lo que el quickstart prevé. Los cuatro pendientes necesitan el `+34653321693`
y el Business Manager, y se cierran con el owner delante.
