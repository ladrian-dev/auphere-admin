# Concept: la identidad y el consumo en la aplicación de escritorio

- **Slug**: identidad-y-consumo-en-la-app
- **Created**: 2026-09-09
- **Recommended option**: **Opción A — el código de emparejamiento**. La decisión
  transversal §T-1 se recomendó aquí a favor de *dejar el dispositivo donde está*
  (T-1a), y **la puerta de `decide` la revocó** con información que esta etapa no
  tenía. Ver «Corrección tras la puerta», al final
- **Etapas anteriores**: [`intake.md`](./intake.md) · [`research.md`](./research.md)
  · [`problem.md`](./problem.md)

> Nivel de concepto. Aquí no hay endpoints, esquemas ni tareas: eso es de
> `/speckit-specify` en adelante.

---

## El eje que separa las opciones

Las tres opciones vivas se diferencian en **una sola cosa**: por dónde viaja el
secreto desde la plataforma hasta la máquina. Todo lo demás —qué se ve, qué se
mide, qué se audita— es igual en las tres, porque viene heredado de la 001.

El impedimento que las ordena está en `research.md` D-3: hoy la página cargada
**no tiene ninguna vía de hablar con la cáscara**, y abrir una roza el Requisito
15.3, que es la razón entera por la que la aplicación se pudo construir.

---

## Options

### Option A — El código de emparejamiento

- **Sketch**: la persona entra en la consola dentro de la ventana, como ya hace
  hoy. En la sección de puesto de trabajo pide dar de alta esta máquina y la
  consola le muestra un **código corto y efímero**. La aplicación, que hasta ese
  momento se comporta como una ventana sin puente, le pide ese código en su única
  pantalla propia y lo canjea por su credencial de dispositivo. A partir de ahí
  late, sondea y ejecuta. El canal entre la web y la cáscara **es la persona**:
  no hace falta abrir ninguno.
- **Appetite**: `small`–`medium`. Semana y media larga, no un mes. La mayor parte
  ya existe: el endpoint de alta, la credencial, el transporte y la pantalla de
  dispositivos.
- **Trade-offs**:
  - **Gana**: cero superficie nueva en la cáscara. Ni `preload`, ni puente de
    contexto, ni esquema de URL propio. `session-isolation.ts` sigue diciendo la
    verdad sin matices.
  - **Gana**: el patrón es conocido y probado —es RFC 8628 con los papeles
    cambiados: aquí el navegador cómodo es la ventana, y el que espera es el
    proceso—. La forma (secreto corto, canje, caducidad, un solo uso) ya está
    resuelta en este repositorio para las invitaciones.
  - **Sacrifica**: un paso manual. La persona copia unos caracteres de una mitad
    de su pantalla a la otra. Es feo y es honesto.
  - **Sacrifica**: obliga a **una pantalla propia** de la aplicación. Hay que
    escribir por qué eso no viola el Requisito 15.1 — y la razón es que 15.1
    prohíbe *reimplementar pantallas de la consola*, y ésta no existe en la
    consola ni puede existir: pregunta por algo que solo la cáscara sabe.
  - **Riesgo**: si el código se pide por copia manual, hay que decidir su
    longitud, su caducidad y su resistencia a un intento por fuerza bruta, con
    el mismo cuidado que una invitación.
- **Rabbit holes**:
  - Diseñar «la primera pantalla de la aplicación» y que se convierta en un
    onboarding entero. El alcance es **una** pantalla con un campo y sus estados.
  - Querer que el código se autocomplete «para que sea cómodo». Autocompletar es
    exactamente la Opción B disfrazada.
  - Que la caducidad del código y la de la credencial se confundan: son dos
    relojes distintos y mezclarlos produce un estado que la pantalla no sabe
    contar (§V).

### Option B — El puente de contexto

