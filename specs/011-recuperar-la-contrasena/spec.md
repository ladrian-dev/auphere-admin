# Especificación: Recuperar la contraseña, y salir con la puerta cerrada

**Rama**: `011-recuperar-la-contrasena` · **Creada**: 2026-09-23 · **Estado**: Borrador

**Entrada**: evaluación `.specify/assessments/recuperar-la-contrasena/`, cerrada
con `go` el 2026-09-22 (Opción A). Sus cuatro decisiones (D-1 a D-4) son
canónicas y no se re-discuten aquí.

---

## Encabezado Auphere

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`0` y `3a`** — `0` porque el correo **ya** es autoridad de esta cuenta (quien lo tiene verificado en Google entra hoy sin contraseña), y `3a` porque D-4 hace que restablecer **archive las máquinas**, y eso alcanza al puente |
| **Garantías de aislamiento tocadas** | Ninguna de las ocho se debilita. Pero la operación corre con **rol dueño**, así que la RLS **no la protege**: lo único que la acota es el `WHERE` por `principal_id`. Ya tiene su test (`test_38`), y esta spec añade el suyo para el camino nuevo |
| **Nota de KB que la justifica** | `[[research/2026-09-19-auditoria-clase-mundial/_index]]` §5 (fila 011) y §3; el incidente del 2026-09-18 está en el `problem.md` de la evaluación |
| **Qué se mide** | **Nada.** No se añade ninguna llamada al modelo ni ninguna herramienta de pago. Un correo por petición, con techo de intentos |

> **§II — por qué no abre superficie.** El correo ya decide quién entra: desde
> `identity_link.py:72-90`, quien tiene el correo verificado en Google accede a
> la cuenta existente **sin dar la contraseña**, y nadie lo declaró nunca. Esta
> spec **usa** esa autoridad, no la crea — y la usa para el partner que hoy
> queda fuera, el de correo de dominio propio, que es el cliente real de
> Auphere.

---

## Lo que esto arregla, y por qué no es teórico

El **2026-09-18** alguien perdió su contraseña. Se resolvió **escribiendo el
hash a mano en producción**, y la contraseña nueva viajó por un chat.

Eso no es una anécdota: es el procedimiento que existe hoy. Y mientras tanto la
pantalla de entrada prometía una salida sin destino — «Escríbenos», sin `mailto`
ni enlace — a dos centímetros de un botón de Google que habría dejado entrar a
media base de partners. *(Ese texto ya se corrigió el 2026-09-22; lo que falta es
la capacidad.)*

---

## Escenarios de usuario y pruebas

### Historia 1 — Puedo volver a entrar sin que nadie toque la base de datos (Prioridad: P1)

Una persona de un partner olvida su contraseña. Su correo es de su propio
dominio, así que el botón de Google no la reconoce.

Escribe su dirección, recibe un enlace, elige una contraseña nueva y entra.
Nadie de Auphere abre una consola de producción.

**Por qué esta prioridad**: es la capacidad que no existe, y su ausencia ya
empujó una vez a escribir un hash a mano en producción.

**Prueba independiente**: con el correo capturado en local, recorrer el circuito
entero. Entregable sola: sin nada más de esta spec, deja de hacer falta el
procedimiento manual.

**Escenarios de aceptación**:

1. **Dado** un correo con cuenta, **cuando** se pide restablecer, **entonces**
   llega un enlace que sirve **una vez** y caduca.
2. **Dado** ese enlace, **cuando** se elige una contraseña válida, **entonces**
   se puede entrar con ella y **no** con la anterior.
3. **Dado** un enlace ya usado o caducado, **cuando** se abre, **entonces** se
   dice que ya no vale y cómo pedir otro, sin revelar de quién era.
4. **Dado** un correo **sin** cuenta, **cuando** se pide restablecer,
   **entonces** la pantalla dice **exactamente lo mismo** que si la hubiera.

---

### Historia 2 — Restablecer deja a quien entró, fuera (Prioridad: P1)

Alguien cree que otra persona ha entrado en su cuenta. Restablece la contraseña.

Después de esta historia, ese alguien **ya no está dentro**: ni su sesión abierta
ni ninguna máquina que hubiera dado de alta.

**Por qué esta prioridad**: la mitad de los motivos para recuperar una
contraseña no son «se me olvidó» sino «creo que alguien entró». Para ése,
restablecer **sin** cerrar el resto no arregla nada — y encima **da por resuelto
lo que no lo está**, que es peor que no ofrecerlo.

**Prueba independiente**: se abre una segunda sesión, se registra una máquina, se
restablece, y se comprueba que las dos quedan fuera.

**Escenarios de aceptación**:

1. **Dado** una persona con dos sesiones abiertas, **cuando** restablece,
   **entonces** la otra sesión deja de valer.
2. **Dado** una persona con máquinas dadas de alta, **cuando** restablece,
   **entonces** todas quedan archivadas con su motivo.
