# Fase 1 — Modelo de datos

**Spec**: 015 · **Fecha**: 2026-09-22

**Una sola migración en toda la spec, y va en el último tramo** (H4). Los tramos
1, 2 y 3 no tocan la base.

---

## Lo que cambia

### `teammates` — una columna

| Columna | Tipo | Nulo | Por defecto | Por qué |
|---|---|---|---|---|
| `instructions` | `TEXT` | **sí** | **ninguno** | Lo que el partner escribe sobre cómo trabaja este teammate |

**Nulo, no cadena vacía, y la distinción importa.** `NULL` significa «no
escritas» y es lo que tienen los teammates que ya existen; el Requisito 6.2
depende de ello para garantizar que **nadie tiene que reconfigurar nada**. Una
cadena vacía significaría «escritas y borradas», que es otra cosa, y el
formulario no debe poder producirla.

**Sin `server_default`** por lo mismo: un `DEFAULT ''` convertiría todas las
filas existentes en «escritas y vacías» al migrar.

**Tope: 4.000 caracteres**, validado en el esquema de entrada
(`Field(max_length=4000)`), **no** en la base. La razón de no ponerlo como
`VARCHAR(4000)`: un tope de producto que cambia no debería exigir una migración,
y este número es defendible pero no sagrado.

> **De dónde sale el 4.000**, porque un número sin razón se convierte en folclore:
> son ≈1.000 tokens, que caben en el segundo tramo de caché sin acercarse al
> tamaño del texto compartido (6.413 caracteres tras D-4). Y son cincuenta veces
> `job` (80) y dos veces el prompt vertical más largo que un partner ya escribe
> hoy. Quien necesite más no quiere instrucciones: quiere conocimiento, y eso ya
> existe.

**A qué tenant pertenece**: a ninguno. `teammates` es del **partner** y la RLS la
alcanza por `partner_id`, como el resto de la fila. La columna nueva no añade
ningún eje: viaja dentro de una fila que ya está acotada.

### `teammate_changes` — el `CHECK` se ensancha

| Antes | Después |
|---|---|
| `fields <@ ARRAY['job', 'permissions', 'local_exec', 'model']` | `fields <@ ARRAY['job', 'permissions', 'local_exec', 'model', 'instructions']` |

**Esto no es opcional y casi se escapa.** Sin ensancharlo, registrar un cambio de
instrucciones viola la restricción y **la edición falla en producción, no en los
tests del camino feliz**. Se encontró leyendo el modelo antes de escribir la
migración — la lección directa de la spec 012 (`research.md` §M-4).

La restricción se reemplaza: `DROP CONSTRAINT` + `ADD CONSTRAINT` con el mismo
nombre, `teammate_changes_fields_check`.

---

## Lo que NO cambia, y conviene decirlo

- **El vocabulario de auditoría.** `teammate.updated` ya existe
  (`0110_teammate_audit_vocab.py:32`) y es la acción que ya se escribe al editar.
  Cambia qué campos se nombran, no qué acción se registra. **Ninguna migración de
  vocabulario.**
- **Las políticas de RLS.** `teammates` y `teammate_changes` ya las tienen y la
  columna nueva no crea ningún camino nuevo hacia la fila.
- **`permissions`, `tool_names`, `local_exec`, `model`.** Las instrucciones **no
  amplían el catálogo** (R6.3): son texto que el teammate lee sobre cómo
  trabajar, no una llave.
- **Ninguna tabla nueva.**

---

## Entidades que existen solo durante el turno

No se persisten, y por eso **no pueden quedarse viejas**. Es una propiedad
buscada, no una omisión.

### Bloque de identidad

Lo que el teammate lee sobre sí mismo, **derivado** en el momento de:

| De dónde sale | Qué aporta |
|---|---|
| `teammates.name` | su nombre |
| `teammates.job` | su oficio |
| `teammates.instructions` | sus instrucciones, si las tiene (H4) |
| `for_teammate(...)` | **qué familias tiene de verdad** |
| lo que `for_teammate` **no** devuelve | qué le falta, y qué interruptor lo daría |

Va como mensaje de sistema **en la posición 2**, inmediatamente tras el texto
compartido y **antes de la historia**, y lleva detrás el **corte 2** del caché
(D-2).

### Bloque de entorno

| De dónde sale | Qué aporta |
|---|---|
| la aplicación, por el turno | zona horaria de la persona |
| el reloj del servidor | fecha y hora en esa zona |
| `tenant.timezone` | la zona del cliente, **cuando el turno va de un cliente** |
| la presencia de la máquina | si puede ejecutar ahora mismo |

Va como mensaje de sistema **justo antes del turno de la persona**, que es donde
vive lo fresco. **No entra en el contexto de página** (D-6): ese va vallado
porque lleva texto de terceros, y una zona IANA validada no lo es.

---

## La migración

**Número**: el siguiente libre tras `0126`. **Va en H4** y es la única.

**No es destructiva**: añade una columna nula y reemplaza un `CHECK` por uno más
ancho. Aun así se ensaya **arriba, abajo y arriba**, como las tres de la spec
012.

**El `downgrade` tiene una decisión que tomar y hay que escribirla**: al estrechar
el `CHECK` de vuelta, cualquier fila de `teammate_changes` que ya nombre
`instructions` lo violaría. El `downgrade` **retira `'instructions'` de los
arrays existentes antes de estrechar**, y elimina las filas que se queden sin
ningún campo (`array_length >= 1` es parte de la restricción). Se pierde el
registro de que alguien cambió las instrucciones; no se pierde ninguna otra fila
ni ningún otro campo. **Bajar de versión no puede dejar el esquema roto**, y esto
es lo que cuesta.