- **Sketch**: la aplicación expone un canal mínimo a la página que carga; la
  consola detecta que corre dentro de la cáscara, y al dar de alta la máquina le
  entrega la credencial directamente. La persona no copia nada: pulsa un botón y
  la aplicación queda emparejada.
- **Appetite**: `medium`, y con una cola larga de verificación que no se ve al
  principio.
- **Trade-offs**:
  - **Gana**: la mejor experiencia con diferencia. Un botón.
  - **Sacrifica**: abre en la cáscara exactamente el tipo de superficie que la
    cáscara existe para no tener. `main.ts` presume hoy de
    `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true` y **cero
    `preload`**; esta opción rompe la cuarta.
  - **Riesgo mayor**: la garantía deja de ser estructural y pasa a ser
    condicional. Hoy el Requisito 15.3 se sostiene porque *no hay dónde mirar*;
    con un puente, se sostiene mientras nadie consiga cargar otra cosa en esa
    partición. Eso hay que probarlo, no afirmarlo, y probar una ausencia es caro.
  - **Sacrifica**: acopla la consola a la cáscara. La consola tendría que saber
    que a veces vive dentro de una aplicación, que es justo el tipo de bifurcación
    que hace divergir dos superficies (el argumento del Requisito 15.1).
- **Rabbit holes**:
  - Delimitar quién puede llamar al puente: origen, navegación, redirecciones,
    ventanas hijas. Cada respuesta abre dos preguntas.
  - El día que se quiera cargar cualquier cosa que no sea la consola en esa
    ventana, el puente se convierte en el problema.

### Option C — El esquema de URL propio

- **Sketch**: el alta ocurre en la consola —dentro o fuera de la ventana— y
  termina en un enlace `auphere://…` que el sistema operativo entrega a la
  aplicación instalada, credencial incluida. Sirve además para el enlace de
  invitación que hoy llega por correo y muere en el navegador del sistema
  (research D-2).
- **Appetite**: `medium`, con dependencia externa.
- **Trade-offs**:
  - **Gana**: resuelve de paso el problema del correo de invitación.
  - **Sacrifica**: registrar un esquema propio convierte a la aplicación en algo
    invocable **desde cualquier página web** de la máquina. Es superficie de
    entrada nueva, y el Requisito 6.1 de la 001 —«nada entra desde internet a mi
    máquina»— se escribió con otro sentido, pero el espíritu queda incómodo.
  - **Sacrifica**: depende del empaquetado firmado, y `T057` está bloqueada por
    certificados que hoy no existen. En Windows el registro es distinto del de
    macOS y hay que pagar los dos.
  - **Riesgo**: un secreto viajando por una URL que pasa por el sistema operativo
    puede acabar en registros que nadie ha auditado.
- **Rabbit holes**: el registro del protocolo en las dos plataformas; el
  comportamiento cuando hay dos versiones instaladas; y la tentación de meter más
  cosas por el esquema una vez existe.

### Option D — No hacer nada (seguir con el script de operador)

- **Sketch**: se acepta que dar de alta una máquina es un procedimiento de
  Auphere. Un operador ejecuta el script, entrega el token por un canal acordado,
  y el partner lo pone donde se le diga.
- **Appetite**: `zero`.
- **Trade-offs**:
  - **Gana**: cero trabajo, y con uno o dos partners piloto funciona.
  - **Sacrifica**: **no sobrevive a las 12 horas** (research D-7). Esta opción no
    es «lento pero funciona»: es que la instalación se muere sola el mismo día.
  - **Sacrifica**: exige acceso a la base de producción en cada alta, y el envío
    de un secreto por un canal sin definir. Es un procedimiento que no se puede
    auditar ni delegar.
- **Rabbit holes**: ninguno, y ése es su único mérito.

> **Nota sobre «comprar en vez de construir»**: no aplica. El emparejamiento es
> con *nuestra* credencial de dispositivo y *nuestro* modelo de pertenencia. No
> hay nada que comprar; lo que sí se copia —y se cita— es la forma de RFC 8628 y
> la del flujo de invitaciones que ya vive en este repositorio.

