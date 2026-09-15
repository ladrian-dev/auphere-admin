# Bug Assessment: el tope del plan se cuenta como avería pasajera

- **Slug**: teammate-tope-de-plan-mensaje-generico
- **Created**: 2026-09-15
- **Source**: pasted text (reproducido por Luis con la app instalada)
- **Verdict**: valid
- **Severity**: medium

## Report

Crear un teammate desde la app de escritorio devuelve:

> **No se pudo crear. No se ha creado nada; vuelve a intentarlo.**

Confirmado por Luis el 2026-09-15: **el partner de prueba está en Free**, y Free tiene
`max_teammates = 0` (migración `0116`).

## Symptom

La API rechaza **correctamente** —el plan no incluye teammates— y la pantalla presenta
ese rechazo como un fallo transitorio, invitando a reintentar algo que nunca va a
funcionar. Se esperaba que dijera que es el plan, y que no queda nada que reintentar.

**El fallo está enteramente en lo que la pantalla dice.** Ni la API ni el BFF tienen
nada que arreglar: los dos hacen bien su parte, incluido mandar los números.

## Reproduction

1. Entrar en la app de escritorio con una persona de un partner en Free.
2. Equipo → «Crear teammate».
3. Rellenar nombre, oficio, modelo y permisos.
4. Enviar.
5. Sale «No se pudo crear. No se ha creado nada; vuelve a intentarlo.»

## Suspected Code Paths

Recorrido completo del error, de donde nace a donde se pierde:

- `apps/api/src/nexus_api/api/console/teammates.py:242-249` — `_refuse("tier_limit_reached",
  kind=…, limit=…, current=…, tier=…)`: un 422 con
  `detail = {"code": "tier_limit_reached", "kind": "teammates", "limit": 0, "current": 0, "tier": "free"}`.
  **Correcto.** Va a propósito antes de validar el modelo, con la razón escrita al lado:
  comprobarlo primero haría que un partner en Free viera un error sobre modelos cuando lo
  que le falta es plan.
- `apps/api/src/nexus_api/services/membership_limits.py` — `TierLimitReached`. Su
  docstring dice por qué carga los números: *«A message that only says "limit reached"
  makes someone open a support ticket to learn a number we already know.»* Esa intención
  es la que hoy se pierde por el camino.
- `apps/console/src/app/api/companion/_guard.ts:44-63` (`describe`) y `:90` — **correcto**:
  saca `code` del `detail` anidado y sube `limit`, `current` y `tier` como extras al nivel
  superior, respondiendo `{...extra, detail, code}`.
- `apps/desktop/src/platform-client.ts:76-82` — **correcto**: conserva `code` y el `body`
  entero en `Err`. `redact` (`app-ipc.ts:134`) solo quita claves de credencial, así que
  los tres números sobreviven al IPC.
- `apps/desktop/src/app/App.tsx:296` — **aquí se pierden los números**:
  `return { ok: false as const, error: res.code ?? "unknown" }` descarta `res.body`.
- `apps/desktop/src/app/routes/new-teammate.tsx:72` — **aquí se pierde el código**:
  `KNOWN_ERRORS = ["model_not_allowed", "tool_not_in_catalog"]`. `tier_limit_reached` no
  está, así que la línea 244 cae en `create.failed.unknown` (`i18n.ts:67`).
- `apps/desktop/src/app/routes/teammate-settings.tsx:195` — comparte `isKnownError` y la
  misma lista, con su propio genérico. Hereda el problema, aunque ahí `tier_limit_reached`
  no se puede dar: editar un teammate no crea ninguno.

## Root Cause Hypothesis

**Confianza: alta.** Dos omisiones independientes en la app, ninguna en el servidor.

1. `tier_limit_reached` nunca se añadió a `KNOWN_ERRORS`, así que se trata como
   desconocido y se le aplica la copia de «vuelve a intentarlo».
2. `App.tsx:296` reduce el error a su `code` y tira el cuerpo, así que aunque el código
   se reconociera, la pantalla no tendría con qué decir de cuánto es el tope.

La primera es la que produce el síntoma. La segunda es la que impide arreglarlo bien.

Es deuda de nacimiento, no una regresión: la lista blanca se escribió en la spec 003 y el
tope del plan llegó en la 005 sin volver a pasar por esa lista.

## Proposed Remediation

**Preferido: decir que es el plan, con el número, y ofrecer el camino para cambiarlo.**

Tres piezas pequeñas:

1. **`App.tsx:296`** — dejar de tirar el cuerpo. El `Err` ya trae `limit`, `current` y
   `tier`; se leen con una guarda de tipo y se pasan junto al código.
2. **`new-teammate.tsx`** — añadir `tier_limit_reached` a `KNOWN_ERRORS` y elegir la
   frase según el tope.
3. **`i18n.ts`** — dos claves nuevas, en `es` y en `en`.

