# Especificación: La máquina se registra con la sesión

**Rama**: `012-la-maquina-se-registra-con-la-sesion` · **Creada**: 2026-09-22 · **Estado**: Borrador

**Entrada**: evaluación `.specify/assessments/maquina-sin-emparejar/`, cerrada con
`go` el 2026-09-22. Su `decision.md` es el texto canónico y sus seis decisiones
(D-1…D-6) no se re-discuten aquí: se traducen a requisitos.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `3a` (el puente) y la API. **Sustitución, no apertura** — ver la nota de abajo |
| **Garantías de aislamiento tocadas** | Ninguna de las ocho se debilita. Se **apoya** en la 1 (RLS) y respeta la separación partner/persona que ya vigilan `test_29` y `test_30` |
| **Nota de KB que la justifica** | `[[research/2026-09-19-auditoria-clase-mundial/_index]]` §5 fila 012, y §A del informe 06 de referentes |
| **Qué se mide** | Nada |

> **Por qué esto no abre superficie nueva (constitución §II).** El endpoint que
> emite una credencial de máquina a partir de una sesión web **sustituye** a uno
> que hoy emite la misma credencial a partir de un código tecleado **desde una
> aplicación que ya tiene esa misma sesión**. La autoridad no cambia de manos:
> era la sesión antes y es la sesión ahora. Lo que se retira es un segundo acto
> que no probaba nada — y que además es el patrón que explotó Storm-2372 contra
> el device code flow.
>
> A diferencia de la spec 009, esto **no abre ningún puerto** y no enmienda
> `no-inbound.test.ts`: es una petición saliente más.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Se puede retirar el acceso de una persona, entero y de golpe (Prioridad: P1)

Alguien pierde el portátil, o se va del equipo, o cree que le han entrado en la
cuenta. Con una sola acción, esa persona queda fuera: sus sesiones abiertas
dejan de valer y sus máquinas dejan de poder leer y ejecutar.

**Por qué esta prioridad**: porque **hoy no se puede**, ni siquiera a mano. No
existe ninguna forma de cerrar todas las sesiones de una cuenta —los dos únicos
borrados son «las caducadas» y «ésta una»— y desemparejar desde la aplicación no
toca el servidor: la credencial sigue valiendo hasta doce horas. Es el único
tramo de esta spec que **tiene valor sin retirar nada**, y es la pieza que la
spec 011 va a usar cuando restablecer la contraseña revoque las máquinas (D-6).

**Prueba independiente**: una persona con dos sesiones y dos máquinas. Se retira
su acceso. Las dos sesiones dejan de resolver y las dos máquinas reciben su
negativa en la siguiente petición.

**Escenarios de aceptación**:

1. **Dado** una persona con sesiones abiertas y máquinas registradas, **cuando**
   se retira su acceso, **entonces** ninguna de sus sesiones resuelve y ninguna
   de sus máquinas puede latir, sondear, devolver resultado, renovar ni declarar
   un directorio.
2. **Dado** que retirar el acceso falla a mitad, **cuando** se consulta después,
   **entonces** o se retiró todo o no se retiró nada — nunca las sesiones sin las
   máquinas.
3. **Dado** dos personas del mismo partner, **cuando** se retira el acceso de
   una, **entonces** la otra conserva sus sesiones y sus máquinas.
4. **Dado** que se retiró el acceso, **cuando** se mira la auditoría,
   **entonces** consta qué se retiró, de quién y por qué.

---

### Historia 2 — Desemparejar dice la verdad (Prioridad: P1)

Alguien desempareja una máquina desde la aplicación. La pantalla le dice **qué
pasa de verdad**: la máquina queda pendiente de archivar desde la consola, y
volver a usarla no es «emparejarla otra vez» sino dar de alta una nueva.

