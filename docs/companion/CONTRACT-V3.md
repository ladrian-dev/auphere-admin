# CONTRACT-V3 · Los eventos de teammate (spec 003)

> **Estado: enmienda de [`CONTRACT-V2.md`](CONTRACT-V2.md) §8**, 2026-09-10.
> Todo lo que la v2 congeló sigue en pie; aquí solo está lo que se **añade** o
> se **amplía** para que un hilo pertenezca a un teammate y a una persona, para
> que una tarea sobreviva al turno y para que la máquina del partner ejecute.
> Autoridad: v3 > v2 > v1.1.

## 1. El catálogo pasa de veinte a **veinticuatro**

La v2 §8 dijo «veinte, ni uno más en la Ola 2» y lo fijó con un test. La 003
lo enmienda por la puerta: el test pasa a fijar veinticuatro, y este documento
es el único sitio donde se dice por qué.

### 1.1 Nuevos

| Evento | Origen | Claves | Cuándo |
|---|---|---|---|
| `task.state` | 003 | `task_id, state, cause` | Cada cambio de estado de `teammate_tasks`. `state ∈ {en_marcha, esperandote, pausada_por_tope, terminada, cancelada, caducada}`; `cause ∈ {hitl, budget, completed, cancelled, expired, teammate_archived, machine_absent}` (no `reason`: C8 prohíbe esa clave porque podría llevar prosa) |
| `exec.dispatched` | 003 | `execution_id, executable, args, cwd_relative, client_ref` | La plataforma dejó una ejecución `pending` para la máquina. `args` es lista |
| `exec.completed` | 003 | `execution_id, outcome, exit_code` | La máquina contestó por `/device/result`. **Sin salida**: la muestra viaja al modelo como resultado de herramienta, nunca por el stream |
| `inbox.changed` | 003 | `action_id, decision, by` | Alguien decidió una acción de teammate. Va en el stream del hilo **y** en el de la bandeja |

### 1.2 Ampliados

| Evento | Antes | Ahora |
|---|---|---|
| `hitl.requested` | `action_id, kind, title, preview, diff, impact, expires_at` | + `level` (`critico · aviso · informativo`), + `task_id`; `expires_at` **puede ser `null`** — solo cuando hay `task_id` (la acción espera a la tarea) |
| `run.completed` | `status ∈ {completed, cancelled, error, interrupted, paused}` | + `waiting`: el run cerró aparcado y la tarea sigue |

## 2. Reglas que no cambian

- `publish` rechaza lo que no está en el catálogo y elimina claves no
  declaradas (`sanitise_payload`).
- `since_seq` y `resume.gap` valen para el stream de un run. **El stream de la
  bandeja no tiene historial**: es un aviso; la verdad es `GET /console/teammates/inbox`,
  y el cliente lo refresca en cada (re)conexión.
- Ningún evento lleva cuerpos de cliente final ni salida de comandos.
- El identificador es estable y la interfaz pone la palabra: `state` y `cause`
  se traducen en la pantalla, nunca en el backend.

## 3. Garantías con test

- `tests/integration/test_contract_v3_catalog.py`: veinticuatro eventos; `task.state`
  con `state` fuera del enum se rechaza; `hitl.requested` acepta `expires_at=None`
  solo con `task_id`.
