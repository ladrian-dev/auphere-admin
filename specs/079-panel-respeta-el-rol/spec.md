# Especificación: el panel respeta el rol del operador

**Rama**: `079-panel-respeta-el-rol` · **Creada**: 2026-11-25 · **Estado**: Aprobada (Luis, 2026-11-25)

**Entrada**: la spec 078 cerró el panel a quien no sea un operador activo y dejó fuera, a propósito, el rol: «decidir qué puede hacer cada rol es una spec aparte», y que la API sepa qué operador pide cada cosa, «el arreglo de fondo». Esta es esa spec.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | El panel de operadores (`apps/admin`): sus Server Actions, sus páginas y sus rutas de `app/api`. En la fase 2, también las rutas `/admin/*` de la API. No abre ninguna superficie: acota quién puede usar una que ya está abierta. |
| **Garantías de aislamiento tocadas** | **Ninguna de las 8.** No separa negocios ni clientes finales: decide qué persona del equipo de Auphere puede hacer qué. Las pruebas son de autorización y barren el código: la estructural del panel (la de la 078, ampliada) y, en la fase 2, una de la API sobre todas las rutas `/admin/*`. |
| **Nota de KB que la justifica** | `[[decisions/ADR-050-el-rol-del-operador-decide]]`, que sustituye la premisa de `[[decisions/ADR-009-operator-only-panel]]` (el panel como «god-mode» para el equipo, con su Fase 2 pendiente) y `[[decisions/ADR-034-identidad-del-panel-de-operador-en-la-api]]` (la deuda: la API no sabe qué operador pide cada cosa), en `/Users/lmatos/Work/Auphere/nexus/`. |
| **Qué se mide** | **Nada.** No gasta modelo, reloj de máquina ni herramientas. |

## Por qué

El panel distingue tres roles —`admin`, `qa_operator` y `viewer`— y el menú del operador los nombra («Administrador», «Operador QA», «Solo lectura»). Pero solo el Playground QA mira el rol. Todo lo demás lo decide `requireOperator()`, que desde la 078 comprueba que la cuenta esté activa y nada más. La etiqueta «Solo lectura» promete algo que el panel no cumple, y eso choca con la constitución §V: la pantalla no miente.

Hay un segundo hueco, más hondo. La API recibe las llamadas del panel con un único token de servicio. Algunas rutas nombran además al operador, pero como una afirmación del panel, y otras no lo nombran. La API no puede comprobar el rol por su cuenta, y la auditoría de muchas escrituras no dice qué persona las hizo (constitución §IV).

ADR-009 diseñó el panel como «god-mode» para un equipo de tres a cinco personas. Con tres roles que ya existen, y uno que se llama «Solo lectura», esa premisa ya no basta.

## Cómo se entrega

- **Fase 1a — la guarda del servidor** (requisitos 1, 2, 4 y 5, salvo 1.6). La matriz y el permiso declarado en cada acción, página y ruta, con su prueba. Entra en el envío a producción del 2026-11-26 (06:00 UTC). Se puede desplegar sola: cierra el hueco para cualquier uso del panel.
- **Fase 1b — la interfaz** (requisito 3 y criterio 1.6). Ocultar lo que el rol no puede hacer y el rol por defecto. Después del envío.
- **Fase 2 — la API** (requisito 6). La API conoce al operador de cada llamada y aplica la misma matriz. Es la defensa que no depende de que el panel no se equivoque. Después de la 1b.

El inventario de lo que hay que proteger, clasificado por efecto, está en [`inventario.md`](inventario.md): 131 funciones de Server Action, 10 rutas (nueve en `app/api` y una dentro de `(dashboard)`) y 63 páginas.

## Clarifications

### Session 2026-11-25

- Q: ¿Qué puede hacer un `qa_operator`? → A: Leer, probar y operar. Las escrituras delicadas y la plataforma quedan para `admin` (Luis). Los tres roles son internos del equipo de Auphere; los de la consola de partners no se tocan.
- Q: ¿Un `viewer` lee también el contenido de las conversaciones con clientes finales? → A: Sí, todo, conversaciones incluidas (Luis).
- Q: ¿Cómo y dónde se arregla que la API no sepa qué operador actúa? → A: En esta spec, como fase 2, con una credencial propia del operador que la API verifica en cada llamada (Luis).
- Q: ¿Qué rol recibe por defecto un operador nuevo? → A: `viewer` (Luis).
- Q: ¿Qué entra en el envío a producción del 2026-11-26? → A: Solo la guarda del servidor (fase 1a). La interfaz y el rol por defecto (fase 1b) y la API (fase 2) van después (Luis).
- Q: ¿Cómo se revisan los roles de producción antes del envío? → A: Leyéndolos en producción, solo lectura (Luis). Hecho el 2026-11-25: ningún operador de producción pierde acceso con la matriz, así que no hay que ajustar ninguno.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Cada operador hace solo lo que permite su rol (Prioridad: P1)