> **Esta historia cambió de forma el 2026-09-22, al implementarla, y conviene
> que se vea.** Decía «desemparejar revoca de verdad» y pedía que la aplicación
> revocara en el servidor. **Estaba mal**, y no por un detalle: la spec 002 ya
> se había hecho esta pregunta y la contestó al revés, con la razón escrita en
> su R11.2 — *«archivar es un acto de persona con su nombre (R13.1) y la
> credencial no gana una sexta operación (R4.2)»*.
>
> Es una decisión buena y sigue siéndolo. Archivar con el nombre de quien lo
> hace es §IV; dejar que una credencial de máquina se revoque a sí misma abre
> una operación más en la superficie `3a` para ahorrar un viaje a la consola.
>
> **Lo que sí estaba roto es el texto**, y resulta que incumple dos requisitos
> de la 002 a la vez: no dice que la máquina queda pendiente de archivar
> (R11.2), y promete «hasta que la vuelvas a emparejar» cuando **archivar es
> terminal y se da de alta otra** (R11.5). O sea: la pantalla mentía, que era el
> diagnóstico correcto — pero el arreglo no era construir la revocación, era
> decir lo que pasa. **Menos código y más honesto.**
>
> El caso que preocupaba —desemparejo porque he perdido el control de esa
> máquina— **ya tiene respuesta, y es la Historia 1**: retirar el acceso, o
> archivar desde la consola. La aplicación del portátil que ya no controlas no
> es el sitio donde se arregla eso.

**Por qué esta prioridad**: porque una pantalla que miente sobre lo que apaga es
peor que una que no lo ofrece, y porque el arreglo es barato.

**Prueba independiente**: desemparejar y leer lo que dice la pantalla.

**Escenarios de aceptación**:

1. **Dado** una máquina emparejada, **cuando** la persona va a desemparejarla,
   **entonces** se le dice que la máquina queda **pendiente de archivar desde la
   consola** y que su credencial deja de valer cuando se archive.
2. **Dado** que se desemparejó, **cuando** la persona quiere terminar el
   trabajo, **entonces** la aplicación le ofrece el camino a archivarla en la
   consola, sin que tenga que buscarlo.
3. **Dado** que se desemparejó, **cuando** la persona quiere volver a usar esa
   máquina, **entonces** lo que se le ofrece es **darla de alta de nuevo**, y en
   ningún sitio se le promete «volver a emparejar la misma».

---

### Historia 3 — Entrar deja la máquina lista (Prioridad: P1)

Se instala la aplicación, se entra por el navegador, y ya está: la máquina
trabaja. No hay código que pedir en otra pantalla, ni que copiar, ni que teclear
antes de que caduque.

**Por qué esta prioridad**: es el corazón de la spec y lo que se ve en el primer
minuto. Hoy son doce pasos hasta el primer trabajo útil; el listón externo son
tres o cuatro. Y el paso que se retira **no protege nada**: para poder teclear
el código, la aplicación ya tenía la sesión confirmada.

**Prueba independiente**: instalación limpia, entrar, y comprobar que la máquina
queda registrada y trabajando sin ningún paso intermedio.

**Escenarios de aceptación**:

1. **Dado** una instalación sin máquina registrada, **cuando** la persona entra
   por el navegador y vuelve, **entonces** la máquina queda registrada y lista,
   sin pantalla intermedia.
2. **Dado** una sesión abierta hace días, **cuando** se abre la aplicación en
   una máquina sin registrar, **entonces** se pide entrar de nuevo antes de
   registrarla.
3. **Dado** una persona sin permiso para registrar máquinas, **cuando** lo
   intenta, **entonces** se rechaza y se le dice qué le falta.
4. **Dado** un registro que falla, **cuando** se reintenta, **entonces** el
   rechazo es el mismo sea cual sea el motivo, y hay un techo de intentos.
5. **Dado** una máquina que se registra, **cuando** se mira la auditoría,
   **entonces** consta — el registro es silencioso para la persona, no para el
   registro.

---

### Historia 4 — Hay un tope de máquinas (Prioridad: P2)