---

## Decisiones transversales — no son opciones, hay que tomarlas igual

Las tres atraviesan cualquier opción elegida. `decide` tiene que pronunciarse
sobre las tres, porque dejarlas implícitas es como llegaron a estar como están.

### T-1 · ¿De quién es un dispositivo — del tenant cliente o del partner?

Es **la pregunta más cara del expediente**. Hoy `partner_devices` va por
`tenant_id` con RLS forzada, y un portátil que sirve a cinco clientes son cinco
filas y cinco credenciales (research D-5).

- **T-1a · Dejarlo donde está (del tenant), y decirlo.** Coste: cero código. La
  persona empareja una vez por cliente. Con un piloto es soportable; con cinco
  clientes es un peaje visible.
- **T-1b · Moverlo al partner.** La máquina se empareja una vez y el tenant lo
  fija cada trabajo despachado, no la credencial. Coste: modelo de datos de la
  001, su RLS, el Requisito 6.3 —que dice literalmente «acotada a su tenant»— y
  `test_29`. Toca §I de frente, así que no es un refactor: es otra spec.

### T-2 · ¿Qué hace la aplicación con `principal_id`?

La columna existe, se escribe y **nadie la lee** (research D-6). La decisión 9
dice «privado por persona» y el mecanismo ya está construido para el Companion
(`0090_companion.py` + `core/principal_context.py`). Aquí caben dos posturas:
leerla ahora —barato, porque el mecanismo existe— o dejarla escrita y sin uso una
temporada más, sabiendo que cada día que pasa es más raro explicarlo.

### T-3 · Qué es cerrar sesión y qué es desemparejar

Son dos actos. Con lo que hay hoy, **ninguno de los dos detiene el puente**:
cerrar sesión no toca la credencial de dispositivo, y archivar el dispositivo
tampoco, porque nadie mira `revoked_at`. Cualquier política que se escriba aquí
depende de que ese incumplimiento del Requisito 6.3 se arregle por su camino.

---

## Recommendation

**Opción A, con T-1a, T-2 «leerla ahora» y T-3 escrita como política explícita.**

El razonamiento, atado a las metas de `problem.md`:

1. **La meta 1 —entregar sin tocar la base— la cumplen A, B y C por igual.** No
   discrimina. Lo que discrimina es el precio, y §II lo dice sin ambigüedad:
   *agotar el valor que quepa dentro de la superficie ya abierta antes de abrir
   la siguiente*. B abre una superficie dentro de la cáscara; C abre una en el
   sistema operativo. **A no abre ninguna.**
2. **La meta 6 —no empeorar lo que en el navegador funciona— y el riesgo de Meta
   (M-6) siguen ahí en las tres opciones.** Ninguna los resuelve, así que no
   deben usarse para elegir; se atacan por separado, con un spike acotado que va
   **antes** que todo lo demás, por la misma razón por la que la 001 puso la
   verificación del catálogo y de los subagentes al principio y no al final.
3. **La meta 3 —que la instalación sobreviva— no la resuelve ninguna opción por
   sí sola**: es la caducidad de 12 horas sin renovación (research D-7). Va
   dentro del alcance recomendado, se elija lo que se elija, y es la razón por la
   que la Opción D no es una opción sino una fecha de caducidad.
4. **T-1a se recomienda por §II y no por comodidad.** T-1b puede acabar siendo lo
   correcto, pero toca §I de frente y eso lo convierte en su propia evaluación.
   Lo que **no** se acepta es seguir como estamos: T-1a hay que **escribirla como
   decisión con su motivo**, no dejarla como herencia de un modelado que nadie
   discutió.
5. **T-2 «leerla ahora» sale casi gratis** porque el mecanismo existe y está
   probado, y cierra la distancia entre la decisión 9 y el código antes de que se
   ensanche. Es el valor barato que cabe dentro de la superficie ya abierta.