Una persona del equipo con rol `viewer` entra en el panel, consulta clientes, partners y consumo, y no puede cambiar nada. Una con `qa_operator` hace lo que su rol permite y nada más. Un `admin` lo hace todo.

**Por qué esta prioridad**: es el hueco. Sin esto, el rol es una etiqueta.

**Prueba independiente**: con una sesión de cada rol, se invoca cada acción del inventario. Las que el rol no tiene se rechazan sin llegar a la API, y las que tiene se ejecutan.

**Escenarios de aceptación**:

1. **Dado** un operador `viewer`, **cuando** se invoca una acción de escritura (por ejemplo, recargar el saldo de un partner), **entonces** se rechaza, la API no recibe ninguna llamada y queda rastro con el operador y la acción.
2. **Dado** un operador `admin`, **cuando** invoca la misma acción, **entonces** se ejecuta como hoy.
3. **Dado** un operador `viewer`, **cuando** abre por enlace directo una página que solo sirve para escribir (el alta de un cliente), **entonces** ve la página de «no encontrada».
4. **Dado** un operador `qa_operator`, **cuando** pausa un cliente o cambia la configuración de un agente, **entonces** se ejecuta; **cuando** intenta recargar un saldo o rotar una clave, **entonces** se rechaza como en el escenario 1.

---

### Historia 2 — El `viewer` ve un panel de lectura, sin controles que no puede usar (Prioridad: P1)

El `viewer` recorre las mismas vistas que un `admin`, sin botones, menús ni formularios de acciones que su rol no tiene. No hay controles apagados ni avisos de «no tienes permiso»: la ausencia se diseña (§V).

**Por qué esta prioridad**: sin ella, la fase 1 deja un panel lleno de botones que fallan al pulsarlos.

**Prueba independiente**: con una sesión `viewer`, cada vista se pinta completa en sus estados (cargando, vacío, error, parcial e ideal) sin ningún control de escritura.

**Escenarios de aceptación**:

1. **Dado** un `viewer` en la ficha de un partner, **cuando** se pinta, **entonces** ve sus datos sin «Recargar», «Rotar clave» ni «Suplantar».
2. **Dado** un `viewer` y un cliente sin claves de API, **cuando** abre la sección de claves, **entonces** ve el vacío sin la acción de crear una.
3. **Dado** un `viewer`, **cuando** abre la navegación o ⌘K, **entonces** no aparecen las vistas que su rol no abre (por ejemplo, Playground QA o «Nuevo partner»).

---

### Historia 3 — Una acción nueva no puede olvidar su permiso (Prioridad: P2)

Quien añade una Server Action, una ruta o una página tiene que declarar qué permiso pide. Si no lo hace, la prueba falla y dice dónde.

**Por qué esta prioridad**: el hueco de la 078 nació de acciones que se olvidaron de la guarda. Sin esta prueba, el de esta spec vuelve con la siguiente acción.

**Prueba independiente**: se añade una acción sin permiso en una rama y la prueba falla nombrándola.

**Escenarios de aceptación**:

1. **Dado** un archivo `"use server"` con una función exportada que solo comprueba la sesión, **cuando** corre la prueba, **entonces** falla con el archivo y el nombre de la función.
2. **Dado** un permiso declarado que no existe en la matriz, **cuando** corre la prueba, **entonces** falla.

---

### Historia 4 — La API comprueba al operador ella misma (Prioridad: P3, fase 2)

La API sabe qué operador hace cada llamada del panel y aplica la misma matriz. Una acción del panel que declare mal su permiso, o una llamada que no venga de un operador activo, se rechaza en la API.

**Por qué esta prioridad**: es el arreglo de fondo, pero la fase 1 ya cierra el hueco para cualquier uso del panel. Es más trabajo: toca todas las rutas `/admin/*`.