Una persona no acumula máquinas sin darse cuenta. Al llegar al tope, se le dice
cuál retirar.

**Por qué esta prioridad**: hoy no hay tope, y el límite práctico era **la
fricción de pedir un código**. La Historia 3 retira esa fricción, así que sin
esto se quita el único freno que había. No es P1 porque el daño es acumulativo y
lento, no inmediato.

**Prueba independiente**: registrar máquinas hasta el tope y comprobar qué pasa
en la siguiente.

**Escenarios de aceptación**:

1. **Dado** una persona en el tope de máquinas, **cuando** registra otra,
   **entonces** se rechaza diciendo cuántas tiene y cuál puede retirar, y **no**
   se archiva ninguna por su cuenta.
2. **Dado** una persona en el tope, **cuando** retira una y registra otra,
   **entonces** funciona.
3. **Dado** máquinas archivadas, **cuando** se cuenta para el tope, **entonces**
   no cuentan: lo archivado no ocupa sitio.

---

### Historia 5 — La decisión que importa es la carpeta (Prioridad: P2)

El acto deliberado que la persona hace —y recuerda— es **decir qué carpeta toca
un teammate para un cliente**, no demostrar qué ordenador es éste.

**Por qué esta prioridad**: es la mitad buena de la evaluación y casi no hay que
construirla: declarar el directorio ya existe, con sus asientos de auditoría y
su denegación. Lo que falta es que se vea. Va detrás de la 3 porque sin ella el
sitio donde ponerla todavía está ocupado por la ceremonia.

**Prueba independiente**: instalación limpia; comprobar que tras entrar, lo
primero que se ofrece es declarar el directorio de un cliente.

**Escenarios de aceptación**:

1. **Dado** una máquina recién registrada sin directorios declarados,
   **cuando** la persona llega a la aplicación, **entonces** lo que se le ofrece
   es declarar la carpeta de un cliente, no un estado de la máquina.
2. **Dado** un teammate sin carpeta declarada para su cliente, **cuando** va a
   trabajar con ficheros, **entonces** se dice qué falta y cómo declararla.

---

### Historia 6 — El código desaparece (Prioridad: P3)

Nadie vuelve a ver un código de ocho símbolos, ni en la consola ni en la
aplicación.

**Por qué esta prioridad**: es limpieza, y va la última a propósito: se retira
cuando ya nadie lo usa. Entregar la Historia 3 sin esto deja dos caminos
abiertos un tiempo, que es incómodo pero seguro; al revés sería dejar a la gente
sin ninguno.

**Prueba independiente**: buscar en la consola y en la aplicación; no queda
pantalla, campo ni canal de emparejar por código.

**Escenarios de aceptación**:

1. **Dado** el producto entregado, **cuando** se busca cómo emparejar con un
   código, **entonces** no existe: ni pantalla, ni campo, ni endpoint.
2. **Dado** una máquina registrada antes del cambio, **cuando** se usa después,
   **entonces** sigue funcionando: nadie tiene que volver a registrarla.

---

### Casos límite

- **Registrar dos veces desde la misma máquina** (la persona abre la aplicación
  dos veces, o reinstala): no aparecen dos máquinas donde había una.
- **Volver a registrar una máquina archivada**: archivar es terminal —«borrar no
  existe: se archiva, y queda por qué»—, así que la vuelta crea una **fila
  nueva**. Deja de ser un caso raro y pasa a ser el camino de después de cada
  restablecimiento de contraseña (D-6): tiene que funcionar sin tropezar con la
  archivada.
- **La sesión caduca mientras se registra**: se pide entrar, no se deja la
  máquina a medio registrar.
- **Dos personas en la misma máquina física**: cada una con su credencial; la de
  una no aparece por haber entrado la otra.