6. **La meta 5 —un solo contador— se cumple no haciendo nada**: la aplicación
   carga `/usage`. Se escribe como restricción para que nadie la rompa con buena
   intención.

**Sobre el consumo, dicho en una frase para que no se convierta en trabajo:** el
partner ve su consumo entrando en `/usage` dentro de la ventana, como ve todo lo
demás. No hay pantalla nueva porque no hay concepto nuevo.

---

## Out of Scope (for the recommended option)

Además de todo lo que `problem.md` puso en Non-Goals:

- **El puente de contexto y el esquema de URL propio.** Se descartan aquí con su
  motivo escrito, no se aplazan sin decirlo.
- **Mover el dispositivo al partner (T-1b).** Si se quiere, es una evaluación
  propia porque toca §I.
- **Resolver el enlace de invitación que llega por correo.** Sigue naciendo en el
  navegador del sistema, y con la Opción A eso no impide emparejar: la persona
  entra en la aplicación y desde ahí empareja. Se anota como aspereza conocida.
- **Arreglar la revocación rota del Requisito 6.3.** Va por su camino; aquí solo
  se declara la dependencia.
- **Cualquier cifra de consumo calculada por la aplicación.**

---

## Assumptions to Validate

- **La consola se puede usar dentro de la ventana para todo lo que el partner
  necesita el primer día.** El riesgo conocido es el Embedded Signup de Meta
  (research D-2, confianza media). **Se valida con un spike antes de especificar**,
  no durante la implementación.
- **Una pantalla propia de la aplicación no viola el Requisito 15.1.** La lectura
  es que 15.1 prohíbe reimplementar pantallas *de la consola*, y ésta pregunta por
  algo que solo la cáscara sabe. Hay que escribirlo en la spec y sostenerlo.
- **La credencial de dispositivo admite renovación sin dejar de ser lo que el
  Requisito 6.3 dice que es** —propia de la máquina, acotada a su tenant,
  revocable por sí sola y limitada a cuatro operaciones—. Si renovarla obliga a
  ampliar esas cuatro operaciones, la premisa cambia y hay que decirlo.
- **Un piloto con un solo cliente por máquina es cierto durante la beta 2.** Es lo
  que hace tolerable T-1a. Si el primer partner llega con tres clientes en la
  misma máquina, la recomendación se debilita y T-1b sube en la lista.
- **`principal_id` puede leerse con el mecanismo del Companion sin tocar la RLS
  por tenant que ya existe** en `0106_local_workstation.py`. Es lo que hace barato
  T-2; si resulta que hay que rehacer la política, deja de serlo.

---

## Corrección tras la puerta de `decide` (2026-09-09)

Esta etapa recomendó **T-1a** —dejar el dispositivo colgando del tenant— y lo
hizo apoyada en un supuesto explícito: *«un piloto con un solo cliente por
máquina es cierto durante la beta 2»*. Ese supuesto era el que sostenía la
recomendación, y estaba escrito arriba precisamente para que se pudiera derribar.

Se derribó en la puerta. El propósito del producto, dicho por Luis: **la
aplicación es la herramienta con la que un partner configura y administra a sus
clientes**, en plural y desde el primer día. Con eso encima de la mesa, T-1a no
es «deuda tolerable»: es entregar un emparejamiento que la persona tiene que
repetir una vez por cada cliente que administre, en la misma máquina, para acabar
con varias credenciales que la aplicación no puede llevar a la vez.

**La decisión pasa a ser T-1b**, con su coste dicho: toca el modelo de datos de
la 001, obliga a **enmendar el Requisito 6.3** —que hoy dice «acotada a su
tenant»— y exige tests de aislamiento nuevos. El apetito sube de `small`–`medium`
a **`medium`**. El detalle y el razonamiento están en
[`decision.md`](./decision.md).

Las otras dos recomendaciones de esta etapa —Opción A y T-2— pasaron la puerta
sin cambios.
