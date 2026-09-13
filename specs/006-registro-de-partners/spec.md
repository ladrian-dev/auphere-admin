# Especificación: el registro de partners

**Rama**: `006-registro-de-partners` · **Creada**: 2026-09-13 · **Estado**: Clarificada — cero marcas abiertas, lista para `/speckit-plan`

**Entrada**: [`docs/pendientes-tras-el-go-live.md` §1](../../docs/pendientes-tras-el-go-live.md)
— «nadie puede contratar sin que un operador le abra la puerta», el hueco más
grande que dejó el go-live del 2026-09-13. Ampliado en la misma sesión con el
inicio de sesión con Google, pedido explícitamente y elegido «de forma que sirva
para próximas integraciones».

Depende de la spec **005** (`005-membresias-y-cobro`), desplegada y cobrando: el
catálogo `membership_tiers` existe en producción con sus `stripe_price_id`, el
checkout funciona y la escalera de estados de suscripción está construida. Esta
spec **no rehace nada de eso**: construye el tramo que lo precede.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`0`** — API de la consola. **No abre una clase nueva, pero sí un modo nuevo dentro de ella**: es la primera escritura **anónima** que crea una fila de plataforma (un `partner`). Ver el recuadro de abajo |
| **Garantías de aislamiento tocadas** | **1. Postgres RLS** — el registro crea un `partner` y su primera membresía, ambas tablas de plataforma sin `tenant_id`; ningún objeto nuevo lleva `tenant_id` y ninguna ruta nueva alcanza datos de un tenant · **4. Acción consecuente con rastro** — crear un partner, aceptar el alta y contratar son acciones de una **persona**, y la auditoría tiene que nombrarla (`decided_by`) también cuando esa persona todavía no era principal · **6. Log + trace tagging** — el rastro del registro no puede llevar contraseña, token de Google ni el token de verificación en claro |
| **Nota de KB que la justifica** | `[[nexus/decisions/ADR-038-registro-autonomo-de-partners]]` — escrito el 2026-09-13 en `/Users/lmatos/Work/Auphere/nexus/decisions/` con las cinco decisiones de §Clarificaciones, que son exactamente lo que el ADR tenía que registrar |
| **Qué se mide** | **Nada nuevo en el medidor de consumo.** Un registro no gasta modelo ni reloj de máquina. Lo que sí se cuenta, y es distinto, son **los envíos de correo de verificación**, porque son el vector de abuso barato de un formulario abierto: se limita por ritmo, no por medidor |

> **Por qué una escritura anónima no es una superficie nueva, y qué la contiene
> igualmente.** El repositorio ya atiende llamantes sin sesión: el webhook de
> Meta, el de Stripe, y los tres endpoints PRE-SESIÓN de `/console/auth/*`. Lo
> que este formulario tiene de distinto no es la clase, es la **consecuencia**:
> los anteriores escriben sobre filas que ya existen; éste **crea un partner**,
> que es la raíz de todo lo demás — membresías, clientes, claves de API y saldo
> cuelgan de él.
>
> Tres cosas lo contienen, y las tres son requisitos de esta spec: **un correo
> verificado antes de que exista ningún partner** (el formulario no crea nada,
> crea una *solicitud*); **límite de ritmo por IP y por dominio de correo**, con
> las respuestas indistinguibles que ya usa el login para no permitir enumerar
> cuentas; y **el partner nace sin ninguna capacidad que cueste dinero** — sin
> clave de API viva, sin cliente final, en el nivel Free, y con todo lo que
> gasta detrás de una suscripción.

> **Google es un tercero que afirma quién eres, y eso es lo que se compra.**
> Delegar la identidad en Google no debilita nada que hoy esté fuerte —la
> contraseña la elige el usuario y la guardamos hasheada—, pero sí cambia quién
> responde de que el correo sea suyo: hoy respondemos nosotros con un token de
> verificación, y con Google responde Google. Es un cambio deseable (Google
> verifica mejor que nosotros) siempre que se cumplan dos condiciones que esta
> spec exige: **el `email_verified` del proveedor se lee y se respeta** —una
> cuenta de Google con correo sin verificar no vale como verificación— y **la
> identidad se ancla al identificador estable del proveedor, no al correo**,
> porque un correo puede cambiar de dueño y el identificador no.

---

## Clarificaciones

### Sesión 2026-09-13