- **Se retira el acceso de una persona mientras su máquina está ejecutando algo**:
  lo que ya está en marcha en la máquina no se puede parar desde aquí — lo que se
  corta es que pueda volver a pedir trabajo o devolver resultado. **La pantalla
  tiene que decir eso y no más.**
- **La capacidad no disponible** (§V): quien no tiene permiso para registrar
  máquinas no ve un botón apagado — ve lo que sí puede hacer, y el motivo
  aparece si lo intenta por otra vía.

## Requisitos *(obligatorio)*

### Requisito 1 — Retirar todo el acceso de una persona

**Historia de usuario:** Como partner, quiero poder dejar fuera a una persona de
golpe, para que perder un portátil o sospechar de una cuenta tenga una respuesta.

#### Criterios de aceptación

1. El sistema DEBE ofrecer una operación que retire **a la vez** todas las
   sesiones y todas las máquinas de una persona.
2. WHEN esa operación se ejecuta THEN el sistema DEBE hacerlo de forma atómica, y
   NO DEBE dejar un estado donde las sesiones estén retiradas y las máquinas no,
   ni al revés.
3. WHEN una sesión retirada se presenta THEN el sistema DEBE rechazarla.
4. WHEN una máquina retirada presenta su credencial THEN el sistema DEBE
   rechazarla en **cualquiera** de las cinco operaciones del puente, aunque la
   credencial no haya caducado.
5. WHERE hay más personas en el mismo partner EL sistema DEBE dejar intactas sus
   sesiones y sus máquinas.
6. WHEN se retira el acceso THEN el sistema DEBE dejar asiento de auditoría con
   quién lo hizo, sobre quién y por qué.

### Requisito 2 — Desemparejar dice la verdad

**Historia de usuario:** Como partner, quiero que la pantalla de desemparejar me
diga qué apago y qué no, para no creer que he cerrado algo que sigue abierto.

#### Criterios de aceptación

1. WHEN la persona va a desemparejar THEN la aplicación DEBE decir que la
   máquina queda **pendiente de archivar desde la consola** (spec 002, R11.2), y
   NO DEBE afirmar que la credencial deja de valer en ese momento.
2. La aplicación NO DEBE prometer «hasta que la vuelvas a emparejar»: archivar
   es terminal y lo que procede es **dar de alta otra** (spec 002, R11.5).
3. WHEN la máquina queda desemparejada THEN la aplicación DEBE ofrecer el camino
   para archivarla en la consola, y NO DEBE dejar a la persona buscándolo.
4. WHEN una máquina archivada presenta su credencial THEN el sistema DEBE
   rechazarla con el motivo que ya usa hoy. *(Ya se cumple: `require_device` lo
   hace. Se prueba para que no se pierda, no porque falte.)*

### Requisito 3 — La máquina se registra con la sesión

**Historia de usuario:** Como partner, quiero que entrar deje mi máquina lista,
para no hacer dos veces el mismo trámite.

#### Criterios de aceptación

1. WHEN una persona con sesión confirmada abre la aplicación en una máquina sin
   registrar THEN el sistema DEBE registrarla y entregar su credencial **una
   sola vez**, sin pantalla intermedia.
2. IF la sesión no se ha confirmado recientemente THEN el sistema DEBE pedir que
   se entre de nuevo antes de registrar, y NO DEBE registrar con una sesión
   antigua sin más.
3. WHEN se pide registrar THEN el sistema DEBE comprobar que la persona tiene el
   permiso de emparejar puesto de trabajo.
4. IF el registro se rechaza **por la sesión** THEN el sistema NO DEBE
   distinguir entre «no hay sesión» y «la sesión es vieja»: las dos llevan al
   mismo sitio, que es entrar de nuevo.
5. WHERE el rechazo es por permiso o por el tope EL sistema DEBE decirlo, como
   hace el resto de la consola.

