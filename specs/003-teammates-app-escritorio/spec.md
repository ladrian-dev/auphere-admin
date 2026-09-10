# Especificación: los teammates viven en la aplicación de escritorio

**Rama**: `003-teammates-app-escritorio` · **Creada**: 2026-09-10 · **Estado**: Borrador

**Entrada**: traspaso de
[`.specify/assessments/teammates-en-la-app/decision.md`](../../.specify/assessments/teammates-en-la-app/decision.md)
— veredicto **go** del 2026-09-10 con la **Opción A** y las tres decisiones de
esa puerta: la beta 1 se construye en la app y la consola no tiene teammates;
las aprobaciones de teammate esperan a la tarea; la política de ejecución local
tiene tres capas y gana la más restrictiva. Con los tres supuestos que Luis
confirmó: crear teammate desde la app; Pendientes muestra solo lo de los
teammates; el techo del administrador vive en la página de equipo de la consola.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`0`** —API de la consola, a través del BFF con la sesión de la persona— y **`3a`** —ejecutar en la máquina por el puente de la 001—. **No abre superficie nueva.** La aplicación abre un renderer propio con IPC: es superficie *de la aplicación*, no del agente, y el Requisito 12 la acota |
| **Garantías de aislamiento tocadas** | **1. Postgres RLS** (roster por partner; hilo con dos ejes, teammate y persona) · **2. Tool whitelist por agente** (de frente: cada teammate recibe un catálogo propio, subconjunto del catálogo del companion, y el modelo no ve más) · **3. Env aislado del agente** (la ejecución local sigue por la 001; se le añade una política por persona que **solo puede restringir**) · **6. Log + trace tagging** (crear, cambiar y archivar un teammate, y cada decisión de política, con la persona) |
| **Nota de KB que la justifica** | `[[10-decisiones]]` decisiones 2, 4, 7–12 y las dos nuevas (13: política en tres capas; 14: la aprobación espera a la tarea); `[[14-mvp-y-fases]]` §2 **enmendado**: la beta 1 vive en la app. Diseño de referencia `Auphere Web v3`, leído entero (research §2.1) |
| **Qué se mide** | **Nada nuevo.** Los teammates gastan el consumo de la membresía por el medidor que ya existe. El Requisito 9 lo convierte en prohibición: ni un segundo contador, ni un segundo camino al modelo |

> **Por qué no abre superficie (§II):** el hilo corre en la plataforma —donde ya
> corren el Companion, sus aprobaciones y su medidor— y lo que toca la máquina
> pasa por el puente que la 001 abrió y la 002 hizo del partner. La aplicación
> **pinta** y **pregunta**; no ejecuta nada que no ejecutara ya, y no habla con
> la plataforma con ninguna credencial que no tuviera ya (la sesión de la
> persona, en el proceso principal).

> **Esta spec supera dos requisitos anteriores y enmienda uno.** Supera
> **001-R15.1** y **002-R12.1** («una sola superficie propia»): la aplicación tiene
> desde aquí dos, la barra y la pantalla de operar, y conserva el espíritu —no
> duplica pantallas de la consola. Enmienda **§IV** de forma acotada
> (Requisito 6): la aprobación que un teammate pide no caduca por reloj propio
> sino con la tarea que la pidió. Todo lo demás de §IV se conserva.

## Lo que hereda del diseño *Auphere Web v3*, y lo que esta spec le corrige

El diseño dibuja **esta** pantalla. Lo que la 002 decía de él («es la consola
reescrita como aplicación de mensajería») era la lectura con la premisa vieja;
con la premisa nueva, el diseño es la aplicación, con dos correcciones: dice
«web» donde ahora es «escritorio», y promete «el mismo hilo en web, escritorio y
iPhone» donde ahora hay escritorio hoy y móvil después.

