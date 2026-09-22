# Especificación: El teammate sabe quién es, qué día es y qué puede hacer de verdad

**Rama**: `015-el-teammate-sabe-quien-es` · **Creada**: 2026-09-22 · **Estado**: Borrador

**Entrada**: evaluación `.specify/assessments/teammate-sabe-quien-es/`, cerrada
con `go` el 2026-09-22. `decision.md` es el texto canónico y sus seis decisiones
(D-A a D-F) no se re-discuten aquí.

---

## Encabezado Auphere

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`0`** — API de consola. No hay frontera nueva: ni puerto, ni ruta, ni credencial. Cambia lo que el prompt dice y de dónde sale, y se añade una columna de texto |
| **Garantías de aislamiento tocadas** | Ninguna se debilita. **La 2 (whitelist exhaustiva) se refuerza**: `unknown_tool` deja de nombrar las 44 herramientas del catálogo entero y nombra solo las del teammate, que es retirar una fuga de superficie existente |
| **Nota de KB que la justifica** | `[[research/2026-09-22-que-sabe-un-teammate-de-si-mismo]]` en `/Users/lmatos/Work/Auphere/nexus/`, y `[[research/2026-09-19-auditoria-clase-mundial/02-teammates-y-companion]]` §7 |
| **Qué se mide** | **Nada nuevo.** No se añade ninguna llamada al modelo ni ninguna herramienta de pago. El único efecto sobre el consumo es de entrada: unos cientos de tokens por turno, acotados por el Requisito 3 |

> **§II — por qué no hay que ampliar nada.** Todo lo que esta spec entrega cabe
> dentro de la superficie que ya está abierta: los mensajes del turno ya se
> construyen en el servidor, el catálogo ya se calcula ahí, y la tabla
> `teammates` ya existe con sus políticas. **Esta spec no abre superficie: usa
> mejor la que hay**, y en un punto la reduce.

---

## Lo que esta spec NO entrega, dicho al principio

**Un teammate seguirá sin ser un trabajador para el cliente del partner.**

De sus **44 herramientas, 40 administran la consola de Auphere**. Fuera de
`shell_local` no tiene ficheros, ni web, ni conectores. Esta spec hace que sepa
quién es, qué día es y qué tiene de verdad — **no le da nada nuevo que hacer**.

Lo que lo convierte en trabajador es el toolset, que es superficie `3a`, tiene su
propia evaluación abierta (`teammate-que-trabaja-en-la-terminal`) y tomará otro
número.

*Está escrito aquí, al principio y no al final, porque quien espere otra cosa es
mejor que lo descubra leyendo la spec y no al recibirla.*

---

## Escenarios de usuario y pruebas

### Historia 1 — Lo que el teammate dice tener es lo que tiene (Prioridad: P1)

Una persona del equipo de un partner crea un teammate al que solo le da
**publicar**. Le pregunta qué puede hacer.

Hoy, el teammate contesta que tiene herramientas de lectura sobre la consola y
que puede consultar clientes, agentes, políticas, canales, consumo y auditoría.
**Tiene dos herramientas y ninguna es de lectura.** Y si la persona le pide un
dato, el teammate se calla, porque una regla del prompt le prohíbe afirmar lo que
no ha leído — sin decirle que es que no puede leer.

Después de esta historia, el mismo teammate contesta qué tiene, nombra lo que le
falta, y dice qué interruptor lo daría.

**Por qué esta prioridad**: es la mentira que el sistema cuenta en cada turno, y
la que hace que los interruptores sean una trampa. No necesita migración.

**Prueba independiente**: se crea un teammate por cada combinación de
interruptores y se le pregunta qué puede hacer. Lo que conteste se compara con lo
que el servidor le entregó. Entregable sola: sin nada más de esta spec, los
interruptores dejan de mentir.

**Escenarios de aceptación**:

1. **Dado** un teammate con solo el interruptor de publicar, **cuando** se le
   pregunta qué puede hacer, **entonces** nombra proponer publicaciones y
   confirmar, y **no** nombra ninguna lectura.
