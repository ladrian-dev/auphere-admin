# Modelo de datos — spec 012

**Resumen: dos migraciones, y ninguna añade una columna.**

Nada de lo que esta spec construye necesita un campo nuevo. Eso no es
casualidad: casi todo lo que hace falta ya estaba declarado y **sin usar**, que
es otra forma de decir que el defecto llevaba tiempo ahí.

> **Corrección del 2026-09-22, al implementar US1.** Este documento decía «una
> sola migración». Eran dos, y conviene que quede escrito en vez de arreglado en
> silencio: se miró que `revoked_at` y el motivo ya existían, y no se miró que
> este repositorio tiene un **vocabulario de auditoría sembrado por migración**.
> Una acción nueva sin su frase se pinta con el fallback crudo
> —`actor · accion · target`—, que no miente pero no se entiende. El aviso ya
> estaba escrito en `api/console/support.py`: «un valor nuevo obliga a tocar los
> dos sitios». Así que:
>
> | Migración | Qué hace | Cuándo |
> |---|---|---|
> | `0124_access_revoked_vocab` | **Aditiva**: la frase de `principal.access_revoked` | con **US1** |
> | la del final | **Destructiva**: retira `device_pairing_codes` | con **US6** |

---

## Lo que ya existe y se usa como está

### `partner_devices` — la máquina registrada

De **un partner** y de **una persona de ese partner**. Nunca lleva `tenant_id`:
una máquina no es de un cliente final, y por eso la credencial que la nombra
tampoco menciona tenant.

| Campo | Se usa en | Nota |
|---|---|---|
| `partner_id` | RLS | La garantía 1 la alcanza por aquí |
| `principal_id` | R1, R3.7, R4 | El eje de persona dentro del partner |
| `revoked_at`, `revoked_reason` | R1, R2 | **Ya existían.** Lo que faltaba era quien los escribiera |
| `last_heartbeat_at` | — | La presencia se deriva de él; no se toca |

**El motivo `"desemparejada"` ya está en el CHECK** de motivos de revocación
(`db/models/local_workstation.py:97-105`) y **no lo escribe nadie**. R2 le pone
el escritor. No hay migración: hay un hueco que se rellena.

### `console_auth.principal_sessions` — la sesión de consola

| Campo | Se usa en | Nota |
|---|---|---|
| `principal_id` | R1 | Tiene índice (`ix_console_sessions_principal`): el borrado en bloque es barato |
| `created_at` | **R3.2** | Cuándo se entró por el navegador. **No se mueve con el uso** |
| `last_used_at` | — | Se mueve con cada petición. **No sirve para R3.2**, y confundirlos es el error silencioso que este documento existe para evitar |
| `expires_at` | — | Caducidad absoluta de 7 días, no se renueva |

### `device_client_links` — qué carpeta toca un teammate

Existe entera, con sus asientos de auditoría (`device.link_declared` /
`device.link_denied`). H5 no la cambia: la saca a la superficie.

### `audit_log` — el vocabulario ya está completo

La migración `0108_device_audit_vocab` declaró ocho acciones. Siete tienen
escritor. **`device.unpaired` no lo tiene**, desde que se declaró.

| Acción | Escritor hoy | Después |
|---|---|---|
| `device.pair_code_issued` | consola | **desaparece** con R6 |
| `device.paired` | canje | sigue, desde el registro nuevo |
| `device.pair_denied` | canje | sigue, desde el registro nuevo |
| `device.renewed` | la máquina | sin cambios |
| `device.link_declared` / `link_denied` | el puente | sin cambios |
| `device.archived` | consola | sin cambios |
| **`device.unpaired`** | **nadie** | **R2.2 le pone escritor** |
| **`principal.access_revoked`** | **no existe** | **la crea US1** — es el único acto nuevo |

Para el eje de máquinas basta con usar el vocabulario que hay. Para R1 no: hay
un acto que no existía, y un acto nuevo trae su frase (ver la corrección de
arriba). Severidad `warning` y no `info`, porque no es una preferencia que
alguien cambió: es una persona que se quedó fuera.