| Del diseño, literal | Dónde aterriza aquí |
|---|---|
| Las tres columnas: roster a la izquierda (`AGENTS`: nombre, oficio, modelo, `busy`, `unread`, última cosa hecha), hilo en medio, panel a la derecha | Requisito 1 (roster) · Requisito 3 (hilo) · Requisito 11 (panel de entorno) |
| Los seis estados del hilo (`normal · cargando · vacío · error · reconectando · parcial`) y el copy que separa pantalla de trabajo | Requisito 3.4: estados nombrados, y el `parcial` es el que más importa |
| `pausaPorTope`: *«Trabajo en pausa: alcanzaste el tope. Los hilos y las confirmaciones siguen vivos. El tope se sube desde la consola.»* | Requisito 9.3: la pausa se pinta como estado, y el tope se sube en la consola |
| **Pendientes**: bandeja con `urgent`, `flagged` («riesgo alto», «no bloquea») y la prueba (*«Probada · 4 de 4 en verde»*, *«Esta acción no admite prueba»*, *«Se puede probar y no se probó»*); estado vacío *«Cuando un teammate necesite permiso… aparece aquí. Nada se ejecuta antes.»* | Requisito 5 (la bandeja) · Requisito 6 (la aprobación que espera) · Requisito 7 (el nivel) |
| Los tres niveles de aviso: Crítico / Aviso / Informativo, como política | Requisito 7 |
| **Crear teammate**: nombre, oficio (`jobList` de ocho), `brain` con nota y coste, permisos como cinco interruptores (`read · write · spend · publish · contact`) | Requisito 2. El `jobList` es semilla; los interruptores se traducen a catálogo y política |
| **Cuenta**: uso del mes, equipo, roles (`Owner · Admin · Operador · Lectura` con lo que cada uno puede en consola y en companion), «Abrir la consola» | Requisito 8. Los roles son los cinco del código, no los cuatro del diseño |
| El handoff entre teammates como nota legible del hilo (*«Le pidió a Nilo que lo probara antes de proponerlo · 4 mensajes»*) | Fuera de alcance (agente↔agente, `[[14-mvp-y-fases]]` §2.4); el Requisito 3.6 reserva la forma para que no haya que migrar |
| Panel de entorno `navegador / archivos / terminal` y la lista de ficheros | Requisito 11: `archivos` y `terminal` existen (002 y 001); `navegador` se pinta como ausencia diseñada |
| **Plugins** con «Pedirla» | Fuera de alcance como pantalla; la petición existe en la plataforma (`support.request_capability`) y el hilo la usa |
| **Tomar control** | Fuera de alcance (3b) |
| «Borrar no existe» (`[[00-revision-del-diseno-v3]]` §3.9); la auditoría nombra a la persona (§5.6) | Requisitos 2.6 y 13 |
| Los dos fallos de contraste del sistema (§7) | Requisito 12.5 |

## Escenarios de usuario y pruebas *(obligatorio)*

### El recorrido completo, en una página

Una persona de un partner abre la aplicación que ya emparejó (002). Deja de ver
la consola: ve **su equipo**. A la izquierda, los teammates del partner con su
oficio y lo último que hicieron; en medio, el hilo con el que eligió —**su**
hilo, que nadie más de su partner ve—; a la derecha, en qué máquina y en qué
carpeta trabaja ese teammate, y cuánto consumo queda este mes.

Le pide algo a Sofía. Sofía revisa los canales del cliente, encuentra el
problema, lo prueba y **propone** un cambio: la tarjeta enseña qué, dónde, la
prueba que hizo y cómo se deshace. La persona cierra el portátil. Sofía no se
para: lo que puede hacer sola lo hace; lo que no, lo deja **esperándote**. Al
día siguiente, la aplicación abre con un aviso del sistema —«Sofía espera una
decisión»— y **Pendientes** lista lo que espera, con su nivel. Aprueba desde la
bandeja; la tarjeta del hilo se marca sola.

Nilo pide ejecutar algo en la máquina. Es la primera vez: la tarjeta enseña el
ejecutable, los argumentos y el directorio del cliente, y ofrece **una vez /
siempre / nunca**. La persona elige *siempre* para ese ejecutable. El
administrador del partner había puesto el techo en *preguntar siempre*: la
preferencia de la persona se guarda, se enseña como acotada, y se sigue
preguntando. Gana la más restrictiva, y la pantalla lo dice.

Crea un teammate nuevo: nombre, oficio, modelo, permisos. Aparece en el roster
de todo el partner; los hilos, no: cada persona estrena el suyo. En **Cuenta**
ve el uso del mes con el mismo número que la consola, y un botón para abrir la
consola cuando toque administrar.