**Prueba independiente**: se llama a una ruta de escritura `/admin/*` con el token de servicio y un operador `viewer`; la API contesta 403 y no escribe nada.

**Escenarios de aceptación**:

1. **Dado** un operador `viewer`, **cuando** el panel llama a una ruta de escritura, **entonces** la API contesta 403 y no cambia nada.
2. **Dado** un `admin`, **cuando** hace una escritura delicada, **entonces** la auditoría nombra a esa persona.

---

### Casos límite

- **Rol desconocido.** Si la API devuelve un rol que la matriz no conoce, el operador no tiene ningún permiso y va a `/sin-acceso`, como una cuenta deshabilitada. Falla cerrado.
- **Cambio de rol a mitad de sesión.** El panel resuelve la sesión en cada petición, así que el rol nuevo se aplica en la siguiente sin volver a entrar. Si tenía abierto un formulario que ya no puede enviar, al enviarlo la vista se vuelve a pintar sin el control y un aviso dice que la acción no se hizo. Es un estado de error después de un intento, no una explicación previa de lo que falta: §V no lo prohíbe.
- **Suplantación abierta.** Si un operador pierde el permiso de suplantar con una suplantación abierta, el panel deja de aplicarla en su siguiente petición.
- **Acción con dos efectos según su argumento.** `setTenantStatusAction` pausa, reanuda o archiva. Archivar es borrar (§IV: «borrar no existe: se archiva»), así que se separa.
- **Página de solo escritura por enlace directo.** Se pinta «no encontrada». No se explica qué permiso falta (§V).
- **El Playground QA de hoy.** Su página explica «Tu rol no abre el Playground». Se alinea con §V: la vista no aparece en el menú y el enlace directo da «no encontrada». Su guarda propia (`requireQAOperator`) desaparece en favor de la común: un flujo por concepto.
- **Entre la fase 1a y la 1b.** Durante unos días, un `qa_operator` o un `viewer` ve controles que su rol no permite. Si pulsa uno, la página se vuelve a pintar y avisa de que no se hizo nada (2.2). Es una excepción temporal a §V, decidida por Luis para que la guarda entre en el envío; la cierra la 1b.
- **Conflicto con el encargo.** El encargo admitía botones «deshabilitados con explicación». La constitución §V lo prohíbe y su única excepción (el catálogo del panel) no cubre esto. Gana la constitución: los controles se ocultan.
- **Lecturas que van por `POST` o `PUT`.** Las vistas previas (router, modelo por defecto) y las consultas dentro de archivos `"use server"` piden `read`. Lo que cuenta es el efecto, no el verbo.

## Requisitos *(obligatorio)*

### Requisito 1 — Una matriz rol → permisos

**Historia de usuario:** Como responsable del equipo, quiero decidir en un solo sitio qué puede hacer cada rol, para que el panel y la API digan lo mismo.

#### Criterios de aceptación

1. El sistema DEBE definir los nueve permisos del inventario: `read`, `qa`, `operate`, `money`, `credentials`, `impersonate`, `people`, `delete` y `platform`.
2. El sistema DEBE asignar los permisos según esta matriz:

   | Permiso | `admin` | `qa_operator` | `viewer` |
   |---|---|---|---|
   | `read` · lectura | sí | sí | sí |
   | `qa` · pruebas | sí | sí | no |
   | `operate` · operación | sí | sí | no |
   | `money`, `credentials`, `impersonate`, `people`, `delete` · escrituras delicadas | sí | no | no |
   | `platform` · plataforma | sí | no | no |

3. El `viewer` DEBE poder leer todo lo que el panel enseña, también el contenido de las conversaciones con clientes finales y su flujo en vivo.
4. IF el operador tiene un rol que la matriz no conoce THEN el sistema DEBE tratarlo como sin ningún permiso: lo lleva a `/sin-acceso` desde una página o una acción, y una ruta de `app/api` contesta 403.
5. El sistema DEBE tener **una** matriz. IF existe una copia en otro sitio (el panel y la API) THEN una prueba DEBE fallar en cuanto difieran.
6. WHEN se da de alta un operador sin decir su rol THEN el sistema DEBE darle `viewer`. Los operadores que ya existen conservan el suyo.

### Requisito 2 — Toda acción, ruta y página exige su permiso

