# Fase 1 — Modelo de datos

**Rama**: `001-puesto-trabajo-partner` · **Fecha**: 2026-09-09

Cuatro entidades nuevas, todas en el plano de control (`apps/api`, Alembic `0106+`).
**Las cuatro llevan `tenant_id` y RLS**, y ningún repositorio lo acepta del
llamante: sale del contexto de petición (`SET LOCAL app.tenant_id`). Esa es la
condición de §I y lo que comprueban `test_28` y `test_21` (que exige RLS en toda
tabla con tenant).

---

## 1. `partner_devices` — la máquina declarada

La máquina del partner, su latido y el directorio donde puede trabajar.

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid | |
| `tenant_id` | uuid | **RLS**. Del contexto, nunca del llamante |
| `principal_id` | uuid | La persona dueña del dispositivo (decisión 9: hilo privado por persona) |
| `display_name` | text | Lo que ve el partner: *«el MacBook de Luis»* |
| `platform` | text | `macos` \| `windows` |
| `workdir` | text | Directorio declarado por el partner (Requisito 1.1) |
| `app_version` | text | Para saber qué versión firmó lo que corrió |
| `last_heartbeat_at` | timestamptz | Base del estado; **no** hay columna `status` |
| `enrolled_at` / `revoked_at` | timestamptz | Borrar no existe: se archiva |

**El estado es derivado, no almacenado**: `presente` mientras el latido esté dentro
de su ventana, `ausente` en cuanto caduque. Guardar un booleano invitaría a que la
pantalla mienta cuando el proceso que lo actualiza muere (§V).

**Transiciones**: `nunca visto → presente → ausente → presente → revocado`.
`revocado` es terminal.

**Validación**: `workdir` debe existir, ser directorio y resolver dentro de sí mismo
en el momento de usarse, no solo al declararse (Requisito 1.4) — un directorio que
entre dos turnos pasa a ser un enlace simbólico deja de valer.

---

## 2. `local_executables` — la lista blanca, que es configuración

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid | |
| `tenant_id` | uuid | **RLS** |
| `executable` | text | Nombre del ejecutable. **Sin separadores de ruta y sin metacaracteres** |
| `added_by` | text | La persona. Se añade solo desde la consola (Requisito 2.1) |
| `added_at` | timestamptz | |
| `removed_at` | timestamptz | Se archiva, no se borra |

**Unicidad**: `(tenant_id, executable)` con `removed_at IS NULL`.

**Arranca vacía por tenant.** No hay ejecutables por defecto y no hay lista global:
§I dice que la whitelist es exhaustiva y por tenant, y un default global sería
justamente el «global» que prohíbe.

---

## 3. `local_argument_grants` — lo que sí se aprueba en el turno

Un permiso durable para **un conjunto de argumentos** de un ejecutable ya permitido.
Nunca crea ejecutables: si el ejecutable no está en la lista, no hay grant que valga
(Requisito 2.2).

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid | **uuid5 determinista** sobre `(tenant, ejecutable, firma de argv)` + UPSERT, para que una carrera no cree dos |
| `tenant_id` | uuid | **RLS** |
| `executable_id` | uuid | FK a `local_executables` |
| `argv_signature` | text | Forma canónica de los argumentos, normalizada |
| `action_id` | uuid | FK a `companion.actions` — **la aprobación durable vive ahí**, con su `state_hash`, `decided_at` y `decided_by` |
| `granted_at` | timestamptz | |
| `revoked_at` | timestamptz | Se archiva |

**Por qué no una tabla de aprobaciones nueva**: §IV ya está construido en
`companion.actions`. Un segundo mecanismo sería complejidad que la spec no pidió, y
dos sitios donde mirar quién aprobó qué.

---

## 4. `local_executions` — la auditoría

Una fila por intento, **incluidas las denegaciones** (Requisito 8.3).

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | uuid | |
| `tenant_id` | uuid | **RLS**, y etiqueta la traza (garantía 6) |
| `device_id` | uuid | FK a `partner_devices` |
| `executable` | text | Verbatim, aunque después se archive de la lista |
| `argv_signature` | text | |
| `grant_id` | uuid \| null | Null si no hizo falta aprobación o si se denegó |
| `outcome` | text | `completada` \| `expirada` \| `terminada` \| `denegada` |
| `denial_reason` | text \| null | `ejecutable_no_permitido` \| `metacaracteres` \| `fuera_del_directorio` \| `sin_verificar` \| `dispositivo_ausente` |
| `started_at` / `ended_at` | timestamptz | |
| `exit_code` | int \| null | |
| `children_reaped` | int | Cuántos procesos hijos hubo que recoger (Requisito 12.3) |

**No guarda la salida del comando.** La salida es contenido leído: se trata como
dato (§III) y no se persiste en el hilo del teammate, que además no puede
transcribir texto de cliente final. Se guarda que ocurrió, no lo que dijo.

---

## Lo que NO se modela aquí

- **La memoria del sustrato** (su índice con embeddings) vive en la máquina del
  partner, fuera de Postgres. El aislamiento ahí es **por instancia**, no por fila:
  una máquina, un partner. Esa es la razón por la que el modelo mono-usuario del
  sustrato es cierto en esta superficie y no lo sería en la nube.
- **Las sesiones y los turnos** del agente: ya existen.
- **Los subagentes**: si `T002` sale en verde, se apoyan en lo que ya hay; si sale
  en rojo, el Requisito 11 se retira y no hay nada que modelar.