**Las dos frases son distintas y esto no es cosmético.** Con Free, `limit` y `current`
valen los dos `0`: «tu plan admite 0 teammates y ya tienes 0» es una frase absurda que
además suena a error del sistema. Son dos situaciones que la persona vive distinto:

- `limit === 0` — *«Tu plan no incluye teammates. Para crear uno hay que cambiar de plan,
  desde Cuenta.»* No hay nada que liberar; lo único que mueve la aguja es el plan.
- `limit > 0` — *«Tu plan admite {limit} teammates y ya tienes {current}. Archiva uno o
  cambia de plan, desde Cuenta.»* Aquí sí hay dos salidas, y archivar es la gratis.

Ambas nombran **Cuenta**, que es la pantalla que ya existe y que lleva a la consola
(`account.tsx:233`, `account.openConsole`). Sin eso la frase explica el muro y no la
puerta.

Ninguna dice «vuelve a intentarlo», que es la palabra que sobra: no hay nada que
reintentar.

**Alternativa, y es la que respeta mejor la constitución §V: no ofrecer el formulario.**

§V dice que «cuando una capacidad no está disponible, no hay botón apagado ni pantalla que
explique lo que no tienes: **la ausencia se diseña**». Y `new-teammate.tsx` ya aplica ese
principio para el caso de cero modelos, con este comentario:

> *Sin modelos no hay teammate posible: la lista la decide un administrador en la consola.
> Pintar el formulario y fallar al enviar sería hacerle escribir para nada (§V).*

El argumento vale igual aquí: un partner en Free **nunca** puede crear un teammate, así
que hacerle rellenar nombre, oficio, modelo y cinco permisos para después decirle que no
es exactamente lo que ese comentario prohíbe.

**No se propone como preferida porque hoy no se puede hacer.** Comprobado: la app no
conoce el tope. Lo único que pide es `/api/teammates/usage` (`app-surface.ts:156`), que
devuelve el medidor y el reparto por teammate, **sin `max_teammates`**. Saberlo antes de
pintar exige un campo nuevo en una respuesta de la API — comportamiento de producto
nuevo, que entra por `/speckit-specify` y no por el flujo de bugs.

Queda anotado como seguimiento. El arreglo del mensaje no estorba a esa spec: la frase
seguiría haciendo falta para el caso `limit > 0`, donde el formulario **sí** debe pintarse
y el rechazo llega al enviar.

**Files likely to change**:
- `apps/desktop/src/app/App.tsx`
- `apps/desktop/src/app/routes/new-teammate.tsx`
- `apps/desktop/src/app/i18n.ts`
- `apps/desktop/tests/new-teammate-form.test.tsx`

**Tests to add or update** (en `tests/new-teammate-form.test.tsx`, que ya tiene 14 casos,
entre ellos «si falla, lo dice y conserva lo escrito» y «un error que no conocemos también
se dice, sin código crudo»):

- Con `tier_limit_reached` y `limit: 0`: la pantalla nombra el plan y **no** dice «vuelve
  a intentarlo».
- Con `tier_limit_reached` y `limit: 3, current: 3`: la frase trae los dos números y
  menciona archivar.
- Lo escrito en el formulario **sobrevive** al rechazo, como en el caso ya cubierto: si
  la salida es cambiar de plan, perder lo tecleado es castigo doble.
- El genérico sigue saliendo para un código de verdad desconocido — que el caso existente
  siga en verde es lo que prueba que no se ha roto la red de seguridad.

## Risks & Considerations

- **No toca la API ni el BFF.** El cambio vive entero en la app de escritorio. Producción
  tiene 3 clientes reales con tráfico y ninguno se ve afectado por esto.
- **No toca ninguna frontera de tenant**; ninguna de las 7 garantías queda rozada, así que
  no hace falta test en `tests/isolation/`.
- **Sin dependencias nuevas**, así que no hay licencia que leer (§VIII).
- **Leer `res.body` sin confiar en su forma.** Viene de la red; la guarda de tipo tiene
  que tolerar que falte o venga con otra forma y caer al mensaje sin números, nunca
  pintar `undefined`.
- **La copia se escribe en `es` y `en`.** La app elige idioma por la cuenta; dejar una de
  las dos a medias deja a la mitad de los partners con la clave cruda en pantalla.
- **`tier_limit_reached` tiene un hermano.** `assert_can_add_member` lanza el mismo código
  con `kind: "personas"` al invitar a alguien. Esa ruta no está en la app de escritorio,
  pero si algún día lo está, la frase de teammates no sirve: conviene que el código de la
  pantalla se apoye en `limit`/`current` y no dé por supuesto el `kind`.

## Open Questions

Ninguna que bloquee. Una para después:

- ¿Se abre spec para llevar `max_teammates` a `/api/teammates/usage` y dejar de pintar un
  formulario que un partner en Free no puede terminar (§V)? Decisión de Luis; no bloquea
  este arreglo.
