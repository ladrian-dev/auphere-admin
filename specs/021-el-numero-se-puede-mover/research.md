# Fase 0 — investigación

Cinco decisiones, todas resueltas leyendo el código que hay. Una de ellas
corrigió la spec.

---

## D0 · Lo que ya existe y no hay que rehacer

| Pieza | Dónde | Estado |
|---|---|---|
| El 409 «número en uso» | `api/console/whatsapp.py:98` — captura `IntegrityError` sobre `uq_channels_type_provider_id` y devuelve `{"code": "number_in_use"}` (spec 016 R1.4) | **existe**; la spec decía que no |
| Reactivar la fila propia al reconectar | `signup.py:436` — el lookup `provider == "meta" AND provider_identifier == phone` **no filtra por estado**, así que bajo RLS encuentra la fila desvinculada del propio tenant y la pone `ACTIVE` | **existe**; R1.3 solo necesita test |
| Desuscribir la app | `meta_client.unsubscribe_app(waba_id, access_token)` → `DELETE /{waba_id}/subscribed_apps` | existe |
| Dar de baja el número | `POST /{phone_number_id}/deregister` | **no existe** en el cliente; `_post` sí |
| Desvincular en la consola | endpoint, acción, tarjeta, diálogo, vocabulario 0131 | en staging desde hoy |

La corrección importa: el problema **no** es un error técnico, es un aviso
correcto para el caso viejo y falso para el nuevo. Un número que A soltó le
sigue diciendo a B «en uso».

---

## D1 · La unicidad deja de contar los desvinculados

**Decisión**: sustituir la restricción por un **índice único parcial**:

```sql
CREATE UNIQUE INDEX uq_channels_live_number
  ON channels (type, provider_identifier)
  WHERE status <> 'disconnected';
```

**Por qué**. Es lo único que cumple R1.1 y R1.2 a la vez: dos canales vivos no
comparten número; uno vivo y uno desvinculado sí. El historial se queda, el
número se libera.

**Aislamiento**. El índice parcial no lee la fila ajena — deja de chocar con
ella. La RLS sigue mandando en toda lectura. Y R1.5 (no revelar de quién es un
número en uso) ya lo cumple el 409: dice `number_in_use` y nada más.

**Alternativas descartadas**:

- **Borrar la fila al desvincular**: libera el número, pero borra el historial
  y rompe R1.3 (reconectar recupera la misma ficha). Además las conversaciones
  apuntan al canal por id.
- **Unicidad por tenant**: dejaría que dos tenants tuvieran el mismo número
  vivo, que es justo lo que Meta no permite y lo que R1.1 prohíbe.

**Migración**: `0132_number_unique_when_live` — `DROP CONSTRAINT
uq_channels_type_provider_id` + `CREATE UNIQUE INDEX … WHERE`. Bajada: al
revés, y **falla si hay duplicados desvinculados** — se dice en la migración en
vez de borrar filas en silencio.

El nombre del índice cambia a propósito: `whatsapp.py:98` busca la cadena
`_NUMBER_UNIQUE` en el error; hay que actualizar esa constante o el 409 se
convertiría en 500.

---

## D2 · Deshacer en Meta, en el orden que no deja huérfanos

**Decisión**: dos transacciones, no una.

1. **Primera**: marcar el canal `disconnected` y anotar en `channels.config`
   qué queda pendiente en Meta: `unlink_pending: ["deregister", "unsubscribe"]`
   (`unsubscribe` solo si es el último número vivo de esa `waba_id` en el
   tenant). Commit. Desde aquí el agente ya no atiende: es lo que el partner
   pidió, y ya está hecho pase lo que pase con Meta.
2. **Después**: llamar a Meta paso a paso y **quitar de `unlink_pending` cada
   paso que termina**. Si todo termina, borrar las credenciales que toquen.
   Commit.

**Por qué en ese orden**. Si Meta se llama primero y el commit falla después,
el número queda dado de baja en Meta sin que la base lo sepa: exactamente el
silencio que R3 prohíbe. Con el estado escrito antes, un proceso que muere a
medias deja los pasos pendientes anotados, y el reintento (R3.2) los termina.

**«Último de la WABA»**: contar canales del tenant con
`config->>'waba_id'` igual y `status <> 'disconnected'`, **excluyendo el que
se está desvinculando**. Todo bajo RLS, en la sesión con scope.

