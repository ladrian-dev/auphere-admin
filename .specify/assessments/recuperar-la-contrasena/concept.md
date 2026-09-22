# Concept: recuperar la contraseña

- **Slug**: recuperar-la-contrasena
- **Fecha**: 2026-09-22
- **Entrada**: [`problem.md`](./problem.md) · [`research.md`](./research.md)

---

## El eje que separa las opciones

No es «qué flujo de reset construimos». Es una pregunta anterior, que el
research puso encima de la mesa y que el intake ya intuía:

> **¿Qué es la autoridad de una cuenta de la consola: la contraseña o el correo?**

Hoy conviven las dos respuestas sin que nadie eligiera. Una contraseña de 12
caracteres que **nadie puede recuperar**, y un acceso por Google que **recupera
solo** (`identity_link.py:72-90`). Eso no es tener dos vías: es tener una vía
buena para unos y ninguna para otros, y no haberlo decidido.

Las tres opciones se separan por dónde ponen esa autoridad. La cuarta es no
hacer nada.

---

## Options

### Opción A — El enlace de un solo uso, y las contraseñas se quedan

Lo que el intake proponía. Una ruta que acepta un correo, emite un token con
caducidad corta, lo manda, y una pantalla que canjea y fija la contraseña nueva.

**Cómo se construye, con lo que ya hay:**

| Pieza | De dónde sale |
|---|---|
| Tabla del token | Copiar la forma de `signup_requests`: `token_hash` SHA-256, `expires_at`, `consumed_at`, `status` (`db/models/signup.py:83-97`) |
| Escribir la contraseña | `set_password` tal cual — ya valida y ya desbloquea |
| Límite | `check_login_rate_limit` (`auth.py:125`), **sobre la petición**, no solo el canje |
| Respuesta uniforme | El patrón de `_INVALID_CREDENTIALS` + `_decoy_hash` ya está en el módulo |
| Enviar | `send_email` + la composición de URL de `services/signup.py:180` |
| Pantalla | `(auth)/` ya tiene cuatro hermanas con la misma forma |

**A favor**: resuelve el caso real (correo propio de dominio, sin Google); no
abre superficie nueva —el correo **ya** es autoridad de facto, §2 del research—;
todas las piezas tienen precedente en producción.

**En contra**: sigue habiendo contraseñas que caducan en la cabeza de la gente,
y con ellas un flujo más que mantener. No resuelve por sí solo el caso
«sospecho que me han entrado» salvo que arrastre la revocación en bloque.

**Coste**: una tabla, una migración, dos rutas, dos pantallas, un correo.

---

### Opción B — Enlace mágico y se retiran las contraseñas

Entrar es: escribes tu correo, te llega un enlace, entras. Google sigue siendo
el camino rápido. **No hay contraseña que olvidar.**

**A favor**: es la respuesta honesta al eje. Si el correo ya decide, sostener
una contraseña que nadie puede recuperar es lo peor de las dos opciones.
Elimina la categoría entera de problema en vez de darle salida. Y el flujo de
entrar y el de recuperar pasan a ser **el mismo**, que es la mitad de código y
la mitad de superficie.

**En contra**, y es serio:

- `console_auth.principals.password_hash` es **NOT NULL**
  (`db/models/console_identity.py:56`). No hay cuenta sin contraseña. Retirarlas
  es migración de esquema y de datos, no una bandera.
- Todo lo que hoy escribe contraseña cambia: alta
  (`api/console/signup.py:191`), invitación (`invitations.py:139`), y el
  precedente que se negó a reescribir credenciales (`invitations.py:119-127`)
  pasa a significar otra cosa.
- **Cada entrada depende del correo**, y el correo es la pieza frágil:
  `send_email` no lanza, devuelve `False` (`services/email.py:31`), y en local
  está apagado. Hoy un fallo de correo molesta; con la Opción B, deja a
  todo el mundo fuera.
- Dos tests congelan la forma actual del login y habría que reescribirlos.

**Coste**: alto, y tocando la ruta por la que entra todo el mundo.

---

### Opción C — Solo Google, y se dice en voz alta

Retirar las contraseñas y no poner enlace mágico: se entra con proveedor
externo, punto. Es lo que el intake apuntaba con «un producto que solo entra por
proveedor externo no necesita recuperación — necesita no tener contraseñas».

**A favor**: la menos superficie de todas. Cero secretos que Auphere custodia,
cero correos en el camino crítico, cero flujos de recuperación. El vínculo por
correo verificado ya está construido y con su guardia puesta
(`auth_google.py:167-173`).

**En contra**, y es lo que la descarta hoy: **deja fuera al partner sin
Google.** Correo propio de dominio sin Workspace es el caso real del cliente de
Auphere, no una excepción. Y ata el acceso al producto de un tercero sin
alternativa: si Google rechaza una cuenta, Auphere no tiene qué ofrecer.