- Q: ¿El registro de partners es abierto a cualquiera, o por invitación con aprobación del equipo? → A: **Abierto.** Cualquiera se registra, verifica su correo y llega a Free sin que nadie intervenga, con una bandera que lo apaga si hace falta.
- Q: ¿Verificar el correo basta para dar por bueno a un partner, o hace falta una comprobación adicional? → A: **El correo basta.** Sin revisión humana en ningún punto; la comprobación de identidad real la hace el proveedor de pago cuando cobra.
- Q: ¿Un partner en Free puede dar de alta clientes finales, o el primer cliente exige suscripción de pago activa? → A: **Sí puede, y la puerta es el medidor.** Los clientes finales gastan sólo el saldo comprado (spec 005), así que sin crédito comprado ni plan no pasa un turno. No se añade ningún tope nuevo.
- Q: ¿Qué ocurre con un registro que nunca paga? → A: **Free es indefinido; se archiva por inactividad, no por no pagar.** Disparador: 180 días sin sesión y sin ningún cliente final. Archivar es reversible.
- Q: ¿Google directo o proveedor de identidad de terceros? → A: **Google directo, OIDC con código de autorización + PKCE**, verificando el ID token contra el JWKS de Google. Sin dependencia nueva y preparado para autorización incremental.

---

## Lo que ya existe, y que aquí no se rehace

Media escalera está construida. Enumerarla es la mitad del alcance de esta spec,
porque lo que **no** hay que construir es lo que más se construye por error.

| Ya existe | Dónde | Consecuencia para esta spec |
|---|---|---|
| Cuentas de consola con contraseña scrypt, bloqueo por intentos y sesiones con token hasheado | `console_auth.principals` / `principal_sessions`, migración 0088, ADR-032 | El registro **reutiliza** la cuenta. No hay un segundo almacén de identidad |
| Invitaciones con token SHA-256, TTL de 21 días, un solo uso, y `POST /console/invitations/{token}/accept` que crea principal + membresía | Migración 0080, `repositories/partner_membership.py` | El alta del primer owner **es una invitación**, no un camino paralelo. El flujo ya admite que no haya owner previo |
| `require_console_principal` revalida la pertenencia en `partner_memberships` en **cada** llamada, sin fiarse del BFF | `core/console_auth.py` | Un registro correcto **no** implica acceso: la puerta sigue siendo la membresía |
| Las respuestas del login son indistinguibles a propósito (401 único, 429 con `Retry-After`, dos cubos de ritmo por correo y por IP) | `api/console/auth.py` | El registro **hereda** ese criterio. Un formulario de alta que diga «ese correo ya existe» deshace el trabajo del login |
| El catálogo de niveles, el checkout, el cambio de plan con prorrateo y la escalera `current → payment_failed → unpaid → canceled` | Spec 005, migración 0116 | Contratar ya funciona. Lo que falta es **llegar** a la pantalla de planes |
| **Un partner sin fila en `partner_subscriptions` es Free**, y la ausencia es un estado válido y diseñado | `db/models/membership.py` | Un partner recién registrado **no necesita que se le siembre nada** para existir. Free es el suelo: 1 miembro, 0 teammates |
| El patrón de `state` firmado para un redirect de OAuth — ligado, corto, con nonce y a prueba de manipulación | `services/tiktok_oauth_state.py`, `services/connectors/consent_token.py` | El `state` de Google **copia ese patrón**. No se inventa uno nuevo |
| Envío de correo | `services/email.py` | El correo de verificación usa lo que hay |

---

## Escenarios de usuario y pruebas

### Historia 1 — Alguien se registra y acaba dentro de su consola, sin operador (Prioridad: P1)

Una persona que dirige una agencia llega a la consola, pide una cuenta con su
correo de trabajo, demuestra que ese correo es suyo, elige el nombre de su
empresa y entra en la consola como `owner` de un partner nuevo, en el nivel
Free. Nadie con acceso a la VPC ha tenido que hacer nada.

**Por qué esta prioridad**: es el hueco entero. Sin esto, el resto de esta spec
no tiene a quién servir, y el catálogo de niveles desplegado en producción sigue
con cero suscripciones porque nadie puede llegar a él.

**Prueba independiente**: se ejecuta el alta de punta a punta contra staging con
un correo nuevo y, sin tocar la base de datos ni ejecutar ningún script, la
persona termina viendo la consola con su partner vacío. La prueba de que no hace
falta operador es que el alta funciona **sin credencial de operador en ninguna
parte del recorrido**.