2. **Dado** ese mismo teammate, **cuando** la persona le pide un dato de la
   consola, **entonces** dice que no tiene lecturas y qué haría falta para
   dárselas, en vez de callarse.
3. **Dado** un teammate con máquina vinculada y presente, **cuando** se le
   pregunta qué puede hacer, **entonces** nombra que puede ejecutar en esa
   máquina — hoy no lo nombra nunca.
4. **Dado** cualquier teammate, **cuando** el modelo se inventa el nombre de una
   herramienta, **entonces** la respuesta nombra **solo las suyas**.
5. **Dado** un hilo con cuarenta mensajes, **cuando** llega un turno nuevo,
   **entonces** el teammate sigue respondiendo con su nombre y su oficio, no con
   los del Companion.

---

### Historia 2 — El desajuste no puede volver (Prioridad: P1)

Alguien del equipo de Auphere añade una herramienta al catálogo, o mueve una de
familia. Hoy eso no rompe nada: el prompt sigue diciendo lo que decía, y la
separación entre lo prometido y lo entregado crece en silencio.

Ha pasado **tres veces**. Dos se corrigieron a mano; la tercera entró el
2026-09-20 con `shell_local` y pasó inadvertida hasta que alguien fue a buscarla.

Después de esta historia, ese cambio pone algo en rojo antes de fusionarse.

**Por qué esta prioridad**: es el tramo **más barato** y el único que impide que
el trabajo de la Historia 1 se deshaga solo. Va inmediatamente después porque sin
él la Historia 1 se degrada con el primer catálogo nuevo.

**Prueba independiente**: se añade una herramienta de mentira al catálogo en un
test y se comprueba que la puerta falla. Si no falla, la puerta no vigila.

**Escenarios de aceptación**:

1. **Dado** el catálogo actual, **cuando** se ejecuta la puerta, **entonces**
   pasa.
2. **Dado** un cambio que añade una familia de herramientas sin reflejarla en lo
   que el teammate lee, **cuando** se ejecuta la puerta, **entonces** falla y
   nombra la familia.
3. **Dado** un cambio que devuelve una afirmación de capacidad al prompt
   compartido, **cuando** se ejecuta la puerta, **entonces** falla y cita la
   frase.
4. **Dado** un cambio que mueve una herramienta de una familia a otra,
   **cuando** se ejecuta la puerta, **entonces** falla.

---

### Historia 3 — El teammate sabe cuándo está (Prioridad: P2)

Una persona le pide a su teammate algo con fecha: «¿esto está vencido?», «déjalo
listo para el viernes», «¿cuánto llevamos este mes?».

Hoy el teammate no recibe la fecha por ningún sitio, así que la deduce de lo que
aprendió al entrenarse. El agente de canal de esta misma plataforma **sí** la
recibe, con su zona horaria y con la instrucción de no deducirla nunca.

**Por qué esta prioridad**: va después de las dos primeras porque añade una
verdad, no quita una mentira. Y porque necesita un sitio donde ponerse, que es lo
que crea la Historia 1.

**Prueba independiente**: se le pregunta qué día es y si algo con fecha pasada
está vencido.

**Escenarios de aceptación**:

1. **Dado** un turno cualquiera, **cuando** se le pregunta la fecha,
   **entonces** la dice, y es la de hoy.
2. **Dado** un turno con la zona horaria de la persona, **cuando** resuelve «el
   viernes», **entonces** usa esa zona y no otra.
3. **Dado** un turno cuya zona horaria llega vacía o mal escrita, **cuando** se
   construye el turno, **entonces** se usa UTC **y se dice que es UTC**, en vez
   de fingir que se sabe la local.
4. **Dado** un teammate cuya máquina está ausente, **cuando** se le pide algo que
   la necesita, **entonces** lo sabe antes de intentarlo.

---

### Historia 4 — Dos teammates con los mismos permisos son dos agentes distintos (Prioridad: P3)

Un partner tiene dos teammates. A uno lo quiere seco y directo, para revisar
configuración. Al otro lo quiere paciente y explicativo, porque lo usa alguien
que está aprendiendo.