> **Enmendado el 2026-09-22, al implementarlo.** Esto decía que los **cuatro**
> motivos dieran una respuesta idéntica, heredando el rechazo indistinguible que
> la spec 009 dejó escrito. **Estaba sobre-aplicado.** Aquel rechazo protege el
> canje de un código, donde quien llama es **un desconocido** y puede probar
> códigos hasta acertar: ahí distinguir es un oráculo.
>
> Aquí no hay desconocido. Quien llama ya presentó su sesión y su membresía, y
> los cuatro motivos son sobre **sí mismo**: su sesión, su permiso, sus
> máquinas. Decirle «no tienes permiso» es lo que hace el resto de la consola, y
> decirle cuántas máquinas tiene es información **suya**. Uniformarlo no
> protegía a nadie y dejaba a la persona sin saber qué hacer.
>
> Lo que sí se conserva es lo que de verdad heredaba sentido: **no distinguir
> entre «no hay sesión» y «la sesión caducó»**, porque la acción es la misma.
> Y esto de paso resuelve la contradicción que el análisis cruzado había
> encontrado entre este criterio y R4.4.
5. El sistema DEBE limitar los intentos de registro.
6. WHEN una máquina se registra THEN el sistema DEBE dejar asiento de auditoría,
   aunque para la persona el registro sea silencioso.
7. WHEN la misma máquina se registra otra vez para la misma persona THEN el
   sistema DEBE devolver la que ya existe en vez de crear una segunda.

### Requisito 4 — Tope de máquinas

**Historia de usuario:** Como partner, quiero un techo de máquinas por persona,
para que retirar la fricción no signifique retirar el control.

#### Criterios de aceptación

1. WHERE una persona alcanza el tope de máquinas activas EL sistema DEBE
   rechazar el registro siguiente.
2. WHEN se rechaza por el tope THEN el sistema NO DEBE archivar ninguna máquina
   por su cuenta.
3. WHEN se cuentan las máquinas para el tope THEN el sistema NO DEBE contar las
   archivadas.
4. WHEN se rechaza por el tope THEN el sistema DEBE decir que ése es el motivo,
   para que la persona sepa qué hacer: retirar una. *(Tras la enmienda de R3.5,
   esto ya no choca con nada: quien pregunta está autenticado y el número de sus
   propias máquinas es información suya.)*

### Requisito 5 — La carpeta al frente

**Historia de usuario:** Como partner, quiero que lo que me pida la aplicación
sea decidir qué carpeta toca un teammate, porque es la decisión que importa.

#### Criterios de aceptación

1. WHEN una máquina recién registrada no tiene ningún directorio declarado THEN
   la aplicación DEBE ofrecer declarar el de un cliente como siguiente paso.
2. WHERE un teammate va a trabajar con ficheros de un cliente sin directorio
   declarado EL sistema DEBE decir qué falta y cómo declararlo.

### Requisito 6 — El código de emparejamiento desaparece

**Historia de usuario:** Como quien mantiene esto, quiero que no quede un
segundo camino para registrar una máquina, porque dos caminos son dos que
auditar.

#### Criterios de aceptación

1. El sistema NO DEBE ofrecer ninguna forma de registrar una máquina con un
   código tecleado: ni pantalla, ni campo, ni endpoint, ni canal entre la
   aplicación y su proceso principal.
2. WHEN una máquina registrada antes del cambio presenta su credencial THEN el
   sistema DEBE seguir aceptándola: nadie vuelve a registrar lo que ya tenía.
3. El sistema NO DEBE conservar la tabla de códigos ni su emisor.

### Requisito 7 — Lo que se conserva del código que se retira

**Historia de usuario:** Como quien revisa la seguridad de esto, quiero que
retirar la ceremonia no retire sus propiedades, porque eran lo bueno que tenía.

#### Criterios de aceptación

1. La credencial de máquina DEBE entregarse **una sola vez** y no poder volver a
   leerse.
2. WHEN el canje se rechaza THEN el sistema DEBE dar una respuesta
   indistinguible entre motivos.