**Escenarios de aceptación**:

1. **Dado** un correo que no tiene cuenta, **cuando** la persona pide el alta,
   **entonces** el sistema registra una solicitud, envía un enlace de
   verificación a ese correo, y **no** crea todavía ni partner ni cuenta.
2. **Dado** un enlace de verificación válido y no usado, **cuando** la persona
   lo abre y completa el nombre de la empresa y su contraseña, **entonces** el
   sistema crea el partner, la cuenta y la membresía `owner` activa, y la deja
   con sesión iniciada en la consola.
3. **Dado** un correo que **sí** tiene cuenta, **cuando** alguien pide el alta
   con él, **entonces** la respuesta es **idéntica** a la del caso 1 y el correo
   que llega es el de «ya tienes cuenta, entra por aquí» — nadie descubre desde
   fuera qué correos existen.
4. **Dado** un partner recién creado, **cuando** se consulta su nivel,
   **entonces** es Free, sin fila de suscripción, con sus topes: un miembro,
   cero teammates.

---

### Historia 2 — Contratar un nivel de pago desde dentro (Prioridad: P1)

El owner recién registrado ve qué le da cada nivel y contrata el suyo. El
checkout es el de la spec 005, ya construido; lo que esta historia añade es que
la pantalla de planes sea **alcanzable** desde un alta autónoma y que el estado
del registro y el de la suscripción sean el mismo hilo.

**Por qué esta prioridad**: es la mitad que convierte el hueco en ingreso. La
Historia 1 sin ésta produce partners que no pagan.

**Prueba independiente**: un partner creado por la Historia 1 llega a la pantalla
de planes, contrata Pro, y la suscripción aparece activa en el proveedor y en el
libro. Se prueba sin haber dado de alta ni un solo cliente final.

**Escenarios de aceptación**:

1. **Dado** un partner en Free, **cuando** su owner contrata un nivel de pago y
   el pago se confirma, **entonces** el partner queda en ese nivel con estado
   `current`, y la auditoría nombra a la persona que contrató.
2. **Dado** un partner en Free que intenta usar algo por encima de su tope,
   **cuando** lo intenta, **entonces** el sistema no enseña un botón apagado ni
   una pantalla que explique lo que no tiene: enseña lo que sí puede hacer y,
   donde corresponda, el camino a contratar (constitución §V).
3. **Dado** un partner en Free, **cuando** su owner da de alta un cliente
   final, **entonces** el sistema se lo permite, y ese cliente **no puede
   consumir un turno** hasta que haya saldo comprado o un nivel de pago activo
   — la puerta es el medidor de la spec 005, no un tope nuevo.

---

### Historia 3 — Entrar con Google (Prioridad: P2)

La misma persona, en vez de elegir una contraseña, pulsa «Continuar con Google».
Vale tanto para registrarse como para volver a entrar. Si ya tenía cuenta con
contraseña y el correo coincide, las dos formas abren **la misma** cuenta.

**Por qué esta prioridad**: reduce la fricción del alta justo donde más se
abandona —elegir una contraseña más— y quita de en medio el correo de
verificación, porque Google ya verificó. Va detrás de la P1 porque la P1 tiene
que funcionar sin depender de un tercero: si Google no responde, el alta con
contraseña sigue en pie.

**Prueba independiente**: se completa un alta entera con Google, sin escribir
contraseña en ningún momento, y después se entra de nuevo con Google en una
sesión limpia. Con la cuenta de contraseña ya existente se prueba que el segundo
método aterriza en la misma cuenta y no crea una segunda.

**Escenarios de aceptación**:

1. **Dado** un correo sin cuenta, **cuando** la persona completa «Continuar con
   Google» y el proveedor afirma que el correo está verificado, **entonces** el
   sistema crea la cuenta sin pedir contraseña y sin enviar correo de
   verificación, y sigue con el mismo paso de nombre de empresa de la Historia 1.
2. **Dado** un correo que ya tiene cuenta con contraseña, **cuando** la persona
   entra con Google con ese mismo correo verificado, **entonces** el sistema
   vincula el proveedor a la cuenta existente y **no** crea una segunda cuenta
   ni una segunda membresía.
