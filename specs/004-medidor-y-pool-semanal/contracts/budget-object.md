# Contrato — el objeto de presupuesto, antes y después

El objeto `CompanionBudgetOut` lo devuelven **tres** rutas y lo pintan **tres**
superficies. Cambiarlo sin escribirlo aquí es cómo se rompe la aplicación de
escritorio desde la consola sin enterarse.

Lo consumen:

| Consumidor | Dónde |
|---|---|
| `GET /console/companion/budget` | respuesta entera |
| `GET /console/teammates/usage` | campo `budget` |
| Consola · Consumo | `apps/console/src/app/(console)/usage/` |
| Aplicación de escritorio · Cuenta | `apps/desktop/src/app/routes/account.tsx` (tipo `Budget`) |
| Panel de operador | `apps/admin/src/app/(dashboard)/partners/[id]/wallet` |

Este contrato **supera** la descripción del campo `budget` en
`specs/003-teammates-app-escritorio/contracts/teammates-api.md`, que se actualiza
en el mismo commit.

## Los campos

| Campo | Tipo | Antes | Después |
|---|---|---|---|
| `used` | `int` | `SUM(input+output)` sobre `companion.runs` del mes natural | `max(0, cap − included_remaining)` — **del libro** |
| `cap` | `int` | `partners.companion_monthly_token_cap` | `partners.weekly_pool_tokens` |
| `remaining` | `int` | `cap − used` (un cálculo) | `partner_wallets.included_remaining` (**la columna que decide**) |
| `percent` | `float` | igual | igual |
| `exhausted` | `bool` | `used >= cap` | `remaining <= 0` |
| `period` | `str` | mes UTC, `YYYY-MM` | **semana del partner, `YYYY-Www`** |
| `resets_at` | `datetime` | día 1 del mes siguiente | `partner_wallets.included_expires_at` |

**Ningún campo se quita y ninguno se añade.** Cambia de dónde salen, y `period`
cambia de formato.

### Por qué no se quitan `used` y `cap` aunque el partner ya no los vea

Porque el panel de operador los necesita para conciliar (R7.2), y un segundo
endpoint con los mismos datos sería exactamente el segundo camino de lectura que
esta spec elimina. El recorte es **de presentación**, y vive en la interfaz.

### La propiedad nueva, y es la que importa

`remaining` deja de ser una resta y pasa a ser **el mismo entero de la misma fila
que la plataforma consulta para dejar pasar un turno**. El número que se enseña y
el número que decide son uno.

Hoy no lo son, y por eso `/console/companion/budget` puede decir «20 % usado»
mientras `_require_wallet` responde `409 wallet_empty`.

## Qué NO cambia

- **La ruta, el permiso y la forma.** Mismos verbos, mismo `teammates:use` /
  `companion:use`, mismo JSON.
- **`by_teammate` de `/console/teammates/usage`.** Sigue siendo el reparto por
  teammate, sigue saliendo de `companion.runs` recorriendo membresías bajo RLS, y
  sigue **sin `cost_usd`** por la razón que ya estaba escrita: la fila del run no
  guarda con qué modelo corrió.
- **Ninguna ruta acepta `partner_id`, `principal_id` ni `tenant_id`.** Se toman
  del principal, como todo `/console/*`.

## Lo que la respuesta no puede llevar nunca

Ninguna de las tres rutas puede exponer, ni en esta spec ni en la siguiente:

- el identificador de otro partner o de otro tenant;
- contenido de conversación de un cliente final;
- un importe en dólares en la fila de un turno (decisión 14 de la KB).

Cubierto por `tests/isolation/test_console_scope.py`, que cubre
automáticamente todo endpoint `/console/*`.

## Migración del consumidor

| Consumidor | Qué tiene que cambiar |
|---|---|
| `packages/companion-ui` | **Sí cambia** — pinta cifras absolutas en dos sitios y habla de «mes» en seis cadenas. Detalle abajo |
| App de escritorio | la línea «X de Y tokens» pasa a barra + fecha (R7.1). **El `role="meter"` con sus tres valores se queda** (R7.4) |
| Consola · Consumo | igual para el pool incluido. **El saldo comprado sigue en unidades** (R7.6) |
| Panel de operador | nada: sigue pintando cifras absolutas (R7.2) |

Quien lea `period` esperando `YYYY-MM` verá `YYYY-Www`. **Cero consumidores lo
parsean** — verificado el 2026-09-11: las cinco apariciones lo tratan como cadena
opaca (`str(d.period)`), lo copian a `BudgetPause` y **no lo renderizan en ningún
componente**. Cambiar el formato es seguro.

## Los textos, que es donde estaba lo escondido

`packages/companion-ui/src/messages.ts` tiene **nueve cadenas** que esta spec
toca, y una de ellas pasa a ser **falsa** si nadie la mira.

### Lo que pinta cifras que R7.1 manda quitar

| Clave | Hoy | Qué pasa |
|---|---|---|
| `companion.meter.month.detail` | «{used} de {cap} tokens del tope mensual del Companion ({percent}%)» | Pasa a proporción y fecha. Se renombra: ya no es «month» |
| `companion.paused.body` | «Se alcanzó el tope de tokens del Companion de este mes: {used} de {cap}.» | Quita las cifras; dice el período y cuándo vuelve |

### Lo que deja de ser cierto — y es lo importante

| Clave | Hoy dice | Por qué se vuelve mentira |
|---|---|---|
| **`companion.paused.unblock`** | *«Se reanuda subiendo el tope. Escríbenos y lo ampliamos: no hace falta que reintentes, **esperar no lo desbloquea**.»* | Con el pool semanal, **esperar sí lo desbloquea**: vuelve solo en su fecha. Y con la caída a saldo comprado (R5.3), muchas veces **ni siquiera se pausa**. Dejar este texto sería una pantalla que miente, que es exactamente lo que §V prohíbe |

El texto nuevo tiene que decir las dos salidas que ahora existen —esperar a la
reposición, o tener saldo comprado— y **solo entonces** la de escribirnos.

### Lo que solo cambia de palabra

`companion.meter.month`, `companion.meter.exhausted.body` y las tres claves
hermanas que dicen «mes» / «month» / «mensual». Se renombran al período nuevo.

### Lo que NO se toca, y conviene decirlo

| Clave | Por qué se queda |
|---|---|
| `companion.meter.context.detail` | «{used} de {max} tokens de la ventana del modelo» — es la **ventana de contexto de la conversación**, no el pool. R7 no la alcanza |
| `companion.meter.turn.detail` | «{input} de entrada · {output} de salida» — es **este turno**, no el consumo incluido. Sigue siendo información útil e inmediata |

La distinción importa: R7 abstrae **el pool**, no todo número que aparezca en
pantalla. Borrar los tres medidores dejaría a la persona sin saber si la
conversación se está quedando sin ventana, que es un problema distinto y con otra
solución.
