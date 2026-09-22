# Research: recuperar la contraseña

- **Slug**: recuperar-la-contrasena
- **Fecha**: 2026-09-22
- **Método**: lectura directa del código de este repositorio (ruta:línea y cita
  literal en cada afirmación) + los referentes externos de
  [[research/2026-09-19-auditoria-clase-mundial/06-referentes-externos]] §D.
- **Pregunta que esta fase tiene que dejar contestable**: la del intake —
  **«¿hace falta contraseña?»**— más las cuatro de diseño que cuelgan de ella.

---

## 0 · El titular

Hay **tres** hallazgos que cambian la forma de lo que se construya, y ninguno
estaba en el intake.

1. **La función que restablece la contraseña ya existe y no la llama nadie.**
   `set_password` está escrita, valida, y limpia el bloqueo por intentos. Cero
   llamantes en la consola. Lo que falta no es el mecanismo: es la puerta.
2. **Google ya es la recuperación, hoy, sin que nadie lo decidiera.** Quien
   tenga el correo verificado en Google entra en su cuenta existente **sin dar
   la contraseña**, y el vínculo se crea solo. Es una decisión de producto
   tomada de hecho, en un módulo de enlazado, que nadie declaró como tal.
3. **El repositorio ya rechazó una vez construir esto mal, y lo dejó por
   escrito.** El flujo de invitación se negó a reescribir credenciales con un
   comentario que dice exactamente por qué. Ese comentario es la mitad del
   modelo de amenaza, ya redactada.

Y un cuarto, de coste: **no hay forma de invalidar todas las sesiones de una
cuenta.** Ninguna. Eso no es un detalle del diseño de esta capacidad; es una
pieza que hay que construir y que hoy tampoco tiene quien la pida.

---

## 1 · Lo que existe

### `set_password`, entera — `services/console_identity.py:294-300`

```python
async def set_password(session: AsyncSession, account: ConsoleAccount, password: str) -> None:
    validate_password(password)
    account.password_hash = await asyncio.to_thread(hash_password, password)
    account.updated_at = _now()
    account.failed_attempts = 0
    account.locked_until = None
    await session.flush()
```

- **Valida solo longitud**: 12 a 256 (`console_identity.py:73,75`), vía
  `validate_password` (`:172`). Sin reglas de complejidad y **sin comprobar
  reuso**.
- **Desbloquea**: pone a cero `failed_attempts` y `locked_until`. Esto contesta
  una de las preguntas del intake sin necesidad de decidir nada — restablecer
  **ya** desbloquea, y es lo correcto: quien prueba el enlace de su correo
  demuestra más que quien acierta la contraseña.
- **No toca sesiones.** Ninguna referencia a `ConsoleSession` en el cuerpo.
- **Sin llamantes en la consola.** El único `set_password` invocado en el repo
  es el del panel de operador (`scripts/seed_operator.py:115`).

### Bloqueo y límites que ya existen

| Qué | Dónde | Valor |
|---|---|---|
| Intentos antes de bloquear | `console_identity.py:81` | `MAX_FAILED_ATTEMPTS = 10` |
| Duración del bloqueo | `console_identity.py:82` | 15 minutos |
| Vida de la sesión | `console_identity.py:77` | 7 días, **absoluta**, no se renueva |
| Entradas por minuto | `api/console/auth.py:64` | 10, por correo **y** por IP |
| Altas por minuto | `api/console/signup.py:56` | 3 — «un correo cuesta dinero y reputación de dominio» |

### Las tres rutas de `auth.py`, y no hay una cuarta

`api/console/auth.py`, prefijo `/auth` bajo `/console`:

| Línea | Ruta |
|---|---|
| 149 | `POST /console/auth/login` |
| 204 | `POST /console/auth/session` |
| 225 | `POST /console/auth/logout` |

El barrido de `forgot|reset|recover|olvid|magic` sobre `apps/api/src` y
`apps/console/src` no devuelve **nada funcional**. Solo comentarios que explican
por qué algo *no* es un reset.

### Lo que ve la persona

`apps/console/src/i18n/messages.ts:166`:

```ts
"login.forgot": { es: "¿Has olvidado la contraseña? Escríbenos.", en: "Forgot your password? Contact us." },
```

Se pinta en `login-form.tsx:93` como `<p>`. **Sin `href`, sin `mailto`, sin
destino.** El intake ya lo decía y es peor de lo que parece: no es una promesa
incumplida, es una promesa **sin dirección a la que ir**. Una pantalla que
ofrece una salida inexistente miente (§V).

---

## 2 · El hallazgo que decide la spec: Google ya recupera

`services/identity_link.py:72-90`, `resolve_provider_identity`, rama 2:

```python
account = await console_identity.get_by_email(session, normalised)
if account is None:
    return LinkOutcome(account=None, kind="unknown")

# Existe la cuenta y no el vínculo: se cuelga de ella. **No se crea una
# segunda cuenta ni una segunda membresía** — entrar con contraseña o con
# Google tiene que aterrizar en el mismo sitio.
session.add(PrincipalIdentity(...))
```

**Lee lo que hace, no lo que el comentario cuenta.** El comentario justifica no
duplicar cuentas, que es correcto y buena idea. Pero el efecto es otro y más
grande: **quien presenta un id_token de Google con un correo verificado que
coincide entra en una cuenta con contraseña, sin dar esa contraseña, y sale con
una sesión de 7 días.**

Eso es *account linking by verified email*, es lo que hace medio internet, y
aquí tiene la guardia puesta donde debe: `auth_google.py:167-173` rechaza con
403 si el correo no está verificado, comprobado en
`services/google_oidc.py:196`. No es un agujero.

**Pero es una decisión de producto tomada dentro de un módulo de enlazado.**
Tres consecuencias que la evaluación tiene que mirar de frente:

1. **Para un partner con Gmail, la recuperación ya existe** y el producto no se
   la ofrece: la pantalla de login le dice «escríbenos» mientras el botón de
   Google, dos centímetros más arriba, le habría dejado entrar. Esto no es una
   capacidad que falte. Es una capacidad que hay y **no se nombra**.
2. **La superficie de confianza de la cuenta es hoy el correo, no la
   contraseña.** Quien controla el buzón ya entra. Un enlace de un solo uso por
   correo **no añade una superficie nueva**: usa la que ya decide. Eso rebaja
   mucho el coste de riesgo de construirlo — y es el argumento central que el
   intake no tenía.
3. **Si el correo no es de Google, no hay nada.** Y ahí está el partner real:
   correos propios de dominio sin Workspace. La cobertura de Google es parcial y
   no se puede medir desde el código.

---

## 3 · El precedente que ya escribió medio modelo de amenaza

`api/console/invitations.py:119-127`:

```python
if existing is not None and authenticated is None:
    # An account already exists for the invited address: the only way in
    # is its own password. Accepting an invitation never rewrites
    # credentials (that would make any invitation link a password reset
    # for the address it names).
    raise HTTPException(status_code=409, detail="account_exists: sign in with your existing password to accept")
```

Alguien, construyendo otra cosa, vio que un enlace por correo que escribe
credenciales **es** un restablecimiento de contraseña, y se negó a construirlo
de refilón. Eso es exactamente lo que esta evaluación tiene que decidir a
propósito, y el comentario fija dos condiciones que la spec hereda:

- Un enlace que cambia credenciales es una capacidad con nombre, no un efecto
  lateral de otra.
- Si se construye, se construye **una sola vez**, con su propia puerta, y las
  demás siguen sin poder reescribir nada.

El mismo fichero trae dos detalles de implementación ya resueltos que conviene
no re-inventar: el límite se comparte con el de entrar
(`invitations.py:110`), y hay **doble transacción** para que el contador de
fallos sobreviva al 409 (`invitations.py:95-100`).

---

## 4 · Lo que hay que construir, y lo que ya está

| Pieza | Estado | Dónde |
|---|---|---|
| Escribir la contraseña nueva | **Está** | `console_identity.py:294` |
| Desbloquear al restablecer | **Está**, dentro de la anterior | `:298-299` |
| Límite por correo y por IP | **Está**, reutilizable | `core/rate_limit.py:132` · `auth.py:125` |
| Token de un solo uso con caducidad | **No para esto**, pero hay **dos patrones idénticos en producción** | `partner_invitations` (`partner_membership.py:151`, TTL 21 días) · `signup_requests` (`signup.py:83`, con `consumed_at`) |
| Enviar el correo | **Está**: Resend, best-effort | `services/email.py:23` |
| Componer una URL absoluta al enlace | **Está** | `services/signup.py:180` (`{base}/signup/{token}`) |
| Pantalla de pedir / de fijar | **No** | `(auth)/` tiene login, signup, invite, no-access, desktop-auth |
| **Invalidar todas las sesiones de una cuenta** | **NO EXISTE** | ver abajo |

### Los dos patrones de token que ya funcionan

Los dos guardan **solo el SHA-256** (`db/models/signup.py:15`: «Del token se
guarda **solo** el SHA-256»), los dos tienen `expires_at` y estado, y
`signup_requests` además tiene `consumed_at` — que es justo el campo que
distingue «un solo uso» de «vale hasta que caduque». Copiar esa forma es la
decisión barata y ya probada en producción.

### La que no existe: revocar en bloque

Las **únicas dos** sentencias `DELETE` sobre `ConsoleSession` de todo el
repositorio:

- `console_identity.py:353` — solo las caducadas (`_purge_expired`).
- `console_identity.py:414-416` — **una** sesión, por su `token_hash`
  (`end_session`).