3. **IF** el proveedor devuelve un correo **no** verificado **THEN** el sistema
   DEBE rechazar el alta y **NO DEBE** crear cuenta, vincular nada ni conceder
   sesión.
4. **Dado** un `state` ausente, caducado, ya usado o que no case con el que se
   emitió, **cuando** vuelve la llamada del proveedor, **entonces** el sistema
   la rechaza sin crear nada.
5. **Dado** que la plataforma habla con Google **directamente** (sin proveedor
   de identidad intermedio), **cuando** más adelante un teammate necesite leer
   Calendar o Gmail, **entonces** los permisos se añaden a la misma cuenta
   vinculada por autorización incremental, **sin** rehacer el inicio de sesión
   ni pedir a la persona que se registre otra vez.

---

### Historia 4 — El operador ve y gobierna lo que entra solo (Prioridad: P2)

Cuando el alta deja de pasar por una persona, el equipo necesita ver qué entró,
poder parar a quien abusa y poder atender a quien se quedó a medias.

**Por qué esta prioridad**: abrir la puerta sin mirilla es lo que convierte un
formulario en un problema. No es P1 porque un volumen de cero a diez altas
diarias se sostiene con el rastro de auditoría y los límites de ritmo; se vuelve
urgente con el volumen.

**Prueba independiente**: se completan tres altas de prueba y el operador las ve
las tres en el panel, con su origen y su estado, sin consultar la base a mano.

**Escenarios de aceptación**:

1. **Dado** un alta completada, **cuando** el operador mira el panel,
   **entonces** ve el partner nuevo, cuándo se creó, por qué vía entró
   (contraseña o Google) y en qué nivel está.
2. **Dado** un registro que se quedó a medias, **cuando** el operador lo mira,
   **entonces** lo distingue de un partner activo y puede reenviar el enlace de
   verificación sin volver a la VPC.

---

### Casos límite

- **Dos altas simultáneas con el mismo correo.** Sólo una puede crear cuenta;
  la otra no puede crear una segunda ni fallar de un modo que revele que la
  primera existe.
- **Alguien abre el enlace de verificación dos veces.** El segundo uso no crea
  un segundo partner. Un token de un solo uso usado dos veces se comporta igual
  que uno inválido.
- **El enlace de verificación caduca.** La persona puede pedir otro, con el
  mismo límite de ritmo, y el correo de la solicitud caducada deja de valer.
- **El correo de verificación no llega.** El alta se queda a medias sin dejar
  basura: no hay partner huérfano, y el mismo correo puede volver a intentarlo.
- **El nombre de empresa ya existe.** Dos agencias pueden llamarse igual; lo que
  no puede repetirse es la referencia técnica con la que se las nombra.
- **La persona abandona después de verificar y antes de nombrar la empresa.**
  Hay cuenta y no hay partner: la vuelta tiene que retomar donde lo dejó, no
  empezar de cero ni dejarla fuera.
- **El registro nunca paga.** No pasa nada: Free es un nivel del catálogo, no
  una infracción. Lo que se archiva es el partner **inactivo** —180 días sin
  ninguna sesión y sin ningún cliente final—, y si su owner vuelve, se
  desarchiva. El disparador es la inactividad, nunca la ausencia de pago.
- **Google no responde, o el usuario cancela en la pantalla del proveedor.** La
  consola vuelve al punto de partida con el alta por contraseña disponible, sin
  cuenta a medio crear.
- **La capacidad no está disponible** (constitución §V): mientras el alta
  autónoma esté apagada por bandera, la consola no enseña un botón de registro
  apagado ni una página que explique lo que no hay. Enseña el login, sin más.

## Requisitos

### Requisito 1 — Solicitud de alta

**Historia de usuario:** Como persona que quiere ser partner, quiero pedir una
cuenta con mi correo, para no depender de que alguien del equipo me la abra.

#### Criterios de aceptación

1. WHEN alguien envía una solicitud de alta con un correo con forma válida THEN
   el sistema DEBE registrar la solicitud, enviar un enlace de verificación de un
   solo uso a ese correo, y NO DEBE crear todavía ni cuenta, ni partner, ni
   membresía.
2. WHEN alguien envía una solicitud con un correo que **ya** tiene cuenta THEN el
   sistema DEBE responder **exactamente igual** que en 1.1, y DEBE enviar a ese
   correo el aviso de que ya existe una cuenta, y NO DEBE revelar en la respuesta
   ni en los tiempos de respuesta que el correo existía.