Hoy los dos son el mismo agente: lo único que los distingue son ochenta
caracteres de «oficio» dentro de una frase de cuatro.

Después de esta historia, el partner escribe cómo trabaja cada uno, y cada uno
trabaja así.

**Por qué esta prioridad**: es la única con migración y la única que toca §III.
Va la última **a propósito**: si algo se suelta de esta spec, que sea esto, y que
las tres primeras ya estén entregadas.

**Prueba independiente**: se le escriben instrucciones a un teammate y se
comprueba que las sigue; se le escriben contrarias a otro con los mismos
permisos y se comprueba que se comportan distinto.

**Escenarios de aceptación**:

1. **Dado** un teammate con instrucciones propias, **cuando** responde,
   **entonces** las sigue.
2. **Dado** un teammate sin instrucciones propias, **cuando** responde,
   **entonces** se comporta como hoy — nadie pierde nada por no rellenarlo.
3. **Dado** un teammate cuyas instrucciones piden algo que sus permisos no
   permiten, **cuando** lo intenta, **entonces** **los permisos ganan**: las
   instrucciones no amplían el catálogo.
4. **Dado** un partner que cambia las instrucciones de un teammate, **cuando**
   guarda, **entonces** queda asiento de quién lo cambió y cuándo, como con
   cualquier otro campo del teammate.

---

### Casos límite

- **¿Qué ve el teammate que no tiene ninguna herramienta?** Es un caso real, no
  teórico: solo-publicar en modo consulta entrega **cero**. Tiene que saber que
  no tiene ninguna y **por qué**, y poder decírselo a la persona. Callarse es lo
  que hace hoy.
- **¿Y si le preguntan por un colega?** Hablar con otro teammate no existe, y es
  una decisión escrita (spec 003). El teammate tiene que **poder decir que no
  puede**, no quedarse en blanco ni inventarse una forma.
- **¿Y si el partner escribe instrucciones larguísimas?** Hay un tope, se dice
  cuál en el formulario, y pasarse no rompe el turno.
- **¿Y si el partner escribe instrucciones que contradicen lo prohibido
  globalmente?** Lo prohibido globalmente gana, y el teammate lo dice.
- **¿Qué pasa con los teammates que ya existen?** Nadie tiene que volver a
  configurarlos. Sin instrucciones propias se comportan como hoy, con lo demás
  ya arreglado.
- **La ausencia se diseña (§V)**: en el formulario del teammate, el campo de
  instrucciones vacío **no se pinta como un error ni como algo pendiente**. Es un
  campo opcional y así se lee.

---

## Requisitos

### Requisito 1 — La identidad del teammate llega antes que nada

**Historia de usuario:** Como persona que configuró un teammate, quiero que sea
ese teammate desde el primer momento del turno, para que no me conteste como si
fuera otro.

#### Criterios de aceptación

1. El sistema DEBE entregar la identidad del teammate —su nombre, su oficio y,
   cuando existan, sus instrucciones propias— en una **posición fija del turno**
   que NO dependa de cuántos mensajes lleve la conversación.
2. WHEN el hilo crece THEN la posición de la identidad NO DEBE alejarse del
   principio. *(Hoy la identidad viaja detrás de toda la historia: en un hilo de
   cuarenta mensajes llega en la posición 42.)*
3. El texto compartido con el Companion DEBE seguir siendo **idéntico byte a
   byte entre turnos y entre teammates**, y el sistema NO DEBE interpolar en él
   ningún dato que varíe.
4. WHERE hay identidad de teammate EL sistema DEBE evitar que el coste de
   cachear el texto compartido se multiplique por el número de teammates.
   *(Ver Requisito 3: esto es una consecuencia medible, no una preferencia.)*
5. WHEN no hay teammate —la persona habla con el Companion— THEN el turno DEBE
   construirse exactamente como hoy.

### Requisito 2 — Lo que dice tener es lo que tiene

**Historia de usuario:** Como persona que usa un teammate, quiero que me diga la
verdad sobre lo que puede hacer, para no pedirle cosas que no puede ni dejar de
pedirle las que sí.