**Coste**: medio en código, alto en clientes que no pueden entrar.

---

### Opción D — No hacer nada

Seguir escribiendo `password_hash` a mano en producción cuando alguien llama.

**A favor**: cero código.

**En contra**: no es un estado estable, es un procedimiento manual con acceso a
producción que ya ocurrió una vez y mandó una contraseña por un chat. Y la
pantalla sigue prometiendo una salida sin dirección.

---

## Decisiones transversales — no son opciones, hay que tomarlas igual

### T-1 · Restablecer cierra las demás sesiones

**Hoy es imposible**: los dos únicos `DELETE` sobre `ConsoleSession` son «las
caducadas» (`console_identity.py:353`) y «esta una» (`:414`). No hay
`.where(principal_id == …)` en todo el repositorio.

Con cualquiera de las opciones A, B o C, **hay que construirlo**, porque el
caso «creo que me han entrado» es la mitad de los motivos para recuperar. Y
porque sin ello se da una falsa sensación de haber resuelto: el intruso sigue
dentro sus siete días.

Es barato —una sentencia y un llamante— y es lo que hace que la capacidad sirva
para lo que la gente cree que sirve.

### T-2 · Avisar por correo de que la contraseña cambió

Es lo que convierte un secuestro silencioso en uno que la víctima ve. La
infraestructura está (`send_email`) y hay siete correos ya en producción. Va con
T-1: cerrar sesiones sin avisar es la mitad del gesto.

### T-3 · Qué hace la pantalla cuando el correo no sale

`send_email` devuelve `False` y sigue. La respuesta uniforme complica esto:
**no se puede decir «no pudimos enviarlo» sin revelar que la cuenta existe.** La
salida honesta es decir siempre lo mismo —«si esa dirección tiene cuenta, le
llega un enlace»— y que el fallo de envío sea un problema de Auphere, visible en
sus registros, no en la pantalla de la persona.

### T-4 · Y el correo en local

Mailhog está en `docker-compose.yml:34-39` sin estar conectado a nada, desde que
se eligió Resend. O se cablea, o se acepta que este flujo no se prueba de punta
a punta en local. **Decidirlo, no descubrirlo.**

---

## Recommendation

**Opción A**, con T-1, T-2 y T-3 dentro del alcance y T-4 decidido
explícitamente.

Y **una cosa más que no es la Opción A y cuesta una línea**: arreglar el texto
de `login.forgot` para que la vía que ya existe se nombre. Hoy dice
«escríbenos»; quien tiene Gmail podía haber entrado por el botón de arriba.

### Por qué A y no B

La Opción B es mejor idea y peor decisión **hoy**. Mejor idea porque contesta el
eje en vez de rodearlo. Peor decisión por tres razones concretas:

1. **Toca la ruta por la que entra todo el mundo**, para resolver un problema
   que hoy afecta a quien olvida su contraseña. Cambiar el camino de todos para
   arreglar el de algunos es la forma de convertir un hueco en un incidente.
2. **El correo no está listo para ser el camino crítico.** `send_email` no
   lanza, está apagado en local, y Mailhog lleva meses huérfano. Cuando un fallo
   de envío pase de «molestia» a «nadie entra», eso importa.
3. **`password_hash` es NOT NULL.** Retirar contraseñas es migración de datos
   sobre la tabla de identidad. No es la clase de cambio que se hace de camino a
   otra cosa.

La Opción A **no cierra la puerta a B**: construye la mitad de su maquinaria —
token de un solo uso por correo, pantalla de canje, límites— sobre la que B se
apoyaría después, cuando el correo tenga la fiabilidad que B necesita.

### Por qué no C

Deja fuera al partner con correo propio de dominio, que es el cliente real.

---

## Out of Scope (para la opción recomendada)

- Cambiar la contraseña estando dentro.
- Verificación de correo en el alta.
- Segundo factor.
- Política de complejidad de contraseñas.
- Retirar las contraseñas (eso es B, y es otra decisión, más adelante).

---

## Assumptions to Validate

1. **Que el caso del correo propio de dominio es mayoritario.** Si resultara que
   casi todos los partners entran por Google, B sube mucho y A baja. Se resuelve
   con una consulta a producción, no con código.
2. **Que la entrega de Resend en producción es fiable** (dominio verificado,
   sin rebotes). Si no lo es, A entrega una capacidad que falla en silencio.
3. **Que nadie depende de que las sesiones sobrevivan a un cambio de
   contraseña.** T-1 las cierra; si algún flujo automático se apoya en una
   sesión larga, hay que saberlo antes.