### Historia 1 — Mi equipo, y mi hilo con cada uno (Prioridad: P1)

Como persona de un partner, quiero abrir la aplicación y ver los teammates del
partner y hablar con cada uno en un hilo que es mío, para operar el día a día
sin pasar por la consola.

**Por qué esta prioridad**: es la pantalla entera. Sin roster e hilo no hay
producto que probar.

**Prueba independiente**: con dos teammates sembrados y dos personas del mismo
partner, cada una abre la app, ve los dos teammates, escribe a uno, y ninguna ve
el hilo de la otra. El teammate responde usando las herramientas de su oficio y
**solo** ésas.

**Escenarios de aceptación**:

1. **Dado** un partner con teammates, **cuando** una persona con membresía abre
   la aplicación emparejada, **entonces** ve el roster completo del partner con
   oficio, modelo y estado de cada teammate, y su propio hilo con el que elija.
2. **Dado** dos personas del mismo partner, **cuando** ambas escriben al mismo
   teammate, **entonces** cada una ve solo su hilo, y el teammate no mezcla
   contextos.
3. **Dado** un teammate de finanzas, **cuando** el modelo recibe su catálogo,
   **entonces** no contiene ninguna herramienta de desarrollo — comprobado en el
   catálogo, no en la pantalla.
4. **Dado** un hilo abierto, **cuando** la plataforma no responde,
   **entonces** la pantalla dice que el trabajo sigue en la plataforma y que lo
   que falla es la pantalla, y se recupera sola al volver la conexión.

---

### Historia 2 — El trabajo sobrevive a cerrar la aplicación (Prioridad: P1)

Como persona de un partner, quiero encargar algo, cerrar la aplicación y volver,
para que el teammate haya seguido y lo que necesite de mí me espere.

**Por qué esta prioridad**: es la promesa de la categoría («termina la tarea
mientras te vas a por un café»).

**Prueba independiente**: encargar una tarea de varios pasos con una aprobación
en medio, cerrar la app, esperar, abrir: la tarea llegó hasta la aprobación y
está «esperándote»; aprobar la reanuda hasta el final.

**Escenarios de aceptación**:

1. **Dado** una tarea en marcha, **cuando** la persona cierra la aplicación,
   **entonces** la tarea continúa en la plataforma sin la aplicación.
2. **Dado** una tarea que necesita una decisión y la aplicación cerrada,
   **cuando** pasa el tiempo, **entonces** la aprobación **no** caduca: la tarea
   queda en `esperándote` mientras la tarea viva.
3. **Dado** una aprobación esperando, **cuando** la persona abre la aplicación,
   **entonces** recibe un aviso del sistema operativo si el nivel lo merece, y
   Pendientes la lista con su nivel, su prueba y cómo se deshace.
4. **Dado** la misma aprobación visible en el hilo y en Pendientes, **cuando** la
   persona decide en uno, **entonces** el otro se actualiza sin recargar.

---

### Historia 3 — Ejecutar en mi máquina, con mi política y el techo del partner (Prioridad: P1)

Como persona de un partner, quiero decidir cuánto me pregunta un teammate antes
de ejecutar en mi máquina, y como administrador quiero poner un techo a esa
decisión para todo el equipo.

**Por qué esta prioridad**: es lo que hace de la aplicación algo distinto de la
consola, y es donde está el riesgo.

**Prueba independiente**: con lista blanca, techo y preferencia en tres
combinaciones, comprobar qué se pregunta y qué no; y que ningún ajuste de la
aplicación amplía lo que la lista blanca permite.

**Escenarios de aceptación**:

1. **Dado** un ejecutable en la lista blanca del cliente y sin preferencia,
   **cuando** un teammate lo pide, **entonces** la tarjeta enseña ejecutable,
   argumentos y directorio, y ofrece *una vez / siempre / nunca*.
2. **Dado** una preferencia *siempre* de la persona y un techo *preguntar
   siempre* del partner, **cuando** el teammate lo pide, **entonces** se
   pregunta, y la pantalla dice que el techo del partner manda.