#### Criterios de aceptación

1. El sistema DEBE derivar lo que el teammate puede hacer **del mismo cálculo que
   decide qué herramientas recibe**, y NO DEBE mantener esa descripción escrita a
   mano en otro sitio.
2. El texto compartido con el Companion NO DEBE afirmar que el teammate tiene
   ninguna familia de herramientas.
3. WHEN el teammate no tiene una familia de herramientas THEN el sistema DEBE
   decírselo con su motivo, y DEBE decirle **qué lo cambiaría**.
4. WHERE el teammate puede ejecutar en una máquina EL sistema DEBE nombrárselo.
   *(Hoy no se nombra nunca, ni cuando la tiene.)*
5. IF el teammate no tiene **ninguna** herramienta THEN el sistema DEBE decírselo
   explícitamente y DEBE permitirle explicárselo a la persona, y NO DEBE dejarle
   una instrucción que equivalga a guardar silencio.
6. WHEN el modelo nombra una herramienta que no existe THEN la respuesta DEBE
   enumerar **solo las del teammate**, y NO DEBE enumerar el catálogo completo de
   la plataforma.
7. WHEN se le pregunta por hablar con otro teammate THEN el sistema DEBE
   permitirle decir que eso no existe, y NO DEBE ofrecer ninguna forma de
   hacerlo.

### Requisito 3 — El coste de esto es acotado y está medido

**Historia de usuario:** Como responsable del producto, quiero saber qué cuesta
que el teammate sepa quién es, para que no se convierta en una factura
inesperada.

#### Criterios de aceptación

1. El sistema DEBE mantener el texto compartido con el Companion cacheado **una
   sola vez para todos los teammates**, y NO DEBE escribir una copia por
   teammate.
2. El sistema DEBE dejar comprobable, sin llamar al proveedor, **dónde caen los
   puntos de corte del caché** y qué queda dentro de cada tramo.
3. WHEN se añade la identidad y el entorno THEN lo que se paga de más por turno
   DEBE ser solo el tamaño de esos dos bloques.
4. El sistema NO DEBE añadir ninguna llamada al modelo ni ninguna herramienta que
   se cobre.

### Requisito 4 — La puerta que impide que vuelvan a separarse

**Historia de usuario:** Como quien mantiene el catálogo, quiero que separar lo
prometido de lo entregado ponga algo en rojo, para no enterarme meses después.

#### Criterios de aceptación

1. El sistema DEBE comprobar que el texto compartido **no promete capacidades**.
2. El sistema DEBE recorrer **todas** las combinaciones de interruptores y modos,
   y comprobar que lo que el teammate lee sobre sí mismo coincide con lo que el
   servidor le entrega.
3. IF se añade una herramienta al catálogo sin que aparezca en lo que el teammate
   lee THEN la comprobación DEBE fallar y DEBE nombrar qué falta.
4. IF se mueve una herramienta de una familia a otra THEN la comprobación DEBE
   fallar.
5. La comprobación NO DEBE basarse en **buscar nombres de herramienta citados en
   el texto**. *(Comprobado: el texto cita tres nombres y los tres existen, así
   que una comprobación así nacería en verde sin vigilar nada.)*
6. La comprobación DEBE fallar con el código de hoy si se le quita el arreglo —
   es decir, DEBE verse en rojo antes de implementar.

### Requisito 5 — El teammate sabe cuándo está

**Historia de usuario:** Como persona que le pide cosas con fecha, quiero que mi
teammate sepa qué día es, para que «el viernes» signifique el viernes.

#### Criterios de aceptación

1. El sistema DEBE entregar en cada turno la fecha, la hora y la zona horaria, en
   una posición **cercana al mensaje de la persona**.
2. El sistema DEBE instruir al teammate a usar esa fecha para resolver cualquier
   referencia relativa y a **no deducirla nunca de su propio conocimiento**.
3. La zona horaria DEBE ser la de **la persona que escribe**.
4. WHERE el turno trata de un cliente concreto EL sistema DEBE poder nombrar
   también la zona de ese cliente, sin sustituir a la de la persona.