3. El sistema DEBE guardar el token de verificación **sólo** como hash, DEBE
   mostrarlo una única vez en el enlace, y NO DEBE escribirlo en ningún registro
   ni traza.
4. IF una solicitud supera el límite de ritmo por IP o por correo THEN el sistema
   DEBE responder con el mismo código y cabecera de reintento que usa el login, y
   NO DEBE enviar el correo.
5. WHEN una solicitud lleva más de su plazo de validez sin usarse THEN el sistema
   DEBE dejar de aceptar su enlace, y DEBE permitir pedir uno nuevo.
6. El registro es **abierto**: el sistema NO DEBE exigir aprobación de nadie
   del equipo para que un alta se complete, y NO DEBE dejar una solicitud
   esperando a un humano.
7. WHERE el alta autónoma esté apagada por bandera EL sistema DEBE comportarse
   como si el registro no existiera (constitución §V: la ausencia se diseña), y
   DEBE seguir admitiendo el alta por invitación.

### Requisito 2 — Verificación de quién pide el alta

**Historia de usuario:** Como plataforma, quiero saber que quien pide una cuenta
controla el correo con el que la pide, para que un partner no sea un formulario
relleno por cualquiera.

#### Criterios de aceptación

1. WHEN se abre un enlace de verificación válido y no usado THEN el sistema DEBE
   dar por verificado ese correo, y DEBE invalidar el enlace para usos
   posteriores.
2. WHERE la identidad la aporta un proveedor externo EL sistema DEBE exigir que
   el proveedor afirme que el correo está verificado, y DEBE rechazar el alta si
   no lo afirma.
3. El sistema NO DEBE crear ningún partner a partir de un correo no verificado.
4. El correo verificado es **la única** comprobación exigida: el sistema NO
   DEBE requerir revisión humana, dominio corporativo ni datos fiscales para
   completar un alta.
5. El sistema DEBE poder suspender un partner después del alta, porque ésa —y
   no una puerta previa— es la respuesta a un registro que resulte ser falso.

### Requisito 3 — Nacimiento del partner y de su primer owner

**Historia de usuario:** Como persona verificada, quiero que al terminar el alta
exista mi empresa en la plataforma y yo sea su owner, para poder empezar a
trabajar.

#### Criterios de aceptación

1. WHEN una persona verificada completa el alta con el nombre de su empresa THEN
   el sistema DEBE crear, en una sola operación indivisible, el partner, la
   cuenta de consola y la membresía `owner` activa que las une.
2. IF cualquier paso de esa operación falla THEN el sistema NO DEBE dejar un
   partner sin owner, ni una cuenta sin membresía, ni una membresía que apunte a
   un partner inexistente.
3. WHEN el partner nace THEN DEBE quedar en el nivel Free, sin fila de
   suscripción, y con la consola habilitada para su owner.
4. WHEN el partner nace THEN NO DEBE tener ninguna clave de API viva, ningún
   cliente final, ni ninguna capacidad que genere gasto.
5. WHEN se completa el alta THEN la auditoría DEBE registrar el hecho nombrando a
   la **persona** que lo completó y la vía por la que entró, y NO DEBE contener
   la contraseña, el token de verificación ni ningún token del proveedor externo.
6. WHEN una persona vuelve tras verificar pero sin haber nombrado su empresa
   THEN el sistema DEBE retomar el alta en ese punto, y NO DEBE crear una segunda
   cuenta.

### Requisito 4 — El enlace con el nivel contratado

**Historia de usuario:** Como owner recién llegado, quiero ver qué me da cada
nivel y contratar el mío, para dejar de estar en el suelo.

#### Criterios de aceptación

1. WHEN un owner en Free entra en la consola THEN el sistema DEBE ofrecerle la
   pantalla de planes de la spec 005 sin ningún paso que exija un operador.
2. WHEN el pago de un nivel se confirma THEN el partner DEBE quedar en ese nivel
   con estado `current`, y la auditoría DEBE nombrar a la persona que contrató.
3. WHILE un partner está en Free el sistema DEBE aplicarle los topes del nivel
   Free, y DEBE seguir dejándole leer lo suyo.
4. El sistema NO DEBE cobrar nada durante el alta: el alta y la contratación son
   dos actos separados, y el segundo es del owner.

### Requisito 5 — Entrar con Google

