# Modelo de datos: spec 056

Cinco migraciones encadenadas sobre la cabeza actual `0222_merge_0220_heads`. **Se crean juntas y en este orden antes de implementar nada más**, para que quien trabaje en paralelo nunca tenga dos cabezas (lo que abortó el despliegue de `b2ed5825`).

| Revisión | `down_revision` | Qué hace | Requisito |
|---|---|---|---|
| `0223_booking_unbacked_reason` | `0222_merge_0220_heads` | Rehace `ck_conversations_waiting_reason` con `booking_unbacked` | 1.2 |
| `0224_client_modules_retire` | `0223_booking_unbacked_reason` | Quita `agents` y `business` de `client_access.modules`. Rehace `ck_client_access_modules` con los cuatro módulos | 2.1, 2.2 |
| `0225_client_access_audit_actor` | `0224_client_modules_retire` | Reescribe las frases del vocabulario de auditoría del acceso del cliente con `{actor}` | 3.8 |
| `0226_correction_batches` | `0225_client_access_audit_actor` | `inbox_corrections.batch_id` con su FK compuesta | 9.1, 9.2 |
| `0227_notice_handled` | `0226_correction_batches` | `console_notifications.handled_at` con su índice parcial | 8.1, 8.2 |

Ninguna crea tabla. Todas tienen downgrade. La 0224 no puede devolver los datos borrados: lo dice en su docstring.

---

## Conversación: motivo de espera (0223)

- `conversations.waiting_reason` admite un valor más: `booking_unbacked` («El agente dio por hecha una cita que no existe»).
- `WAITING_REASONS` (`db/models/conversation.py:67`) lo añade.
- **No** entra en `GATE_REASONS`, así que no se libera con la siguiente respuesta del agente.
- Tenant: la conversación es del tenant y la RLS la alcanza por `tenant_id`, como hoy.

## Acceso del cliente: módulos (0224)

- `client_access.modules` solo admite `panel`, `inbox`, `reservas` y `usage`.
- Migración de datos:
  - `UPDATE client_access SET modules = array_remove(array_remove(modules, 'agents'), 'business'), updated_at = now(), updated_by = 'system:spec_056' WHERE modules && ARRAY['agents','business']::varchar[]`;
  - después, `enabled = false` donde quede `modules = '{}'`, porque encendido exige al menos uno.
- El CHECK se rehace como en `0198_lite_and_corrections.py:120-126`.
- El usuario de migraciones es superusuario: el `FORCE RLS` no le estorba.
- Prueba: `tests/integration/test_migration_0224_client_modules_retire.py`, con el patrón de `test_migration_0204…`:
  - un cliente con `{panel, agents, business}` queda en `{panel}`;
  - uno con `{agents}` queda apagado y vacío;
  - el CHECK rechaza `agents`.

## Vocabulario de auditoría (0225)

- Filas existentes de `console_audit_vocabulary`, sembradas por `0148_client_audience_vocab.py:30-66`:
  - el acceso cambiado;
  - persona invitada;
  - invitación reenviada;
  - persona revocada.
- `summary_es` y `summary_en` pasan de «Auphere cambió…» a «{actor} cambió…». `_human_actor` ya resuelve `operator:` como «Auphere» y `console:` como el correo.
- Acciones nuevas que se siembran:
  - `agent.booking_brake`: «El freno de citas actuó en una conversación de {client}»;
  - `correction.batch_accepted` y `correction.batch_discarded`.
- Prueba: `tests/unit/test_console_audit_words.py` (cubre las filas).

## Corrección: lote (0226)

- `inbox_corrections.batch_id uuid NULL`.
- FK **compuesta** `(tenant_id, batch_id) → inbox_corrections(tenant_id, id)`. Una FK de una columna no pasa por la RLS ([[fk-no-pasa-por-rls]]).
- Índice `(tenant_id, batch_id) WHERE batch_id IS NOT NULL`.
- La corrección que el cliente envía es la cabeza del lote, con `batch_id = id`. Las hermanas, una por cada otro agente `published` o `paused`, llevan el `batch_id` de la cabeza.
- Estados de cada fila: los de hoy. El lote no tiene estado propio: aceptarlo o descartarlo cambia cada fila en una transacción.
- Tenant: cada fila es del tenant del cliente.

## Aviso: atendido (0227)

- `console_notifications.handled_at timestamptz NULL`.
- Índice parcial `((payload->>'conversation_id')) WHERE kind = 'inbox.waiting' AND handled_at IS NULL`.
- Transiciones:

```
inbox.waiting creado (handled_at NULL, pendiente)
  └─ take_over · give_back · resolve/archive · release_reason · release_escalated_for_tenant
       → handled_at = now()   (deja de contar en la campana; sigue en la lista)
```

- Un escalado nuevo de la misma conversación crea un aviso nuevo, pendiente.
- Tenant: el aviso es del partner y va dirigido a un cliente (`external_client_ref`). El `UPDATE` filtra por los dos.

## Sin migración

- **Reglas de horario y servicios** (Requisito 5): constantes en código. Lo que ya incumple se marca al leer.
- **Sesión** (Requisito 15): `expires_at` ya está en la fila de sesión. Solo se devuelve.
- **Freno de citas**: la constancia es una fila de `audit_log` (acción sembrada en 0225) y un evento de log. Sin tabla.
- **Acceso del partner** (Requisito 3): mismas tablas y servicios que el panel.
