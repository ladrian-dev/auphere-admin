# Fase 1 — Modelo de datos

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Fecha**: 2026-09-20

> **Ninguna migración.** Todo lo que estas siete historias necesitan ya está en
> la base de datos desde la spec 003. Lo que falta es leerlo y devolverlo. Este
> documento existe para dejarlo probado, no para proponer tablas.

## Lo que ya existe y no cambia

### `companion.threads` — la conversación

| Columna | Qué es aquí |
|---|---|
| `principal_id` | **El eje de aislamiento.** La RLS de la migración 0090 filtra por él: la conversación de otra persona del mismo partner no existe, ni siquiera para decir que no |
| `teammate_id` | Con quién se habla. `NULL` es el Companion clásico |
| `title` | Hoy se escribe literalmente `"Hilo"` desde la aplicación |
| `archived_at` | Ya existe. Es lo que hoy usa `app:thread.open` para elegir «la» conversación |
| `last_run_at`, `updated_at` | Ya ordenan la lista |

**Varias conversaciones por teammate ya son posibles.** No hay índice único que
lo impida ni columna que sobre. Lo que fuerza el hilo único es una línea de la
aplicación, no el esquema (research §3).

Lo único que cambia de comportamiento: **el título deja de ser `"Hilo"`** y pasa
a derivarse de lo primero que se escribió, recortado. Es un valor distinto en una
columna que ya está, no una columna nueva. No se le pide al modelo que titule:
sería un turno de más y un gasto por una etiqueta.

### `companion.messages` — lo que se dijo

| Columna | Qué es aquí |
|---|---|
| `run_id` | Ata el mensaje a su turno. **Un run tiene exactamente un mensaje `role="user"`**: el que lo disparó |
| `role` | `user` \| `assistant` |
| `content` | El texto. **Ya se guarda el de la persona** y hoy no se devuelve a nadie más que al modelo |
| `seq` | Orden dentro del hilo |

La relación 1:1 entre run y mensaje de persona es lo que permite que R1 se
resuelva con un campo en el resumen de run en vez de con una segunda lista.

### `local_executions` — qué se ejecutó

Sigue diciendo **qué, dónde, quién lo aprobó y cómo acabó**. Y sigue **sin**
columna para la salida, que es el punto: §III y CE-005.

## Lo que se añade, y no es una tabla

### La salida de un comando: un dato con caducidad

| | |
|---|---|
| **Dónde vive** | Redis, y solo Redis |
| **Quién la escribe** | `publish_result`, cuando la máquina contesta |
| **Quién la lee** | Dos: el turno (que la consume) y la pantalla (que no) |
| **Cuánto dura** | Quince minutos desde que la máquina contestó |
| **Dónde NO está** | `local_executions`, la auditoría, los eventos del stream, y cualquier tabla |

**Por qué dos lectores y no uno compartido.** Hoy `await_result` hace `LPOP`: se
lleva el payload. Si la pantalla leyera de ahí, el turno se quedaría sin su
resultado, o al revés — el que llegue segundo no encuentra nada. Así que
`publish_result` deja dos cosas: la cola que el turno consume, **intacta en su
comportamiento actual**, y una clave de solo lectura con su propio TTL.

**Por qué quince minutos.** Es el mismo reloj que ya caduca una aprobación
(§IV). Cubre leer el resultado de un build sin convertirse en un sitio donde
buscar cosas viejas. Al reabrir un hilo de ayer la salida ya no está, y R3.3 pide
**decirlo** en vez de dejar un hueco.

## Las tres afirmaciones que hay que probar

No son garantías de aislamiento entre tenants —esta spec no toca ninguna— pero
son fronteras y merecen test:

1. **R1.3** — pedir el resumen de runs de una conversación de otra persona del
   mismo partner responde como si no existiera. El prompt viaja ahí dentro: si
   esta frontera se cae, se cae con texto de una conversación ajena.
2. **R7.2** — buscar no devuelve contenido de otra persona.
3. **La ruta de la salida** — solo la sirve a quien aprobó esa ejecución, bajo el
   alcance de cliente que ya existe.

## Lo que este modelo deja fuera a propósito

- **No hay entidad «conversación archivada» nueva**: `archived_at` ya está y la
  spec no introduce archivar.
- **No hay índice de búsqueda.** R7 es P3 y se resuelve sobre lo que hay; si
  hiciera falta un índice, es otra decisión y otro coste.
- **No hay copia de la salida para la auditoría.** Es justo lo que §III prohíbe.