3. **Dado** una preferencia *nunca*, **cuando** el teammate lo pide,
   **entonces** se deniega sin preguntar, el hilo lo dice como estado y queda
   auditado.
4. **Dado** un ejecutable **fuera** de la lista blanca, **cuando** cualquier
   preferencia o techo lo permitiría, **entonces** se deniega igual: la
   aplicación no puede añadir nada a la lista.
5. **Dado** la máquina ausente, **cuando** el teammate necesita ejecutar,
   **entonces** el hilo lo pinta como espera diseñada, no como error.

---

### Historia 4 — Crear un teammate desde la aplicación (Prioridad: P2)

Como persona de un partner, quiero crear un teammate con nombre, oficio,
modelo y permisos, para que aparezca en el roster de todos.

**Por qué esta prioridad**: sin él, el roster es semilla; con él, es del
partner. Va después de la 1 porque un roster sembrado ya deja probar el resto.

**Prueba independiente**: crear uno, verlo aparecer para otra persona del
partner, comprobar que su catálogo es el de su oficio y sus permisos.

**Escenarios de aceptación**:

1. **Dado** el formulario, **cuando** la persona crea un teammate,
   **entonces** aparece en el roster de todo el partner con oficio, modelo y
   política, y queda auditado con la persona.
2. **Dado** un teammate existente, **cuando** se cambia su oficio o sus
   permisos, **entonces** el catálogo cambia en el siguiente turno y los hilos
   existentes lo ven como nota.
3. **Dado** un teammate, **cuando** se archiva, **entonces** desaparece del
   roster, sus hilos quedan legibles y nada se borra.

---

### Historia 5 — Cuánto me queda, el mismo número (Prioridad: P2)

Como persona de un partner, quiero ver en la aplicación cuánto consumo queda y
qué teammate lo gasta, con el mismo número que la consola.

**Escenarios de aceptación**:

1. **Dado** consumo del mes, **cuando** la persona abre Cuenta, **entonces** ve
   el mismo número que la consola en el mismo instante.
2. **Dado** el tope alcanzado, **cuando** un teammate está en marcha,
   **entonces** el hilo pasa a pausa por tope, las confirmaciones siguen vivas y
   la pantalla dice dónde se sube el tope.

---

### Casos límite

- La persona pierde la membresía con la app abierta: la pantalla pasa a
  «sin sesión» (002), el hilo deja de responder como estado, nada se pierde.
- Dos teammates con el mismo nombre en el mismo partner: se permite; el
  identificador es propio, la pantalla desambigua con el oficio.
- Un teammate archivado con una aprobación esperando: la aprobación se cierra
  como «no aplicada por archivo» y se audita.
- La misma persona con dos máquinas: cada hilo enseña en qué máquina trabaja
  ese teammate; la preferencia de ejecución local es **por persona**, no por
  máquina.
- El techo del partner baja después de que una persona guardara *siempre*: la
  preferencia se conserva, se muestra como acotada, se aplica el techo.
- Una aprobación de un cambio en un cliente que la persona no puede operar por
  rol: la tarjeta lo dice y no ofrece aprobar.
- La plataforma cae a mitad de un *stream*: el hilo pasa a `reconectando` y
  retoma desde el último evento visto; nada se duplica.
- Texto largo: nombres de teammate de 40 caracteres, rutas de 96 sin espacios,
  una tarjeta con veinte filas de cambios.

## Requisitos *(obligatorio)*

### Requisito 1 — El roster es del partner, y se lee por persona

**Historia de usuario:** Como persona de un partner, quiero ver los mismos
teammates que mis compañeros, con lo que cada uno es y hace.

#### Criterios de aceptación

1. El sistema DEBE mantener un roster de teammates **por partner**, con nombre,
   oficio, modelo, catálogo de herramientas, política de permiso y estado
   (activo / archivado), aislado por partner (garantía 1).
2. WHEN una persona con membresía abre la aplicación THEN el sistema DEBE
   devolverle el roster completo de su partner y nada de otro partner.
3. Cada entrada del roster DEBE llevar el estado operativo derivado del hilo de
   **esa persona** con ese teammate: `en marcha`, `esperándote`, `en pausa por
   tope`, `en espera`; y lo último hecho.
