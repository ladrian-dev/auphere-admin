# Fase 0 — Investigación: el registro de partners

Lo que había que averiguar antes de diseñar, y lo que se encontró leyendo el
código, no suponiéndolo. Cada punto termina en una decisión.

---

## R1 · Cuánto de esto ya existe

**Decisión: el alta no construye un camino nuevo a `partner_memberships`.
Reutiliza el de invitación, entero.**

`PartnerInvitationRepository.accept()` ya hace lo que el registro necesita:
valida el token, comprueba que el correo de la cuenta coincide con el invitado,
rechaza a quien ya pertenece a un partner, crea el principal en
`console_auth.principals` si no existe, crea la membresía y devuelve sesión.
Sus reglas de error ya son estables (`expired`, `not_pending`,
`email_mismatch`, `already_member`).

Lo único que no sabe hacer es **que el partner no exista todavía**.

Por tanto el alta es: crear el `partner`, emitir una invitación de `owner` al
correo ya verificado, y **aceptarla en la misma transacción**. Una sola función
crea membresías en todo el repositorio.

*Alternativa descartada:* un `signup_service` que escriba `partner_memberships`
por su cuenta. Dos caminos a la misma tabla divergen, y el que menos se usa es
el que se queda sin la regla nueva.

---

## R2 · Los endpoints de registro **no pueden ser anónimos** en la API

**Decisión: van detrás del token de servicio del BFF, como `/console/auth/*` y
`/console/invitations/*`.**

`tests/isolation/test_console_scope.py` es estructural sobre **todas** las rutas
registradas, y su regla 5 dice: *sin token, 401 en todas*. Un endpoint de
registro abierto la pondría en rojo el día que se monta — y esa suite bloquea el
merge.

No es una molestia del test: es la forma del sistema desde ADR-032. El navegador
nunca habla con la API; habla con el BFF, y el BFF acuña un token EdDSA de 60 s
por llamada. La anonimidad del registro vive en el borde
**navegador ↔ BFF**, no en **BFF ↔ API**.

**Consecuencia que hay que diseñar:** el token de servicio no identifica a una
persona, así que el limitador de ritmo no puede salir de él. Ver R3.

---

## R3 · El limitador «por IP» del login no limita por IP

**Hallazgo, y es previo a esta spec.** `api/console/auth.py` documenta dos cubos
independientes: uno por correo y otro por IP, éste para *«frenar el barrido de
muchas cuentas desde una»*. La IP sale de `request.client.host`.

Pero **nada reenvía la IP del cliente**: no hay lectura de `X-Forwarded-For` en
`api/console/` ni en `core/`, y el BFF no la manda. Detrás de Vercel,
`request.client.host` es la IP de salida del BFF **para todo el mundo**. El cubo
«por IP» es hoy un único cubo global compartido por todos los visitantes.

Con un formulario de login eso es malo. Con un **formulario de alta abierto**,
que además manda correo, es el vector entero.

**Decisión: el BFF reenvía la IP del cliente en una cabecera propia, y la API la
lee sólo de ahí.**

Tres razones para una cabecera propia (`X-Nexus-Client-IP`) y no `X-Forwarded-For`:

1. `X-Forwarded-For` lo puede poner cualquiera que alcance la API. Una cabecera
   que sólo el BFF pone, dentro de una petición que ya va firmada con el token
   de servicio, no es falsificable por un tercero.
2. La API no tiene que adivinar cuántos proxies hay delante ni cuál de la lista
   es el cliente real.
3. Si la cabecera falta, el comportamiento es **explícito y cerrado**: se cuenta
   contra un cubo único y estrecho, en vez de fingir que hay límite por IP.

**Esto arregla de paso el login.** Es un efecto declarado, no un polizón: lleva
su propia tarea y su propio test, y se dice en el plan que el comportamiento del
login cambia (empieza a limitar por IP de verdad, que es lo que su docstring ya
prometía).

---

## R4 · Google: qué se instala, y la respuesta es nada

**Decisión: OIDC contra Google con código de autorización + PKCE, verificando el
ID token contra el JWKS de Google con `pyjwt`. Cero dependencias nuevas.**

`pyjwt>=2.9.0` ya está en `apps/api/pyproject.toml` y trae `PyJWKClient`, que es
exactamente el cliente de JWKS con caché que hace falta. El intercambio del
código es un `POST` con `httpx`, que también está.

**Puerta de licencias (constitución §VIII): no se abre.** Ninguna dependencia
nueva entra por esta spec, así que no hay licencia que leer ni párrafo que citar.

