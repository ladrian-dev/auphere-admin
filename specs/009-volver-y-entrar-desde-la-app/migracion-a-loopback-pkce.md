# Plan — pasar la Historia 2 a loopback + PKCE (RFC 8252)

**Decidido por Luis el 2026-09-15**, sabiendo el coste. Sustituye al código
tecleado que se construyó antes en esta misma sesión.

Este documento existe porque el cambio **cruza paquetes y enmienda una spec
cerrada**, y `CLAUDE.md` pide que el plan viva en el repo y no en el chat.

## Por qué se cambia

Lo que se construyó era un Device Authorization Grant (RFC 8628) hecho a mano y
**al revés**: el navegador generaba el secreto y la persona lo tecleaba en la
aplicación. De ahí salieron los dos problemas de la sesión — la atadura a la
máquina imposible (Q2) y la falta de límite de intentos (🔴 de `/cso`).

Lo estándar para una aplicación de escritorio es **RFC 8252**: *authorization
code* + **PKCE**, con redirección a `127.0.0.1`. Es lo que hacen Claude Code,
`gh`, `gcloud` y Heroku.

**PKCE recupera lo que Q2 perdió.** El `code_verifier` se genera en la máquina y
no sale de ahí: quien vea el código en la URL no puede canjearlo sin él. La
atadura vuelve, y por un mecanismo que un auditor reconoce de un vistazo.

## Lo que hay que enmendar, y no es poco

| Qué | Por qué | Dónde |
|---|---|---|
| **Requisito 6 de la spec 001** — «El puente es saliente» | Un listener en loopback es entrante, aunque sólo desde la propia máquina | `specs/001-puesto-trabajo-partner/spec.md:250` |
| **`no-inbound.test.ts`** | Prohíbe `createServer` y `.listen(` en todo `src`. Pasa a permitir **exactamente uno**, y sigue cazando el resto | `apps/desktop/tests/no-inbound.test.ts` |
| **La descripción del paquete** | Dice «nothing from the internet reaches the partner's machine». Sigue siendo cierto de internet y deja de serlo de la máquina | `apps/desktop/package.json` |
| **spec 009, ADR-039, plan, research, tasks** | El mecanismo cambia entero | `specs/009-…/`, KB |

### Cómo queda el Requisito 6

No se borra: se acota. De «el puente nunca escucha» a **«el puente nunca escucha
en la red, y escucha en loopback sólo para el retorno del inicio de sesión»**,
con cuatro condiciones que el test comprueba:

1. **Sólo `127.0.0.1`**, nunca `0.0.0.0` ni una interfaz de red.
2. **Puerto efímero**, elegido por el sistema.
3. **Vive lo que dura el inicio de sesión** y se cierra al recibir el código o al
   caducar. No hay un servidor mientras la aplicación está abierta.
4. **Una sola ruta**, que sólo acepta `code` y `state` y no hace nada más.

## Lo que se conserva de lo ya construido

Bastante más de lo que parece:

- `console_auth.session_codes` — la tabla vale. El código pasa de tecleado a
  entregado por redirección, y `machine_hint` **vuelve**, ahora como
  `code_challenge`: lo mismo que quería Q2, con nombre estándar.
- El uso único, el TTL de diez minutos, el hash, y **el rechazo indistinguible**
  con sus tests. Todo eso es igual de necesario aquí.
- `console_identity.start_session(...)` sigue siendo quien acuña.

Lo que se tira: la hoja de teclear el código en la barra, `redeemCode` del
`preload` (vuelve a siete funciones) y la pantalla `/desktop-code` tal como está.

## Lo que hay que construir

**Escritorio**
1. PKCE: `code_verifier` aleatorio y su `code_challenge` (S256).
2. Servidor efímero en `127.0.0.1:0`, una ruta, `state` comprobado.
3. Abrir el navegador a la consola con `redirect_uri`, `state` y `code_challenge`.
4. Canjear `code` + `code_verifier` y cerrar el servidor.

**Consola / API**
5. `/desktop-auth` — con sesión iniciada (incluida la de Google), emite el código
   atado al `code_challenge` y redirige al `redirect_uri`. **Sólo se aceptan
   `redirect_uri` de `127.0.0.1`**, y eso se valida en el servidor.
6. El canje pasa a exigir `code_verifier` y a comprobarlo contra el challenge.

## Lo que este plan NO resuelve, y hay que decidir al llegar

- **El 🔴 de `/cso` sigue abierto**: PKCE no sustituye al límite de intentos.
  Hay que cablear `PairingRateLimiter` igualmente.
- **`/cso` se vuelve a pasar entero** cuando esto esté: cambia la superficie.
- **T012 y T013** de la Historia 1 siguen sin verificar.

## Orden

1. Enmiendas de gobierno: Requisito 6, el test, la descripción del paquete.
2. Enmiendas de la spec 009 y del ADR-039.
3. Retirar lo que sobra de la Historia 2.
4. Construir, test primero.
5. `verify.sh` entero y `/cso` de nuevo.