5. IF la zona horaria llega vacía, mal escrita o desconocida THEN el sistema DEBE
   usar UTC, DEBE **decir que está usando UTC**, y NO DEBE interrumpir el turno.
6. El sistema DEBE decir en el turno si la máquina del teammate está presente.

### Requisito 6 — Las instrucciones que escribe el partner

**Historia de usuario:** Como partner, quiero escribir cómo trabaja cada uno de
mis teammates, para que dos con los mismos permisos no sean el mismo agente.

#### Criterios de aceptación

1. El sistema DEBE permitir al partner escribir instrucciones propias para cada
   teammate, y DEBE entregárselas al teammate junto con su identidad.
2. Las instrucciones DEBEN ser opcionales. WHEN un teammate no las tiene THEN
   DEBE comportarse como antes de esta spec.
3. IF las instrucciones piden algo fuera de los permisos del teammate THEN los
   permisos DEBEN ganar, y las instrucciones NO DEBEN ampliar el catálogo de
   herramientas.
4. IF las instrucciones contradicen lo que está globalmente prohibido THEN lo
   prohibido DEBE ganar.
5. El sistema DEBE acotar el tamaño de las instrucciones, DEBE decir cuál es el
   tope **antes** de que alguien lo rebase, y NO DEBE truncarlas en silencio.
6. WHEN alguien cambia las instrucciones de un teammate THEN DEBE quedar asiento
   con quién y cuándo, como con cualquier otro campo del teammate.
7. Los teammates que ya existen NO DEBEN necesitar ninguna intervención.

### Requisito 7 — La frontera entre lo que se obedece y lo que se lee

**Historia de usuario:** Como responsable de la seguridad del producto, quiero
que esté escrito qué texto es instrucción y qué texto es dato, para que nadie
tenga que deducirlo del código.

> **Este requisito es la decisión D-B, escrita.** No cambia comportamiento en su
> primer criterio: **lo formaliza**. Hoy el campo de oficio ya mete ochenta
> caracteres escritos por el partner dentro de un mensaje de sistema sin que
> ninguna spec lo haya dicho nunca.
>
> **Y no pide enmendar la constitución.** La frontera se declara aquí y se
> documenta en `docs/desktop-teammates.md`; el porqué está razonado en el
> Constitution Check del plan. Legislar §III sobre un solo caso es peor que
> declararlo: si una segunda spec necesita la misma distinción, entonces la
> enmienda se escribe con dos ejemplos en vez de con uno.

#### Criterios de aceptación

1. El sistema DEBE tratar **lo que el partner configura** —el oficio y las
   instrucciones propias— como **instrucción a propósito**, dirigida al
   teammate y destinada a obedecerse, y DEBE dejarlo escrito como decisión, no
   como efecto del código.
2. El sistema DEBE seguir tratando **lo que el teammate lee** —ficheros, salidas
   de programas, contexto de pantalla, resultados de herramienta— como **dato,
   nunca como instrucción**, con el mismo vallado que ya usa hoy.
3. La documentación DEBE decir en voz alta **contra quién NO protege** esta
   frontera: no protege del partner comprometido. Quien controle una cuenta con
   permiso para editar teammates puede escribirles instrucciones, igual que hoy
   puede reescribir entero el prompt del agente de su cliente.
4. El sistema NO DEBE mezclar los dos tipos de texto en un mismo bloque sin
   distinguirlos.

### Entidades clave

- **Teammate** *(existe)*: gana **un campo de texto opcional** con las
  instrucciones que escribe el partner. Pertenece al partner y la RLS lo alcanza
  por su columna de partner, igual que el resto de la fila. No gana ninguna otra
  columna.
- **Identidad del turno** *(no se persiste)*: lo que el teammate lee sobre sí
  mismo en cada turno. Se **deriva** de la fila del teammate y del catálogo
  calculado; no se guarda en ningún sitio y por eso no puede quedarse vieja.