El `state` **no se inventa**: copia el patrón de
`services/tiktok_oauth_state.py` — payload canónico, HMAC-SHA256 verificado con
`compare_digest`, nonce, TTL corto, formato `base64url(payload).base64url(firma)`.
Ese módulo existe justamente porque un `state` sin firmar permitía injertar una
cuenta ajena en otro tenant; aquí el riesgo equivalente es injertar un proveedor
en la cuenta de otra persona.

El `code_verifier` de PKCE **no cabe en el `state`** (viajaría al navegador): se
guarda en Redis bajo el nonce, con el mismo TTL, y se consume una sola vez.

*Alternativa descartada:* Google Identity Services (el botón que devuelve un ID
token al navegador). Es sólo autenticación: no da refresh token ni ámbitos
incrementales, y la parte de «próximas integraciones» habría que construirla
otra vez. *Alternativa descartada:* un proveedor de identidad de terceros —
deshace ADR-032, cobra por usuario activo y mete un tercero en el camino
crítico del login.

---

## R5 · Dónde se ancla la identidad del proveedor

**Decisión: tabla nueva `console_auth.principal_identities`, con única en
`(provider, subject)`.**

El `sub` de Google es estable y opaco; el correo **no** es identidad: cambia de
dueño, y en Workspace se reasigna. Anclar al correo permitiría que quien herede
una dirección herede la cuenta.

La tabla admite varios vínculos por cuenta desde el primer día, que es lo que la
spec pide en §Fuera de alcance («añadir el segundo no obliga a rehacer el
primero»). Va en el esquema `console_auth`, junto a `principals`, porque es
identidad y no plataforma.

**No se guarda ningún token de Google en esta spec.** El `access_token` se usa
para nada —el `id_token` ya trae `sub` y `email_verified`— y el `refresh_token`
no se pide, porque no hay ámbito que refrescar todavía. La columna para
guardarlos se añadirá cuando exista la spec que los use; hoy sería una
credencial almacenada sin lector, que es la misma figura que
`NEXUS_WEBHOOK_HMAC_SECRET`.

---

## R6 · La solicitud de alta y su token

**Decisión: tabla nueva `signup_requests` en `public`, token sólo hasheado, TTL
de 24 h.**

Se sigue el patrón de `partner_invitations` (SHA-256, un solo uso, se enseña una
vez) porque es el que el repositorio ya sabe operar y auditar.

**El TTL es distinto a propósito: 24 h, no los 21 días de una invitación.** Una
invitación la manda una persona que conoces y puede esperar tres semanas; una
solicitud de alta la pide un desconocido y el correo está en su bandeja ahora
mismo. Cuanto más corta la ventana, menos vale un buzón comprometido.

La fila se extingue al completarse el alta o al caducar. **No deja partner
huérfano**: la fila de solicitud no crea nada — el partner nace en el segundo
paso, en una sola transacción.

---

## R7 · Free ya existe y no hay que sembrar nada

**Decisión: el partner nace sin fila en `partner_subscriptions`.**

`db/models/membership.py` lo dice explícito: *«A partner with no row is Free.
Absence is a valid state and is designed as one»*. Free son un miembro, cero
teammates y un pool semanal de 100 000.

Y por la decisión D3 de `/speckit-clarify`, dar de alta clientes finales en Free
**no necesita tope nuevo**: el medidor de la spec 005 ya lo decide, porque los
clientes finales gastan sólo saldo comprado. Inventar un límite aquí sería el
segundo contador sobre el mismo gasto que ADR-037 acaba de eliminar.

---

## R8 · Correo transaccional a desconocidos

**Decisión: se usa `services/email.py`, y la entregabilidad se mide, no se
supone.**

`send_email()` existe y lo usa el alta por invitación. La diferencia es a quién:
hasta ahora, a personas que esperaban el correo; ahora, a desconocidos que
acaban de teclear su dirección, y ahí entran SPF/DKIM/DMARC y la reputación del
dominio.

No se cambia de proveedor por si acaso. Lo que sí entra en el plan es una tarea
de verificación: enviar a los tres dominios que más aparecen en el ICP y
comprobar dónde cae. Si cae en spam, eso es un hallazgo con su propia
corrección, no una suposición que se arrastra.

---

## R9 · Migración

Última aplicada en producción: `0117_billing_events`. Esta spec añade
**`0118_signup_and_identities`** con las dos tablas nuevas
(`public.signup_requests` y `console_auth.principal_identities`) y ninguna
modificación de tablas existentes.