**Historia de usuario:** Como persona que ya vive en Google, quiero registrarme y
entrar con mi cuenta de Google, para no gestionar otra contraseña.

#### Criterios de aceptación

1. WHEN una persona completa el flujo del proveedor y éste afirma un correo
   verificado sin cuenta previa THEN el sistema DEBE crear la cuenta sin
   contraseña y sin enviar correo de verificación.
2. WHEN el correo afirmado por el proveedor ya tiene cuenta THEN el sistema DEBE
   vincular el proveedor a **esa** cuenta, y NO DEBE crear una segunda cuenta ni
   una segunda membresía.
3. El sistema DEBE anclar el vínculo al identificador estable que emite el
   proveedor, y NO DEBE tratar el correo como la identidad.
4. IF el valor de `state` que vuelve del proveedor falta, ha caducado, ya se usó,
   o no case con el emitido THEN el sistema DEBE rechazar la vuelta, y NO DEBE
   crear cuenta, vincular proveedor ni conceder sesión.
5. WHEN se crea una sesión por esta vía THEN DEBE ser la **misma** clase de
   sesión que la del alta con contraseña, y DEBE pasar por la misma revalidación
   de pertenencia en cada llamada.
6. IF el proveedor no está disponible THEN el sistema DEBE mantener utilizable el
   alta y el login con contraseña.
7. El sistema NO DEBE guardar ningún token del proveedor que no necesite, y
   WHERE guarde alguno DEBE quedar fuera del alcance de cualquier agente
   (constitución: ninguna credencial entra en el ambiente de un agente).

### Requisito 6 — El registro que no llega a ninguna parte

**Historia de usuario:** Como plataforma, quiero que un alta abandonada o que
nunca paga no se acumule como basura ni como coste, para que abrir la puerta no
degrade el sistema.

#### Criterios de aceptación

1. WHEN una solicitud caduca sin usarse THEN el sistema NO DEBE dejar ningún
   partner ni ninguna cuenta creados por ella.
2. El sistema NO DEBE borrar un partner: lo archiva (constitución §IV).
3. WHILE un partner esté en Free el sistema NO DEBE archivarlo por no haber
   contratado.
4. WHEN un partner lleve 180 días sin ninguna sesión de ninguno de sus miembros
   y sin ningún cliente final THEN el sistema DEBE archivarlo, y DEBE avisar a
   su owner por correo antes de hacerlo.
5. WHEN el owner de un partner archivado vuelve a entrar THEN el sistema DEBE
   poder desarchivarlo conservando lo suyo, y NO DEBE pedirle que se registre
   de nuevo.

### Requisito 7 — Contención del abuso

**Historia de usuario:** Como plataforma, quiero que un formulario público no sea
un grifo, para no pagar correo ni ensuciar la base con altas falsas.

#### Criterios de aceptación

1. El sistema DEBE limitar por ritmo las solicitudes de alta por IP y por correo
   de forma independiente, con el mismo criterio que el login.
2. El sistema DEBE limitar cuántos correos de verificación se envían al mismo
   destinatario en una ventana de tiempo.
3. WHEN se rechaza una solicitud por cualquier motivo THEN la respuesta NO DEBE
   permitir distinguir entre correo inexistente, correo ya registrado y correo
   bloqueado.
4. El sistema DEBE dejar rastro de los rechazos con suficiente detalle para
   investigarlos, y sin guardar el correo en claro allí donde no haga falta.

### Requisito 8 — Lo que ve el operador

**Historia de usuario:** Como operador, quiero ver qué partners entraron solos y
poder atenderlos, para no perder el gobierno al abrir la puerta.

#### Criterios de aceptación

1. WHEN un partner se crea por esta vía THEN DEBE aparecer en el panel de
   operador con su fecha, su vía de entrada y su nivel.
2. El operador DEBE poder reenviar un enlace de verificación y suspender un
   partner sin ejecutar ningún script dentro de la VPC.
3. El sistema DEBE seguir admitiendo el alta por invitación existente, porque un
   partner atendido por el equipo no tiene por qué pasar por el formulario.

### Entidades clave

Todas son de **plataforma**: no llevan `tenant_id` y ninguna la alcanza la RLS
por tenant, igual que `partners` y `partner_memberships` hoy. Que no haya
`tenant_id` es la afirmación, no la omisión.