4. El roster NO DEBE distinguir `personal` de `team` (decisión 8).
5. WHERE el partner no tiene teammates THEN el sistema DEBE ofrecer crear el
   primero, con la semilla de oficios del diseño, como estado vacío diseñado.

### Requisito 2 — Crear, cambiar y archivar un teammate desde la aplicación

**Historia de usuario:** Como persona de un partner, quiero crear un teammate
con formulario y que quede como decidimos.

#### Criterios de aceptación

1. La aplicación DEBE ofrecer crear un teammate con: nombre, oficio (semilla de
   ocho, editable), modelo (de la lista que la plataforma ofrece, con su nota y
   coste), y permisos como interruptores que se traducen a catálogo y política.
2. El sistema DEBE permitir crear teammates a **cualquier** persona con
   permiso de usar teammates (decisión 7: sin roles de agente).
3. WHEN se crea o cambia un teammate THEN el catálogo del modelo DEBE ser un
   **subconjunto** del catálogo del companion (garantía 2): la aplicación no
   puede añadir una herramienta que la plataforma no publique.
4. WHEN se cambia el oficio o los permisos THEN el siguiente turno de cada hilo
   DEBE usar el catálogo nuevo, y el hilo DEBE anotarlo como nota.
5. La conversación como forma de crear un teammate NO entra en esta spec; el
   objeto que produce el formulario DEBE ser el mismo que produciría aquélla.
6. Un teammate DEBE poder archivarse y NO DEBE poder borrarse; sus hilos DEBEN
   seguir legibles.

### Requisito 3 — El hilo es de la persona, corre en la plataforma y no miente

**Historia de usuario:** Como persona de un partner, quiero hablar con un
teammate en un hilo que es mío, que sigue sin mí y que me dice la verdad de su
estado.

#### Criterios de aceptación

1. Cada hilo DEBE pertenecer a **un teammate y una persona**; ninguna otra
   persona del partner DEBE poder leerlo (garantía 1, decisión 9).
2. El hilo DEBE correr en la plataforma: cerrar la aplicación NO DEBE detener
   una tarea, y abrirla DEBE retomar desde el último evento visto sin duplicar.
3. WHEN un teammate necesita la máquina THEN el trabajo DEBE pasar por el
   puente de la 001/002 con el directorio del cliente vinculado; el hilo NO
   DEBE tener otro camino a la máquina.
4. El hilo DEBE tener estos estados nombrados y ninguno pintado como error:
   `normal · cargando · vacío · error · reconectando · parcial`, más los
   operativos `esperándote · en pausa por tope · máquina ausente`.
5. WHILE la máquina está ausente THEN el hilo DEBE seguir para todo lo que no
   la necesita y DEBE pintar la espera como ausencia diseñada.
6. Los mensajes DEBEN admitir las formas del diseño (`decir · preguntar · nota`)
   y las notas los tipos `check · archivo · handoff · en vivo · ticket`, aunque
   `handoff` no se produzca todavía.
7. El hilo DEBE ser infinito por ahora (decisión 12) y cargarse por páginas.

### Requisito 4 — El catálogo por teammate es lo que el modelo ve

**Historia de usuario:** Como partner, quiero que un teammate de finanzas no
pueda ni intentar una herramienta de desarrollo.

#### Criterios de aceptación

1. WHEN un turno de un teammate empieza THEN el catálogo que recibe el modelo
   DEBE ser exactamente el del teammate, y NO DEBE contener nada fuera de él
   (garantía 2).
2. El catálogo por teammate DEBE ser un subconjunto del catálogo del companion,
   y las herramientas locales DEBEN entrar solo si el teammate tiene permiso de
   ejecutar y hay máquina conectada (001-R15.4 / 002-R12.3, heredados).
3. Un test de aislamiento DEBE comprobar el catálogo **que recibe el modelo**,
   no la pantalla.

### Requisito 5 — Pendientes: lo que los teammates esperan de mí

**Historia de usuario:** Como persona de un partner, quiero una bandeja con todo
lo que mis teammates esperan de mí, y decidir desde ahí.

#### Criterios de aceptación

1. La aplicación DEBE listar en Pendientes toda aprobación de **teammate** que
   espera a **esta persona**, con teammate, cliente, qué, nivel, prueba (si la
   hay), cómo se deshace y desde cuándo.
