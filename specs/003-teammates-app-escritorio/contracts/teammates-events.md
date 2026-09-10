# Contrato — CONTRACT-V3: los eventos de teammate

Enmienda de `docs/companion/CONTRACT-V2.md` §8. V2 fijó veinte eventos y un
test que lo comprueba; V3 fija **veinticuatro** y cambia el test por la puerta.

## Nuevos

| Evento | Origen | Claves |
|---|---|---|
| `task.state` | 003 | `task_id, state, cause` — `cause ∈ {hitl, budget, completed, cancelled, expired, teammate_archived, machine_absent}` |
| `exec.dispatched` | 003 | `execution_id, executable, args, cwd_relative, client_ref` |
| `exec.completed` | 003 | `execution_id, outcome, exit_code` — **sin** salida |
| `inbox.changed` | 003 | `action_id, decision, by` — en el stream de la bandeja y en el del hilo |

## Ampliados

| Evento | Antes | Ahora |
|---|---|---|
| `hitl.requested` | `action_id, kind, title, preview, diff, impact, expires_at` | + `level` (`critico·aviso·informativo`), + `task_id`, `expires_at` **puede ser null** (teammate) |
| `run.completed` | `status ∈ {completed, cancelled, error, interrupted, paused}` | + `waiting` |

## Reglas que no cambian

- `publish` rechaza lo que no está en el catálogo y elimina claves no
  declaradas (`sanitise_payload`).
- `since_seq` y `resume.gap` valen para el stream del hilo; el stream de la
  bandeja no tiene historial (es un aviso, la verdad está en `GET /inbox`).
- Ningún evento lleva cuerpos de cliente final ni salida de comandos.