3. El sistema DEBE mantener un techo de intentos sobre el canje.
4. El sistema NO DEBE guardar ningún secreto de registro en claro.

### Entidades clave

- **Máquina registrada** (`partner_devices`): el ordenador de una persona, a
  nombre de **un partner** y de **una persona de ese partner**. Pertenece al
  partner, no a un tenant cliente: la RLS la alcanza por `partner_id`, y la
  separación por persona la añade `principal_id`. Nunca lleva `tenant_id`.
- **Sesión de consola** (`principal_sessions`): cuelga de la persona por
  `principal_id`. Tiene un momento de apertura, que no se mueve con el uso, y un
  momento de último uso, que sí. **Los dos no son lo mismo**, y el Requisito 3.2
  depende del primero.
- **Asiento de auditoría**: registra los hechos del ciclo de vida de una máquina.
  Es de plataforma, no de tenant.

## Criterios de éxito *(obligatorio)*

- **CE-001**: desde instalar hasta el primer trabajo útil hay **cuatro pasos**
  —instalar, entrar, declarar la carpeta, escribir— frente a los doce de hoy.
- **CE-002**: en el primer uso no hay **ningún** paso que caduque mientras la
  persona lo hace.
- **CE-003**: retirar el acceso de una persona deja **cero** sesiones válidas y
  **cero** máquinas capaces de trabajar, comprobado en la siguiente petición de
  cada una y sin esperar a ninguna caducidad.
- **CE-004**: el ciclo de vida de una máquina deja asiento **en los dos
  extremos**: al registrarse y al retirarse. Hoy solo en uno.
- **CE-005**: ninguna persona puede acumular máquinas activas por encima del
  tope.
- **CE-006**: no queda en el producto ninguna forma de registrar una máquina
  tecleando un código.

## Fuera de alcance

- **Mover la ejecución del agente a la máquina** — es la otra diferencia con los
  referentes, es mucho más grande, y no hace falta para esto. Vive en
  `.specify/assessments/teammate-que-trabaja-en-la-terminal/`.
- **Rediseñar la credencial de máquina o su renovación** — el JWT de doce horas
  con generación y gracia de sesenta segundos funciona y no se toca.
- **Tocar el inicio de sesión** — la spec 009 ya lo resolvió con navegador y
  PKCE. Esto se apoya en él, no lo cambia.
- **Segundo factor** — si algún día se quiere, se pide sobre la sesión, no sobre
  la máquina.
- **Emparejar una máquina que no es la tuya** — Luis confirmó el 2026-09-22 que
  ese caso no existe. Si apareciera, se reabre con su propia evaluación.
- **Restablecer la contraseña** — es la spec 011. Esta construye la pieza que
  aquélla usará (D-6), pero no el flujo de recuperación.

## Supuestos

- **El momento de apertura de una sesión existe y no se mueve con el uso**, así
  que «confirmada hace poco» es distinguible de «usada hace poco». Verificado
  antes de escribir este documento; el Requisito 3.2 depende de ello.
- **El umbral de frescura se fija en una hora.** Es el estándar de la industria
  para re-autenticación ante acciones sensibles, y en el camino normal —instalar,
  entrar, volver— no se nota porque la sesión tiene segundos de vida. El plan
  puede revisarlo con datos, pero no se deja sin decidir.
- **El tope se fija en cinco máquinas activas por persona.** No hay dato de
  producción que lo respalde; se elige un número que no estorba a nadie que
  trabaje normal y que hace ruido si algo va mal. Revisable con datos.
- Registrar una máquina es un acto que ocurre **una vez por máquina**, así que
  pedir entrar de nuevo cuando la sesión es vieja no molesta de forma recurrente.
- La aplicación ya tiene la sesión de consola en su partición persistente antes
  de poder registrar nada — hoy es condición necesaria para teclear el código, y
  después lo seguirá siendo para registrar.
- Ninguna máquina ya registrada deja de funcionar por este cambio.
