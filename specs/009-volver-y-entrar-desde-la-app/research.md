# Fase 0 — investigación

**Spec**: [spec.md](spec.md) · **Fecha**: 2026-09-15

Las cuatro decisiones de producto ya estaban cerradas por `/speckit-clarify` y el
[[ADR-039]]. Lo que quedaba era averiguar **qué hay ya construido**, porque de eso
depende cuánto de esto es código nuevo. La respuesta corta: bastante menos de lo
que parecía.

---

## D1 · Cómo acuña sesiones la consola hoy

**Decisión**: el canje del código llama a `console_identity.start_session(...)`, la
misma función que usa el callback de Google. No se escribe un segundo camino.

**Fundamento**: `apps/api/src/nexus_api/api/console/auth_google.py:176` ya hace
exactamente lo que la Q1 decidió — acuñar una sesión nueva — y devuelve
`(token, expires_at)`. Reimplementarlo sería tener dos formas de crear una sesión,
que es como se acaba con dos caducidades distintas y un agujero en una de ellas.

**Alternativas**: copiar la cookie del navegador (descartada en Q1: un secreto en
dos sitios); un token intermedio (descartada: un segundo secreto que vigilar).

## D2 · La sesión de la app ya es distinguible, sin columnas nuevas

**Decisión**: no se añade ninguna marca «esta sesión es de la aplicación». Se usa
el `user_agent` que `principal_sessions` ya guarda.

**Fundamento**: la cáscara se anuncia. `main.ts:83` añade `AuphereDesktop/<versión>`
al *user agent* de la partición humana, y lo hace desde la spec 002 con este
propósito declarado: «la consola sabe que la carga la cáscara **solo** por esto».
`ConsoleSession` guarda `user_agent` y `ip`. Así que «qué máquina hizo qué» (R4.2,
R5.5) se responde con lo que ya se persiste.

**Alternativas**: una columna `origin` en `principal_sessions` — rechazada: añade
migración y un dato que ya existe, escrito dos veces y con riesgo de discrepar.

## D3 · Las primitivas del código se reutilizan enteras; lo que cambia es qué ata

**Decisión**: `core/pairing_codes.py` tal cual —`ALPHABET` sin `I`/`L`/`O`/`U`,
`CODE_LENGTH = 8`, `CODE_TTL = 10 min`, `generate_code`, `display_code`,
`normalize_code`, `hash_code`— y `PairingRateLimiter` para los intentos.

**Fundamento**: son exactamente las mismas propiedades que se necesitan aquí, y ya
están probadas. Dos alfabetos distintos para dos códigos que se teclean en la
misma hoja de la misma barra sería una diferencia que nadie podría explicar.

**Lo que NO se reutiliza y es el corazón de la spec**: `device_pairing.py` ata una
**máquina** y emite una credencial de dispositivo. Aquí se ata una **persona** y se
emite una sesión. Misma cerradura, llave distinta.

## D4 · La huella de máquina que ya viaja

**Decisión**: para atar el código (Q2 / R5.3) se usa `hostname` + plataforma, que
es lo que `HttpTransport.pair()` ya manda en el canje de emparejamiento.

**Fundamento**: `main.ts:197` construye `machine: { hostname: osHostname(), platform }`
y el runtime lo pasa en cada `pair`. No hay que recoger nada nuevo, que es lo que
convierte «atar el código» en una comprobación y no en una recogida de datos.

**Riesgo anotado**: `hostname` no es único ni infalsificable. No pretende serlo:
cierra el caso de la pantalla compartida (alguien que lee el código y lo teclea en
**su** portátil), no el de un atacante que ya controla la máquina de la víctima —
ése ya perdió antes de llegar aquí.

## D5 · Cómo llega el código a la barra sin romper el test que prohíbe `session`

**Decisión**: la función nueva del `preload` se llama **`redeemCode`** y el canal
IPC **`bar:redeem`**. La barra manda un código y recibe un estado; no ve tokens ni
cookies.

**Fundamento**: `no-own-auth.test.ts:38` prohíbe las cadenas `login`, `session`,
`cookie` y `token` en el texto del `preload`, y esa prohibición es el Requisito 2.1
de la spec 002: **la aplicación no tiene autenticación propia**. Nombrarlo
`redeemCode` no es esquivar el test: es que el hecho sigue siendo cierto. La barra
entrega ocho caracteres que la persona tecleó; quien habla con la plataforma y
quien guarda lo que vuelve es el proceso principal, exactamente como con `pair`.

**Consecuencia**: la prohibición se mantiene tal cual. No hay que enmendarla, y
R2.5 de la spec queda satisfecho sin excepción.

## D6 · La vuelta a la app: `showApp`, no una función nueva por cada superficie

**Decisión**: una función `showApp()` en el `preload` y un `bar:showApp` en el
principal.

**Fundamento**: `showSurface("app")` ya existe en `main.ts:134` y lo llaman el
menú, la bandeja y el atajo global. La barra necesita **una** forma de invocarlo,
no una API de navegación. Una función que sólo sabe volver es más pequeña de
auditar que una que acepta a dónde ir.

**Alternativa rechazada**: `showSurface(name)` parametrizada — daría a la barra la
capacidad de mandar a la consola a cualquier sitio, que es más de lo que hace
falta y más de lo que se puede justificar al ampliar una lista cerrada.

## D7 · Dónde vive el código en la base de datos

**Decisión**: tabla nueva `console_auth.session_codes`, migración **0122**.

**Fundamento**: la más alta hoy es `0121_companion_run_native_input`. Va en el
esquema `console_auth` porque pertenece a la identidad de consola, junto a
`principals`, `principal_sessions` y `principal_identities`. Se guarda el **hash**
(mismo patrón que `principal_sessions`, cuya PK es el hash del token: «un volcado
de la tabla no permite entrar en ninguna cuenta»).

## D8 · Dependencias nuevas

**Ninguna.** Todo sale de lo que ya está instalado: `pairing_codes`, el limitador
en Redis, `console_identity`, y en el escritorio el IPC que ya existe. No hay
licencia que leer (§VIII).