No hay ningún `.where(ConsoleSession.principal_id == ...)`. El único borrado
masivo posible hoy es el `ondelete="CASCADE"` de
`db/models/console_identity.py:91`, o sea: borrando la cuenta.

**Esto importa más de lo que parece para el alcance.** El caso que motiva
restablecer una contraseña no siempre es «se me olvidó»; a veces es «creo que
alguien entró». En el segundo, restablecer sin cerrar sesiones **no arregla
nada**: el intruso sigue dentro siete días con su cookie. Una capacidad de
recuperación que no cierra sesiones resuelve el olvido y **da una falsa
sensación de haber resuelto el otro**, que es peor que no tenerla.

---

## 5 · El correo, que es la pieza frágil

- Cliente único: Resend por HTTP, `services/email.py:19-23`.
- **Nunca lanza**: `email.py:31` — «Returns True on a 2xx, False otherwise
  (never raises)».
- **Apagado en desarrollo**: `config.py:492` `email_enabled` es falso mientras
  la clave empiece por `dev-`, y el defecto es `dev-resend-key-change-me`
  (`config.py:479`). En local un correo se registra como `email.not_configured`
  y se pierde.
- **Mailhog está en `docker-compose.yml:34-39` y no está conectado a nada**: no
  hay cliente SMTP en el código ni variables SMTP en el servicio `api`. Está
  huérfano desde que se eligió Resend.
- Ya se envían siete correos distintos en producción; el más parecido a éste es
  la invitación (`api/console/team.py:182`).

Consecuencia para la spec: **el camino feliz de esta capacidad depende de un
envío que puede devolver `False` en silencio.** Lo que la pantalla diga cuando
eso pase es parte del diseño, no un caso límite (§V). Y probarlo de punta a
punta en local exige decidir algo sobre Mailhog o aceptar que no se prueba.

---

## 6 · Los referentes

De [[research/2026-09-19-auditoria-clase-mundial/06-referentes-externos]] §D y
de la guía de OWASP sobre *forgot password*:

- **La respuesta no puede distinguir si la cuenta existe.** Mismo texto y
  —importante— **mismo tiempo de respuesta** para un correo dado de alta y uno
  que no. El repositorio ya practica esta disciplina en el login:
  `auth.py:67` usa un `_INVALID_CREDENTIALS` único para «no existe», «mal» y
  «bloqueada», y `console_identity.py:155` tiene un `_decoy_hash` para que el
  tiempo no delate.
- **Un solo uso, caducidad corta**, invalidación al usarse y al pedir otro.
- **Al restablecer, se cierran las demás sesiones** y se avisa por correo de
  que la contraseña cambió — el aviso es lo que convierte un secuestro
  silencioso en uno que la víctima ve.
- **El límite va sobre la petición, no solo sobre el canje**, porque el envío de
  correo es el recurso caro y es el vector de molestia hacia terceros.

---

## 7 · Lo que esta fase deja decidido de hecho, y lo que no

**Decidido por el código, sin necesidad de puerta:**

- Restablecer desbloquea: ya lo hace `set_password`.
- El token se guarda hasheado con caducidad y estado: hay dos patrones vivos.
- El límite se reutiliza: existe y es el mismo que el de entrar.
- La respuesta uniforme tiene precedente y herramienta en el propio módulo.

**Lo que sigue abierto y es de la puerta de decisión:**

1. **Si hace falta contraseña, o si el camino es Google + enlace mágico y se
   retiran las contraseñas.** El hallazgo §2 hace esta pregunta más viva, no
   menos: si el correo ya es la autoridad de la cuenta, mantener una contraseña
   de 12 caracteres que nadie puede recuperar es lo peor de las dos opciones.
2. **Si restablecer cierra las demás sesiones** — y por tanto si esta
   evaluación arrastra construir la revocación en bloque, que hoy no existe.
   Recomendación de esta fase: sí, y decirlo en el alcance en vez de
   descubrirlo a mitad.
3. **Qué pasa si el correo no sale.** Hoy `send_email` devuelve `False` y sigue.
4. **Si el restablecimiento invalida la credencial de las máquinas
   emparejadas.** Pendiente, y cruza con la evaluación `maquina-sin-emparejar`:
   si esa retira el código y ata la máquina a la sesión, las dos respuestas
   tienen que ser la misma. **Las dos evaluaciones deciden juntas o se
   contradicen.**

---

## 8 · Lo que no se comprobó

- **Cuántos partners entran hoy por Google y cuántos por contraseña.** Decide
  el tamaño real del problema y no se puede leer en el código; es una consulta
  a producción (`console_auth.principal_identities` contra `principals`).
- **Si el `login.forgot` se ha llegado a usar**, o sea, si alguien ha escrito
  pidiendo ayuda. Es una señal de demanda que vive en el correo de Auphere.
- La entrega real de Resend en producción (tasa de rebote, dominio verificado).