2. Pendientes NO DEBE mostrar lo que el Companion de la consola web propone
   (supuesto confirmado): son superficies distintas.
3. WHEN la persona decide en Pendientes THEN el hilo DEBE reflejarlo sin
   recargar, y viceversa, en menos de dos segundos.
4. WHERE una aprobación toca un cliente que la persona no puede operar THEN la
   tarjeta DEBE decirlo y NO DEBE ofrecer decidir.
5. El estado vacío DEBE explicar cuándo aparece algo aquí y que nada se
   ejecuta antes.

### Requisito 6 — La aprobación de un teammate espera a la tarea *(enmienda acotada de §IV)*

**Historia de usuario:** Como persona de un partner, quiero que lo que un
teammate me pide me espere, no que caduque porque tardé en abrir la aplicación.

#### Criterios de aceptación

1. Una aprobación pedida por un teammate NO DEBE caducar por un reloj propio;
   DEBE cerrarse solo cuando la **tarea** que la pidió termina, se cancela, se
   archiva su teammate o alcanza su tope de vida.
2. Mientras espera, la tarea DEBE estar en `esperándote` y el hilo y el roster
   DEBEN decirlo.
3. Lo demás de §IV se conserva: durable, idempotente, una sola decisión, 409 a
   la segunda, la auditoría nombra a la persona.
4. Las aprobaciones del Companion de la consola NO cambian: siguen caducando
   como hoy.

### Requisito 7 — Tres niveles de aviso, como política

#### Criterios de aceptación

1. Toda aprobación y toda nota que espera a la persona DEBE llevar un nivel:
   `crítico · aviso · informativo`.
2. WHEN la aplicación está abierta y llega algo `crítico` THEN el sistema DEBE
   avisar por el sistema operativo; `aviso` DEBE marcar la bandeja; `informativo`
   NO DEBE interrumpir.
3. WHEN la aplicación se abre con cosas esperando THEN DEBE avisar una vez del
   resumen, no una vez por cosa.
4. El sistema NO DEBE enviar correo.
5. La persona DEBE poder bajar el ruido (silenciar `aviso`) pero NO subirlo
   por encima de `crítico` para nadie más.

### Requisito 8 — Cuenta: el uso, el equipo y la puerta a la consola

#### Criterios de aceptación

1. Cuenta DEBE mostrar el consumo del mes y lo que queda, **con el mismo
   medidor y el mismo número** que la consola, y por teammate.
2. Cuenta DEBE mostrar el equipo con sus roles (los cinco del código), sin
   editarlos: administrar el equipo es de la consola.
3. Cuenta DEBE ofrecer «Abrir la consola» y «Cerrar sesión» (el de la consola,
   002-R11.1).
4. Cuenta DEBE mostrar la preferencia de ejecución local de la persona y el
   techo del partner que la acota.

### Requisito 9 — Un solo medidor, un solo camino al modelo

#### Criterios de aceptación

1. Los teammates DEBEN gastar el consumo de la membresía del partner por el
   medidor existente; esta spec NO DEBE añadir contador.
2. Ninguna llamada al modelo de un teammate DEBE salir por un camino que no
   pase por el medidor.
3. WHEN el tope se alcanza THEN el hilo DEBE pasar a `en pausa por tope` con
   las confirmaciones vivas, y la pantalla DEBE decir que el tope se sube en la
   consola.

### Requisito 10 — La política de ejecución local: tres capas, gana la más restrictiva

**Historia de usuario:** Como persona quiero decidir cuánto se me pregunta;
como administrador quiero acotarlo para todos.

#### Criterios de aceptación

1. La ejecución local DEBE decidirse por tres capas en este orden: **lista
   blanca de ejecutables por cliente** (consola, sin cambios) → **techo por
   partner** (consola, página de equipo: `preguntar siempre · permitir siempre ·
   nunca`) → **preferencia por persona** (aplicación, mismos tres valores, por
   ejecutable o global).
2. La regla DEBE ser: se ejecuta solo lo que la lista blanca permite; entre techo
   y preferencia gana la más restrictiva; por defecto `preguntar siempre`.