**Historia de usuario:** Como responsable del equipo, quiero que el panel no obedezca a quien no tiene el permiso, para que el rol signifique algo.

#### Criterios de aceptación

1. WHEN se ejecuta una función exportada de un archivo `"use server"` de `apps/admin/src` THEN el sistema DEBE comprobar, como primera sentencia y con las mismas reglas que la spec 078 (1.1), que el operador está activo **y** tiene el permiso que declara esa función.
2. IF el operador no tiene el permiso THEN la acción NO DEBE llamar a la API; el operador DEBE quedarse en la misma página, que se vuelve a pintar con su rol vigente, y DEBE ver un aviso de que la acción no se hizo.
3. WHEN se rechaza una acción por permiso THEN el sistema DEBE dejar rastro con el operador, la acción y el permiso que faltaba, sin datos del cliente.
4. Cada acción DEBE declarar un solo permiso. IF el efecto de una acción depende de sus argumentos y cae en dos permisos THEN DEBE separarse en acciones distintas.
5. WHEN cualquier ruta del panel (un `route.ts` de `app`, esté o no en `app/api`) recibe una petición THEN DEBE comprobar su permiso antes de llamar a la API y contestar 403 si falta.
6. WHEN se pinta una página o un layout de servidor de `app/(dashboard)` THEN DEBE comprobar el permiso que declara (por ejemplo, `operate` para un alta o `qa` para el Playground).
7. IF un operador abre una página cuyo permiso no tiene THEN el sistema DEBE pintar «no encontrada», y NO DEBE explicar qué permiso le falta.
8. Las únicas funciones exentas DEBEN seguir siendo `loginAction` y `logoutAction`.
9. El Playground QA DEBE usar la misma comprobación que el resto, con el permiso `qa`, y NO DEBE quedar una guarda aparte.

### Requisito 3 — Lo que ve cada rol

**Historia de usuario:** Como operador con un rol limitado, quiero ver un panel que solo me ofrece lo que puedo hacer, para no tropezar con botones que fallan.

#### Criterios de aceptación

1. WHERE el operador no tiene el permiso de un control (botón, entrada de menú, formulario o acción de un vacío) EL panel NO DEBE pintarlo, ni apagado ni con explicación (§V).
2. WHEN una vista se queda sin acciones para el rol THEN DEBE pintarse completa en lectura, sin huecos donde iban los controles.
3. La navegación lateral y la paleta ⌘K DEBEN omitir las vistas cuyo permiso el rol no tiene.
4. El menú del operador DEBE seguir diciendo su rol. Es la única indicación del rol en el panel.
5. Las vistas de lectura DEBEN conservar sus estados de cargando, vacío, error y parcial. Un vacío NO DEBE ofrecer crear si el rol no puede.
6. IF un operador pierde `impersonate` con una suplantación abierta THEN el panel DEBE dejar de aplicarla en su siguiente petición.

### Requisito 4 — La prueba estructural obliga a declarar el permiso

**Historia de usuario:** Como quien añade una acción al panel, quiero que una prueba me pare si olvido su permiso, para que el hueco no vuelva.

#### Criterios de aceptación

1. WHEN alguien añade una función de Server Action, una ruta de `app/api` o una página sin declarar su permiso THEN una prueba DEBE fallar y nombrar el archivo y la función.
2. La comprobación sin permiso (la de la spec 078 a secas) NO DEBE bastar: el permiso es obligatorio y no hay valor por defecto.
3. La prueba DEBE barrer el código, no una lista de sitios conocidos, y DEBE ser la de la spec 078 ampliada, no una segunda.
4. WHEN una función declara un permiso que no está en la matriz THEN la prueba DEBE fallar.
5. Una prueba DEBE comprobar, rol por rol, que la matriz da lo que fija el criterio 1.2.

### Requisito 5 — El despliegue no deja a nadie fuera por sorpresa

**Historia de usuario:** Como responsable del equipo, quiero revisar el rol de cada operador antes de que el panel empiece a aplicarlo, para que nadie pierda su trabajo de un día para otro.

#### Criterios de aceptación

1. Antes de desplegar la fase 1 en un entorno, el equipo DEBE revisar el rol de cada operador activo de ese entorno y ajustarlo con el procedimiento que ya existe.
2. WHEN cambia el rol de un operador THEN el panel DEBE aplicarlo en su siguiente petición, sin cerrar la sesión.
3. La documentación viva (`docs/admin.md`, apartado «Quién puede operar») DEBE describir la matriz y cómo se declara un permiso, en el mismo cambio.