- **Entorno del turno** *(no se persiste)*: fecha, hora, zona y presencia de
  máquina. Se calcula en el momento.

---

## Criterios de éxito

- **CE-001**: un partner crea dos teammates con los mismos permisos y distintas
  instrucciones, les hace la misma pregunta, y **las respuestas son distintas de
  una forma que reconoce como lo que pidió**.
- **CE-002**: un partner le pregunta a un teammate qué puede hacer, y **todo lo
  que contesta es cierto**: nada que no tenga, nada que tenga y no nombre.
- **CE-003**: un teammate sin ninguna herramienta **explica por qué no puede
  ayudar**, en vez de no contestar.
- **CE-004**: un teammate contesta correctamente qué día es y si algo con fecha
  pasada está vencido, en la zona horaria de quien pregunta.
- **CE-005**: cuando el modelo se equivoca de nombre de herramienta, **lo que se
  le enseña son solo las del teammate**.
- **CE-006**: un cambio que separe otra vez lo prometido de lo entregado **no
  llega a fusionarse**.
- **CE-007**: el coste por turno crece **solo lo que ocupan los dos bloques
  nuevos**, y el texto compartido se sigue cacheando una vez para todos.

---

## Fuera de alcance

- **El toolset de trabajo** —leer, escribir, listar y buscar ficheros; web;
  conectores— porque es superficie `3a` y tiene evaluación propia abierta
  (`teammate-que-trabaja-en-la-terminal`). Con él sale, explícitamente,
  **convertir al teammate en trabajador para el cliente del partner**.
- **La unidad de ejecución** (un comando por vez frente a una sesión viva) —
  misma evaluación, y su pregunta exige medir antes de diseñar.
- **Hablar con un colega** — la spec 003 lo dejó fuera por escrito y su Requisito
  3.6 **reserva el tipo de nota `handoff`** para no tener que migrar. Lo que sí
  entra aquí es que el teammate **sepa decir que no puede** (R2.7).
- **Reescribir el texto compartido con el Companion** — solo se le quitan las
  afirmaciones de capacidad. Son 89 líneas con nueve decisiones anotadas; tocarlo
  «de paso» es cómo se pierden.
- **El rechazo por herramienta fuera de catálogo y el recorte por modo** — están
  bien, tienen su razón escrita y son el respaldo de la garantía 2 frente a un
  fallo que la industria sí tiene documentado. No se tocan.
- **Subagentes** — decisión escrita en cuatro sitios del código y por la misma
  razón.
- **Memoria de equipo** — la KB la lista junto a «instrucciones propias», y es
  otra cosa: instrucciones son lo que el partner escribe una vez; memoria es lo
  que el sistema acumula. Juntarlas metería una spec de persistencia dentro de
  una de identidad.
- **Cambiar quién puede editar teammates** — los permisos de hoy siguen.

---

## Supuestos

- **La aplicación puede decir en qué zona horaria está la persona.** Es un dato
  que el navegador conoce sin preguntar. Ni el partner ni la persona tienen hoy
  una zona guardada; el único que la tiene es el cliente final.
- **Las combinaciones de configuración son pocas y enumerables** —cinco
  interruptores, dos modos y la presencia de máquina— así que la puerta del
  Requisito 4 puede recorrerlas todas en lugar de muestrear.
- **El partner es confianza declarada para su propio texto.** Ya escribe entero
  el prompt del agente que atiende a sus clientes finales, que es más poder que
  esto. Queda escrito en R7 con sus límites, incluido contra quién no protege.
- **Nadie tiene que reconfigurar nada.** Las instrucciones son opcionales y su
  ausencia es el comportamiento de hoy.
- **El tope de las instrucciones** se fija al planificar, con un número
  defendible; lo que esta spec exige es que exista, se anuncie y no trunque en
  silencio.
- **El margen del caché.** El texto compartido tiene tamaño de sobra sobre el
  mínimo cacheable incluso después de quitarle las afirmaciones de capacidad.
  Está estimado por tamaño de texto y sin medir con el contador del proveedor; si
  al planificar el margen apretara, el Requisito 3 es el que manda.