3. La preferencia DEBE poder darse desde la tarjeta (*una vez / siempre /
   nunca*) y desde Cuenta; `una vez` NO DEBE guardarse.
4. WHEN la preferencia queda acotada por el techo THEN la pantalla DEBE decirlo
   donde se ve la preferencia y en la tarjeta.
5. La tarjeta de ejecución DEBE enseñar ejecutable, argumentos y directorio;
   NO DEBE enseñar la salida del comando (§III).
6. Ningún ajuste de la aplicación DEBE poder **ampliar** lo que la lista blanca
   o el techo permiten (garantía 3). Test de aislamiento.
7. Cada decisión (`una vez`, cambio de preferencia, denegación por `nunca`,
   denegación por lista) DEBE auditarse con la persona.

### Requisito 11 — El panel de entorno dice dónde trabaja el teammate

#### Criterios de aceptación

1. El panel DEBE mostrar, por hilo, en qué máquina y en qué directorio del
   cliente trabaja el teammate, y la presencia de la máquina (002).
2. `archivos` DEBE listar lo que el teammate tocó en esta tarea, como
   referencia, sin abrir contenido en la aplicación.
3. `navegador` DEBE pintarse como ausencia diseñada («todavía no»), no como
   botón apagado ni error.
4. WHERE no hay máquina emparejada o el cliente no tiene directorio THEN el panel
   DEBE llevar a la puesta en marcha de la 002, no repetirla.

### Requisito 12 — La segunda superficie propia, y lo que no puede tener

**Historia de usuario:** Como partner, quiero que la aplicación sea una
aplicación de escritorio, y como responsable de seguridad quiero que su pantalla
nueva no tenga nada que no deba.

#### Criterios de aceptación

1. La pantalla de operar DEBE ser propia de la aplicación (renderizada por ella),
   con partición propia, sin acceso al sistema de ficheros ni al proceso, y con
   un canal hacia el proceso principal **enumerado**: cada mensaje del canal
   DEBE estar declarado con su forma, y un test DEBE recorrer la lista.
2. Ningún mensaje del canal DEBE devolver a la pantalla una sesión, cookie,
   credencial de máquina ni token. Test de aislamiento.
3. La vista de la consola DEBE seguir sin canal con la aplicación (002-R14,
   heredado) y DEBE seguir disponible para operar clientes y administrar.
4. La aplicación DEBE comportarse como aplicación de escritorio: una sola
   instancia, icono en la bandeja con lo que espera, ventana que recuerda su
   sitio, atajo para invocarla, aviso del sistema, actualización firmada
   (spec 004).
5. La pantalla DEBE cumplir WCAG 2.2 AA, usar los tokens del sistema, tener los
   cinco estados de cada componente, y NO DEBE repetir los dos fallos de
   contraste de `[[00-revision-del-diseno-v3]]` §7.
6. La pantalla NO DEBE reimplementar ninguna página de la consola; donde algo es
   administrar, DEBE enlazar a la consola.

### Requisito 13 — Todo lo que cambia un teammate o una política queda auditado

#### Criterios de aceptación

1. Crear, cambiar, archivar un teammate; cambiar el techo del partner; cambiar
   la preferencia de una persona; cada decisión de ejecución local: cada uno
   DEBE dejar una fila con la persona, nunca el teammate como actor
   (`[[00-revision-del-diseno-v3]]` §5.6).
2. Las filas NO DEBEN contener cuerpos de mensaje ni salida de comandos.

### Requisito 14 — Nada de esto debilita lo que 001 y 002 garantizan

#### Criterios de aceptación

1. Los tests de aislamiento de la 001 y la 002 DEBEN seguir en verde.
2. El ambiente del agente NO DEBE ganar ningún acceso nuevo: la máquina sigue
   ejecutando lo mismo, bajo la misma lista, con la misma contención.
3. La consola NO DEBE mostrar ni usar teammates.

### Entidades clave

- **Teammate**: del partner; nombre, oficio, modelo, catálogo, política de
  permiso, estado; auditado por persona. Nunca actor de auditoría.
- **Hilo de teammate**: de un teammate y una persona; estados; eventos con
  orden; páginas.