### Requisito 6 — La API conoce y comprueba al operador (fase 2)

**Historia de usuario:** Como responsable de la plataforma, quiero que la API decida con la misma matriz, para que un error del panel no baste para escribir.

#### Criterios de aceptación

1. WHEN la API recibe una llamada del panel a `/admin/*` (salvo el login, la sesión y el cierre de sesión) THEN DEBE saber qué operador la hace y comprobar, con la misma matriz, que su rol tiene el permiso de esa ruta; si no, DEBE contestar 403 sin efecto.
2. IF la llamada no identifica a un operador activo THEN la API DEBE rechazarla, también si es una lectura.
3. La API DEBE identificar al operador con una credencial propia de ese operador que ella misma verifica en cada llamada. El nombre que el panel afirme NO DEBE bastar. Es la Fase 2 de ADR-009: cierra tanto un error del panel como un token de servicio filtrado.
4. WHEN un operador hace una escritura THEN la auditoría DEBE nombrar a la persona, no al token (§IV).
5. WHEN alguien añade una ruta `/admin/*` sin declarar su permiso THEN una prueba de la API DEBE fallar y nombrarla, barriendo las rutas registradas.
6. Las rutas de QA de la API DEBEN comprobar el permiso `qa` con la matriz.
7. La API DEBE tener **una** forma de identificar al operador del panel. Las que conviven hoy (ninguna, opcional, obligatoria y obligatoria con la cuenta activa) DEBEN converger en ella.
8. IF una llamada a `/admin/*` llega solo con el token de servicio THEN la API DEBE rechazarla, salvo en las rutas que no actúan en nombre de un operador (el login y la resolución de la sesión, y las que el plan liste con su razón).

### Entidades clave

- **Operador**: una persona del equipo de Auphere con cuenta en el panel. Tiene un rol y un estado (activa o deshabilitada). No pertenece a ningún tenant; vive en la identidad de operadores de la API (ADR-034).
- **Permiso**: una familia de efectos (leer, probar, operar, dinero, claves, suplantar, acceso de personas, borrar, plataforma). Cada acción, ruta o página declara uno.
- **Matriz**: rol → lista de permisos. Una sola.

## Criterios de éxito *(obligatorio)*

- **CE-001**: con una sesión `viewer`, ninguna acción que no sea de lectura cambia nada ni llega a la API; con una `qa_operator`, ninguna delicada ni de plataforma. Según el inventario del 2026-11-25, son 119 y 73; tras separar archivar de pausar, 120 y 74.
- **CE-002**: una acción, ruta o página nueva sin permiso declarado no se puede fusionar: la prueba la detecta siempre.
- **CE-003**: un `viewer` recorre las vistas de lectura sin ver ningún control que no pueda usar.
- **CE-004**: un cambio de rol surte efecto en la siguiente acción del operador, sin volver a entrar.
- **CE-005**: el día del despliegue, ningún operador pierde un acceso que el equipo no haya decidido quitarle.
- **CE-006** (fase 2): la API no acepta ninguna escritura del panel sin un operador activo con el permiso de esa ruta.

## Fuera de alcance

- **Gestionar operadores desde el panel** (alta, cambio de rol, deshabilitar). Sigue con el script de la API; es otra spec.
- **Roles nuevos o roles por partner** (un operador limitado a ciertos partners). Esta spec aplica los tres que existen.
- **Doble confirmación o volver a pedir la contraseña** antes de una escritura delicada.
- **Un flujo de conversación ya abierto** cuando cambia el rol: sigue vivo hasta cerrarse, como en la 078.
- **La consola de partners**, que tiene su propia matriz.
- **El resto de hallazgos** de la revisión de seguridad del 2026-11-22.

## Supuestos

- Los roles siguen siendo tres, y el inventario del 2026-11-25 cubre todo lo que el panel ejecuta.
- El panel sigue resolviendo la sesión en cada petición, así que siempre aplica el rol vigente.
- Cambiar el rol de un operador sigue siendo una operación del equipo con el script de alta, fuera del panel.
- La sesión que la API devuelve al panel ya trae el rol. Dónde vive la matriz única (criterio 1.5) lo decide el plan.