3. **Dado** que algo falla a mitad, **cuando** se mira el resultado,
   **entonces** o se hicieron **las tres cosas** —contraseña, sesiones,
   máquinas— o ninguna.
4. **Dado** que el acceso se retira, **entonces** queda asiento de que ocurrió,
   con la persona y el motivo.

---

### Historia 3 — Me entero de que mi contraseña cambió (Prioridad: P2)

A alguien le cambian la contraseña sin que lo haya pedido.

Después de esta historia recibe un aviso por correo. Es lo que convierte un
secuestro silencioso en uno que la víctima **ve**.

**Por qué esta prioridad**: va después porque el circuito tiene que existir
primero, pero sin ella el circuito es una puerta que se abre sin hacer ruido.

**Prueba independiente**: se restablece y se comprueba que sale el aviso, con la
hora y qué hacer si no fue uno.

**Escenarios de aceptación**:

1. **Dado** un restablecimiento con éxito, **entonces** se envía un aviso a la
   dirección de la cuenta.
2. **Dado** ese aviso, **entonces** dice **cuándo** ocurrió y a quién escribir si
   no fue la persona, y **no** lleva ninguna contraseña ni ningún enlace que
   sirva para entrar.

---

### Casos límite

- **¿Y si el correo no sale?** `send_email` **no lanza: devuelve `False`**. La
  pantalla dice lo mismo de siempre; el fallo es un problema de Auphere, visible
  en sus registros y **no** en la pantalla de quien pregunta. Decir «no pudimos
  enviarlo» revelaría que la cuenta existe.
- **¿Y si alguien pide cien enlaces?** Hay techo de intentos, y el techo no puede
  convertirse en un oráculo: pasarse dice lo mismo para una dirección con cuenta
  y para una sin ella.
- **¿Y si el enlace se reenvía a otra persona?** Sirve una vez y caduca; quien lo
  use primero gana, y el aviso de la Historia 3 delata el uso.
- **¿Y si la cuenta no tiene contraseña todavía, solo Google?** Entra en la misma
  puerta: restablecer **pone** una, no la cambia.
- **¿Y si la persona está bloqueada por intentos fallidos?** Restablecer con
  éxito la desbloquea — si no, se arregla la contraseña y se sigue sin poder
  entrar.
- **La ausencia se diseña (§V)**: mientras el enlace no llega, la pantalla no
  finge que ya está. Dice qué mirar y en cuánto tiempo.

---

## Requisitos

### Requisito 1 — Pedir el enlace

**Historia de usuario:** Como persona que olvidó su contraseña, quiero pedir un
enlace a mi correo, para volver a entrar sin que nadie toque la base de datos.

#### Criterios de aceptación

1. El sistema DEBE permitir pedir un restablecimiento dando **solo** la
   dirección de correo.
2. WHEN la dirección tiene cuenta THEN el sistema DEBE enviar un enlace que sirve
   **una sola vez** y que **caduca**.
3. La respuesta de la pantalla DEBE ser **idéntica** tenga o no cuenta la
   dirección, y DEBE serlo también **cuando el envío falla**.
4. El sistema NO DEBE guardar el enlace en claro en ningún sitio.
5. El sistema DEBE acotar cuántas veces se puede pedir, y el rechazo por tope
   DEBE ser **indistinguible** de la respuesta normal.
6. WHEN se pide un enlace nuevo THEN los anteriores de esa persona DEBEN dejar de
   valer.

### Requisito 2 — Canjear el enlace

**Historia de usuario:** Como quien recibió el enlace, quiero elegir una
contraseña nueva y entrar.

#### Criterios de aceptación

1. WHEN el enlace es válido THEN el sistema DEBE permitir fijar una contraseña
   nueva, con las mismas reglas de validez que el alta.
2. WHEN la contraseña se fija THEN la anterior NO DEBE volver a servir.
3. IF el enlace ya se usó, caducó o no existe THEN el sistema DEBE decir que ya
   no vale y cómo pedir otro, y NO DEBE revelar de quién era ni si existió.
4. WHEN la persona estaba bloqueada por intentos fallidos THEN restablecer con
   éxito DEBE desbloquearla.
5. El sistema DEBE dejar la sesión iniciada tras restablecer, o llevar a la
   entrada diciendo que ya puede entrar — **una de las dos, y la pantalla no
   miente sobre cuál**.

### Requisito 3 — Restablecer retira todo el acceso

**Historia de usuario:** Como persona que sospecha que alguien entró, quiero que
restablecer deje fuera a quien estuviera dentro.

> **Decisión D-4 de la puerta.** La pieza ya existe: la construyó la spec 012
> (`services/principal_access.revoke_all_access`), y su docstring dice
> literalmente que la 011 la usará dentro de su misma transacción.

#### Criterios de aceptación

1. WHEN una contraseña se restablece THEN el sistema DEBE cerrar **todas** las
   demás sesiones de esa persona.