- **Solicitud de alta**: un correo que pidió cuenta y todavía no la tiene.
  Guarda el correo, el hash del token de un solo uso, cuándo caduca, en qué
  estado está y por qué vía se pidió. Es lo único que existe antes de verificar,
  y se extingue al completarse el alta o al caducar.
- **Vínculo con un proveedor de identidad**: la relación entre una cuenta de
  consola y el identificador estable que un proveedor externo emite para esa
  persona. Una cuenta puede tener varios vínculos (Google hoy, otro mañana) y un
  identificador de proveedor pertenece a una sola cuenta.
- **Partner** *(existente, no se redefine)*: gana el hecho de poder nacer sin
  operador, y el rastro de por qué vía nació.
- **Cuenta de consola y membresía** *(existentes, no se redefinen)*: el alta las
  crea por el mismo camino que la invitación de hoy.

## Criterios de éxito

- **CE-001**: una persona que nunca ha hablado con nadie del equipo pasa de la
  pantalla de entrada a estar dentro de su consola como owner **sin que nadie
  ejecute nada**, y el recorrido completo se hace en menos de cinco minutos
  incluyendo la espera del correo.
- **CE-002**: el número de altas de partner que exigen a una persona con acceso a
  la VPC baja a **cero** para el camino autónomo, y el camino por invitación
  sigue funcionando para las altas atendidas.
- **CE-003**: desde la consola de un partner recién nacido se llega a contratar
  un nivel de pago sin ningún paso manual, y la suscripción queda activa en el
  proveedor y en el libro.
- **CE-004**: nadie puede averiguar desde fuera si un correo tiene cuenta en la
  plataforma: las respuestas del alta son indistinguibles, como ya lo son las
  del login.
- **CE-005**: el alta con Google se completa sin que la persona escriba una
  contraseña en ningún momento, y entrar después con cualquiera de los dos
  métodos aterriza en la misma cuenta.
- **CE-006**: con el proveedor externo caído, el alta y el login con contraseña
  siguen funcionando.

## Fuera de alcance

- **El tratamiento fiscal** (IVA europeo con ventanilla única, IVA chileno) —
  es asesoría, no ingeniería, y ya está declarado como precondición de cobro en
  la spec 005 y en `pendientes` §3. Esta spec construye el camino; cobrarle a un
  desconocido de verdad sigue bloqueado por lo mismo que antes.
- **Mover la cuenta del proveedor de pago** a una persona jurídica — `pendientes`
  §4, con su propio runbook. Que ahora entren partners solos aumenta la urgencia
  de esa decisión, pero no la resuelve esta spec.
- **Otros proveedores de identidad** (Microsoft, SAML corporativo) — se abre uno,
  no una familia. Lo que sí exige esta spec es que añadir el segundo no obligue a
  rehacer el primero.
- **Facturación por uso al registrarse, pruebas gratuitas con tarjeta y cupones**
  — el nivel Free ya es el escalón de entrada y existe desde la migración 0116.
- **Autoservicio de baja y borrado de cuenta** — «borrar no existe: se archiva»
  ya lo acota; el autoservicio de la baja es otra decisión de producto.
- **Recuperación de contraseña** — falta, pero es un hueco anterior e
  independiente de éste; si entra aquí, entra por su propio requisito y no de
  contrabando.

## Supuestos

- El nivel **Free** (migración 0116: un miembro, cero teammates, sin fila de
  suscripción) es el destino natural de un partner recién registrado. No hace
  falta inventar un estado nuevo para «registrado y sin pagar».
- El alta del primer owner **reutiliza** el flujo de invitación existente en vez
  de abrir un segundo camino a crear membresías. Dos caminos a la misma tabla
  divergen.
- La consola sigue **sin base de datos** (ADR-032): todo lo que decide el alta se
  decide en la API, y el BFF sólo transporta.
- El envío de correo de `services/email.py` es suficiente para la verificación.
  Si su entregabilidad no da la talla para correo transaccional a desconocidos,
  eso es un hallazgo del plan, no un supuesto de esta spec.
- El volumen esperado en los primeros meses es de unidades a decenas de altas
  diarias. Los límites de ritmo se dimensionan para eso, no para una campaña.
- Producción tiene hoy 2 partners y 3 clientes finales con tráfico. Nada de esta
  spec cambia el camino por el que hoy entran o trabajan: el formulario es una
  puerta **nueva**, y la existente se queda donde está.