- **Tarea**: unidad de trabajo que sobrevive a la aplicación; tope de vida;
  estados `en marcha · esperándote · en pausa por tope · terminada · cancelada`.
- **Aprobación de teammate**: durable, con nivel, prueba opcional, cómo se
  deshace; espera a la tarea.
- **Política de ejecución local**: techo por partner + preferencia por persona
  (global o por ejecutable); se resuelve con la lista blanca del cliente.
- **Nivel de aviso**: `crítico · aviso · informativo`.
- **Catálogo por teammate**: subconjunto del catálogo del companion, más las
  herramientas locales cuando corresponde.

## Criterios de éxito *(obligatorio)*

- **CE-001**: en una máquina limpia, una persona instala, entra, se empareja,
  declara una carpeta y un teammate lee y escribe dentro de ella — **cero
  instalaciones adicionales** (con la spec 004).
- **CE-002**: el 100 % de las tareas encargadas sobreviven a cerrar la
  aplicación: terminan o quedan `esperándote`.
- **CE-003**: decidir en un sitio actualiza el otro en menos de dos segundos,
  sin recargar, en el 100 % de los casos.
- **CE-004**: un teammate sin permiso **no recibe** la herramienta: comprobado
  en el catálogo que ve el modelo; test de aislamiento en verde.
- **CE-005**: dos personas del mismo partner con el mismo teammate: cero
  lecturas cruzadas; test de aislamiento en verde.
- **CE-006**: contadores de consumo en el producto: exactamente uno; el número
  de Cuenta y el de la consola coinciden.
- **CE-007**: canales de la pantalla que devuelven sesión, cookie o token: cero;
  test que enumera los canales en verde.
- **CE-008**: ningún ajuste de la aplicación amplía la lista blanca ni el techo;
  test de aislamiento en verde.
- **CE-009**: una persona ajena al equipo encarga, aprueba y sabe cuánto le queda
  en menos de cinco minutos sin que nadie le explique nada.
- **CE-010**: la pantalla pasa WCAG 2.2 AA y las cuatro auditorías (estados,
  a11y, responsive, tokens) sin 🔴.
- **CE-011**: los tests de aislamiento de 001 y 002 siguen en verde.

## Fuera de alcance

- **Empaquetar la edición y el loop local del sustrato** (subagentes,
  `session-control`, `select_crew`, TaskRunner): fase siguiente, receta en
  research §3.1 y concept T-6.
- **Firma, notarización, actualización y contención en Windows**: spec 004,
  condición de CE-001.
- **Móvil (beta 3), navegador embebido (beta 4), VM (beta 5), tomar control
  (3b, beta 6).** Nada aquí lo impide; el hilo en plataforma lo permite.
- **Rutinas, voz, chat de grupo, agente↔agente y el handoff real**
  (`[[14-mvp-y-fases]]` §2.4). La forma de nota `handoff` se reserva.
- **Crear teammates por conversación** (decisión 7, después).
- **Aviso por correo** (descartado por Luis).
- **Plugins como pantalla** y **Tomar control**.
- **Teammates en la consola web** y rehacer la consola.
- **Cambiar la lista blanca, la contención, el puente o el emparejamiento.**
- **Memoria e instrucciones de equipo, búsqueda en contenido**
  (`[[00-revision-del-diseno-v3]]` §5.7, §5.8): vendrán con el sustrato.

## Supuestos

- La sesión de la persona en la vista de la consola es la única identidad de
  persona de la aplicación (002-R2); la pantalla nueva la usa a través del
  proceso principal, nunca directamente.
- El loop del Companion es el loop de los teammates: se le añade el eje
  teammate, no se escribe otro.
- Los oficios del diseño son semilla; el partner puede escribir el suyo.
- La lista de modelos, con nota y coste, la publica la plataforma; la
  aplicación no la conoce.
- Un teammate archivado conserva su historial; nada se borra.
- Las preferencias de ejecución local se guardan en la plataforma (viajan con la
  persona, no con la máquina).
- El techo del partner se administra desde la página de equipo de la consola, y
  solo owner y admin pueden cambiarlo.
- Los componentes del Companion se comparten entre consola y aplicación por un
  paquete común, para que las dos pantallas no diverjan.