2. WHEN una contraseña se restablece THEN el sistema DEBE archivar **todas** sus
   máquinas activas, con su motivo.
3. La contraseña, las sesiones y las máquinas DEBEN cambiar **en una sola
   transacción**: o las tres, o ninguna.
4. El sistema DEBE dejar asiento de la retirada de acceso, con la persona y el
   motivo.
5. El sistema NO DEBE alcanzar a ninguna otra persona. *(Corre con rol dueño: la
   RLS no lo impide, solo el `WHERE`.)*
6. La pantalla DEBE decir **antes** de restablecer que esto cierra las sesiones y
   obliga a volver a entrar en cada máquina.

### Requisito 4 — El aviso de que cambió

**Historia de usuario:** Como titular de la cuenta, quiero enterarme si mi
contraseña cambia, para poder reaccionar si no fui yo.

#### Criterios de aceptación

1. WHEN una contraseña se restablece con éxito THEN el sistema DEBE avisar por
   correo a la dirección de la cuenta.
2. El aviso DEBE decir cuándo ocurrió y a quién escribir si no fue la persona.
3. El aviso NO DEBE llevar ninguna contraseña, ni ningún enlace que sirva para
   entrar.
4. IF el aviso no se puede enviar THEN el restablecimiento **ya ocurrido** NO
   DEBE deshacerse, y el fallo DEBE quedar en los registros de Auphere.

### Requisito 5 — Lo que se conserva del otro código de un solo uso

**Historia de usuario:** Como responsable de la seguridad, quiero que este enlace
tenga las mismas propiedades que los demás secretos de un solo uso del producto.

> Es la lista que la spec 009 dejó escrita al retirar **su** código, y que la 012
> volvió a aplicar. Se hereda entera.

#### Criterios de aceptación

1. **Uso único**: el enlace se canjea una vez y no se puede releer.
2. **Hash en reposo**: lo que se guarda no permite reconstruir el enlace.
3. **Rechazo sin oráculo**: no valer, haber caducado y no existir son
   indistinguibles.
4. **Techo de intentos**, con la dirección como clave.
5. El sistema DEBE reutilizar el limitador que ya existe, y NO DEBE escribir uno
   nuevo.

### Entidades clave

- **Petición de restablecimiento** *(tabla nueva)*: a qué cuenta apunta, el
  **hash** del secreto, cuándo caduca y cuándo se usó. Pertenece a la partición
  de identidad (`console_auth`), que es de persona y **no de tenant**: la RLS de
  tenant no aplica y quien la acota es el `WHERE` por cuenta.

---

## Criterios de éxito

- **CE-001**: una persona con correo de dominio propio recupera el acceso **sin
  que nadie de Auphere abra una consola de producción**.
- **CE-002**: quien pide un enlace para una dirección sin cuenta **no puede
  distinguirlo** de una con cuenta — ni por el texto, ni por el tope.
- **CE-003**: tras restablecer, una sesión abierta en otro sitio deja de valer y
  las máquinas quedan archivadas.
- **CE-004**: si algo falla a mitad, **no queda** una contraseña cambiada con las
  sesiones vivas.
- **CE-005**: el titular recibe un aviso de que su contraseña cambió.
- **CE-006**: el circuito entero se puede recorrer **en local**, o está escrito
  por qué no.

---

## Fuera de alcance

- **Retirar las contraseñas** (Opción B de la evaluación) — es mejor idea y peor
  decisión hoy: toca la ruta por la que entra todo el mundo, `password_hash` es
  `NOT NULL`, y pone el correo en el camino crítico de cada entrada cuando
  `send_email` no lanza.
- **Segundo factor** — otra conversación, y no la resuelve esta puerta.
- **Cambiar la contraseña estando dentro** — es otra pantalla y otro flujo; aquí
  se recupera, no se administra.
- **Recuperar la cuenta de un operador de Auphere** (`operator_identity`) — otra
  identidad, otras reglas.
- **El texto de `login.forgot`** — se arregló el 2026-09-22 como cambio trivial,
  y ya está en `develop`.

---

## Supuestos

- **El envío de correo funciona en producción y no se ha medido.** Es el riesgo
  que la evaluación marcó y no cerró: el camino feliz depende de un envío que no
  lanza excepciones. Esta spec lo hace **visible en los registros**, no lo
  arregla.
- **Mailhog está en `docker-compose.yml` sin conectar a nada** desde que se
  eligió Resend. O se cablea para poder recorrer el circuito en local, o se
  escribe por qué no se prueba de punta a punta. **Se decide al planificar, no a
  mitad.**
- **La pieza de retirada de acceso ya existe** y se usa, no se reescribe. Su
  docstring dice que no hace commit **a propósito**, para que el llamante
  componga la transacción — que es exactamente lo que el Requisito 3.3 pide.
- El techo de intentos y su ventana se fijan al planificar, con números
  defendibles; lo que esta spec exige es que existan y no sean un oráculo.
