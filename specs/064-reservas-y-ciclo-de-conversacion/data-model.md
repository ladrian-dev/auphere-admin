# Modelo de datos — spec 064

Una migración, `0236_context_cut_and_autoclose`. No hay tablas nuevas.
Todas las columnas viven en tablas que ya tienen RLS por `tenant_id`.

## `conversations` (dos columnas)

| Columna | Tipo | Por defecto | Qué es |
|---|---|---|---|
| `context_from` | `timestamptz NULL` | `NULL` | Desde cuándo lee el agente el hilo. `NULL` = desde `attended_at`. |
| `cut_on_reopen` | `boolean NOT NULL` | `false` | La resolvieron después de esta spec: la próxima reapertura por el contacto o por el sistema corta. |

- El agente lee desde `greatest(coalesce(attended_at, -∞), coalesce(context_from, -∞))`.
- La Bandeja sigue leyendo desde `attended_at`. No usa `context_from`.
- Añadir las dos columnas no reescribe la tabla (nullable, y un booleano con
  valor por defecto constante).
- Las filas de hoy quedan con `NULL` y `false`: nada cambia para ellas hasta que
  se vuelvan a resolver (requisito 4.8).

### Transiciones

| Hecho | `status` | `cut_on_reopen` | `context_from` |
|---|---|---|---|
| Una persona o el cierre por inactividad resuelven | `CLOSED` | `true` | no cambia |
| Una persona reabre a mano | `OPEN` | `false` | no cambia |
| El contacto escribe, o sale un aviso del sistema, con `cut_on_reopen = true` | `OPEN` | `false` | punto de corte |
| El contacto escribe con `cut_on_reopen = false` (resuelta antes del despliegue) | `OPEN` | `false` | no cambia |
| «Vaciar el chat» | no cambia | no cambia | no cambia (`attended_at` pasa a ahora y manda) |

**Punto de corte**: `closed_at`, o el `created_at` del aviso de sistema más
antiguo que siga sin respuesta y vigente, si es anterior (research D4).

## `client_access` (una columna)

| Columna | Tipo | Por defecto | Qué es |
|---|---|---|---|
| `inbox_autoclose_hours` | `integer NULL` | `NULL` | Plazo sin mensajes tras el que una conversación se resuelve sola. `NULL` = nunca. |

- `CHECK (inbox_autoclose_hours IS NULL OR inbox_autoclose_hours IN (24, 72, 168, 720))`,
  con nombre `ck_client_access_inbox_autoclose`.
- Una fila por cliente (`tenant_id` es la clave), con RLS FORCE.

## `reservation_settings` (sin cambio de esquema)

`agent_min_notice_minutes` ya existe, con 60 por defecto. Cambia solo la
validación al escribir: uno de `0, 15, 30, 60, 120, 240, 1440`. No se añade
`CHECK` en la base: un valor antiguo fuera de la lista se conserva hasta que
alguien lo cambie.

## `reservations` (sin cambio de esquema)

Transiciones nuevas de `status`, solo en `mode = 'services'` y con
`now − ends_at ≤ 7 días`:

| De | Acción | A | Evento |
|---|---|---|---|
| `done` | `noshow` | `noshow` | `noshow` |
| `noshow` (con `ends_at ≤ now`) | `undo` | `done` | `undone` |

`undo` desde `noshow` antes de la hora de fin sigue dejando `confirmed`, como
hoy. Cada transición sube `version` y guarda quién la hizo.

## `conversation_events` (sin cambio de esquema)

El evento `resolved` del cierre por inactividad lleva `actor = "system"` y
`payload = {"reason": "inactivity"}`. El `CHECK` de `kind` no cambia.

## `console_audit_vocabulary` (una fila)

La acción `inbox.settings_changed`, que deja el cambio del plazo, con su frase en
español y en inglés. Sin ella la consola la enseñaría con el código en crudo. Va en
la misma migración.