**Credenciales**: si hay `config_encrypted` en el canal, se borra al terminar
`deregister`. Las del tenant (`tenant_credentials`) se borran solo con el
`unsubscribe`, y solo si ningún otro canal vivo del tenant depende de ellas
como respaldo — es decir, si era el último.

**Alternativa descartada — una sola transacción con Meta dentro**: es la que
deja huérfanos. Y la contraria —Meta primero, base después— es la que deja
la base mintiendo.

---

## D3 · Reintentar es volver a pulsar lo mismo

**Decisión**: el mismo endpoint `POST …/channels/{id}/disconnect` es el
reintento. Sobre un canal ya desvinculado con `unlink_pending` no vacío,
vuelve a intentar los pasos pendientes; sobre uno sin pendientes, no hace
nada (idempotente, como ya es hoy).

**Por qué**: un segundo verbo («terminar la desvinculación») sería enseñarle
al partner una distinción de implementación. Lo que él ve es «quedó algo
pendiente en Meta → reintentar», y la tarjeta ofrece exactamente eso.

---

## D4 · Qué le decimos a B cuando Meta aún retiene el número

**Decisión**: el alta de B ya recibe de Meta el error de que el número está
registrado en otra WABA; lo que falta es **traducirlo** en vez de dejarlo caer
al mensaje genérico. Un código nuevo en el 409 del alta,
`number_held_by_previous_owner`, con copia que dice que el dueño anterior
tiene que soltarlo en su Business Manager.

**Lo que no se hace**: llamar a Meta desde nuestro lado para soltarlo. Es su
activo (R2.4, decisión del owner).

---

## D5 · Coexistencia

Un número en modo `coexistence` sigue vivo en la app WhatsApp Business del
partner. `deregister` lo retira del Cloud API, **no** de la app: el partner
sigue chateando desde su móvil. Es lo correcto — «desvincular» es soltarlo
de nosotros, no dejarlo sin WhatsApp — y el aviso lo dice.

**Medido en staging el 2026-09-29 con el número real (`+34653321693`, en
coexistencia)**: Meta **rechazó** `deregister`, y por el orden de los pasos
`unsubscribe` no llegó a intentarse. El motivo no quedó escrito —el endpoint
no lo guardaba—; ahora se anota en `config.unlink_error` y en la auditoría.

**Decisión**: un número en coexistencia **nunca se da de baja**. Es lo
simétrico del alta, que en coexistencia se salta `register` porque Meta
contesta `CallingNotAllowed`: lo que no se registró no se puede dar de baja.
Los pasos de un canal en coexistencia son solo `unsubscribe`, y solo si era
el último de su cuenta. Un `deregister` que quedó anotado antes de esta regla
se descarta al reintentar.

Visto en staging al reintentar: `unsubscribe` pasa. Y **en producción el
2026-09-30**, con el `+34672138367` (canal de agosto, «conectar número propio»,
sin `mode` guardado), Meta lo dijo con estas palabras:

> `400 · code 100 · Deregister endpoint is not available for API solution for SMB businesses.`

Esa frase **es** coexistencia. Desde entonces, un rechazo así no queda
pendiente: `deregister` se anota como omitido, el canal aprende
`mode = coexistence`, y la desuscripción sigue.

### La premisa de R2.3 era falsa en producción

R2.3 decía «el último número no desvinculado de esa WABA **en ese cliente**».
Los números propios de Auphere («conectar número propio») comparten cuenta
entre clientes: la WABA `725663313243186` ha atendido a Mouna y a la demo de
farmacia. Desuscribir la aplicación por haber soltado el último número *de un
cliente* dejaría mudos los de los demás. La pregunta se hace ahora a **toda la
plataforma** con `count_live_channels_for_waba` (migración 0133): una función
`SECURITY DEFINER` que devuelve solo cuántos, nunca cuáles ni de quién — el
mismo patrón que `resolve_channel_tenant`. El aislamiento no cambia de
promesa: el cliente que suelta sigue sin poder averiguar nada del otro.


---

## Lo que no hizo falta investigar

- **Dependencias nuevas**: ninguna.
- **Permisos**: `channels:write`, el que ya exige desvincular.
- **Playground**: su canal interno tiene `provider = qa_playground` y no es un
  número; el índice parcial lo incluye igual que el viejo, sin cambio.