---

## Lo que se retira

### `device_pairing_codes` — la tabla del código

Se borra entera en la **única migración** de la spec, y va **la última**, cuando
R6 se entrega y ya nadie escribe en ella.

- **Es destructiva.** Se ensaya arriba, abajo y arriba, como se hizo con la 0123.
- **El `downgrade` recrea la tabla vacía.** No se restauran códigos —son secretos
  de diez minutos y bajar una versión no debería resucitar credenciales— pero sí
  la forma, para que bajar no deje el esquema roto.
- Con ella desaparece **el único secreto de registro que había en reposo**. R7.4
  pasa de ser una promesa a ser cierta por construcción.

---

## Reglas que el modelo tiene que sostener

| Regla | De dónde sale | Cómo se sostiene |
|---|---|---|
| Retirar el acceso es atómico | R1.2 | Una transacción. Las dos tablas están en el **mismo Postgres** (`console_auth` es un esquema, mismo `Base`, mismo engine) |
| Retirar el acceso no alcanza a otra persona | R1.5 | La operación corre con rol dueño, así que **la RLS no la protege**: lo hace el `WHERE` por `principal_id`, y eso necesita su test de aislamiento |
| Las archivadas no cuentan para el tope | R4.3 | `WHERE revoked_at IS NULL`. Si contaran, cada restablecimiento de contraseña (D-6) cerraría el tope un poco más: sería un tope que se cierra solo |
| Registrar dos veces la misma máquina no crea dos | R3.7 | Se busca la activa de esa persona para esa máquina antes de crear |
| Volver a registrar tras archivar crea fila nueva | casos límite | Archivar es **terminal**. Deja de ser caso raro: es el camino después de cada restablecimiento (D-6) |

---

## Qué identifica a «la misma máquina» (T030, decidido el 2026-09-22)

**Decisión: un identificador de instalación que genera la aplicación y guarda
en su carpeta de datos, aparte de la credencial. Columna nueva `install_id` en
`partner_devices`, nullable.**

Hoy la máquina se identifica por `hostname` + `platform` y nada más
(`app-runtime.ts:89`). Ninguno de los dos sirve para R3.7:

- **`hostname` cambia** cuando alguien renombra su ordenador, cosa que pasa.
- **`hostname` no es único**: dos «MacBook-Pro» en el mismo partner son
  perfectamente posibles.

Con `hostname` como clave, renombrar el ordenador crea una **máquina fantasma**
—dos filas donde hay un ordenador— y dos ordenadores iguales se pisan. Lo
primero consume tope (R4) y lo segundo es peor: dos personas creyendo que
manejan la misma fila.

**Por qué aparte de la credencial.** Si el identificador viviera junto a la
credencial, desemparejar lo borraría y volver a registrar crearía una máquina
nueva cada vez — justo el caso que R3.7 quiere evitar, y que con registro
silencioso pasa a ser frecuente. Va en un fichero propio de la carpeta de datos.

**Qué NO sobrevive, y está bien que no sobreviva**: borrar el perfil de la
aplicación o reinstalar el sistema. Entonces es, de verdad, una instalación
nueva, y tratarla como tal es honesto. Lo contrario —atar la identidad a algo del
hardware— sería un identificador persistente de dispositivo, que es otra cosa y
con otras implicaciones.

**Nullable**, porque las filas de hoy no lo tienen y no se inventa: una máquina
registrada antes del cambio sigue valiendo (R6.2) y sencillamente no participa
de la deduplicación hasta que se vuelva a registrar.

### Consecuencia: una migración más

| Migración | Qué hace | Cuándo |
|---|---|---|
| `0124_access_revoked_vocab` | aditiva: la frase de auditoría | con US1 ✅ |
| `01XX_device_install_id` | aditiva: `install_id` nullable | con **US3** |
| `01XX_drop_device_pairing_codes` | destructiva | con **US6** |

Ésta **no es una corrección del plan como lo fue la del vocabulario**: este
documento dejó la pregunta abierta a propósito y avisó de que tenía consecuencia
visible. La consecuencia resultó ser una columna.
