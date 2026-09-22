# Concept: que el turno diga lo que el partner configuró

- **Slug**: teammate-sabe-quien-es
- **Created**: 2026-09-22
- **Recommended option**: **B — el mensaje propio del teammate, con puerta**

---

## Las tres decisiones de diseño, con su precio

Van primero porque las tres opciones de abajo se diferencian en **cómo las
resuelven**, no en qué construyen.

### D-1 · Dónde va cada cosa en la lista de mensajes

Hoy: `SYSTEM_PROMPT` → historia → contexto de página → conocimiento (con la
identidad pegada delante) → turno.

| Camino | Qué gana | Qué cuesta |
|---|---|---|
| **Identidad dentro del prefijo** | Posición 1, imbatible | **Descartable, y con razón**: el prefijo es `SYSTEM_PROMPT` literal, sin una sola interpolación, y `test_companion_graph.py:49` lo congela (`"{" not in SYSTEM_PROMPT`). Interpolar el nombre daría **un prefijo distinto por teammate** — tantas entradas de caché como teammates, ninguna reutilizada. El caché de Anthropic es encaje de prefijo: un byte distinto en la posición 1 lo tira entero |
| **Dos prefijos, uno «Companion» y otro «teammate»** | Cada uno se llama como es, desde el token 1 | Dos textos de 7 KB que se copian mutuamente y **divergen**. Este repositorio ya tiene el precedente exacto de lo que pasa con un vocabulario escrito dos veces: costó una acción fantasma en la spec 012, con el aviso puesto por escrito tres ficheros más allá |
| **Segundo mensaje de sistema justo después del prefijo, antes de la historia** | La identidad pasa de la posición «historia+2» a la **posición 2 fija**, y deja de empeorar con el hilo. Un prefijo, un caché | Los mensajes de sistema a mitad de conversación ya existen aquí (`page_context_message`), así que no es mecanismo nuevo. Cuesta ≈300-600 caracteres por turno de entrada no cacheada |
| **Entorno en el mismo mensaje que la identidad** | Un solo mensaje nuevo | La fecha es lo más fresco y quiere ir al final; la identidad quiere ir al principio. Juntarlas obliga a elegir mal para una de las dos |

**Lo que esto deja visto**: son **dos** mensajes, no uno. Identidad en la
posición 2; entorno justo antes del turno, que es donde ya vive lo fresco.

### D-2 · Cómo se enumera lo que tiene de verdad

| Camino | Coste por turno | Mantenimiento |
|---|---|---|
| **Prosa incondicional** (hoy) | 0 | **Falso en 3 de 5 combinaciones de interruptores**, y silencia `shell_local` |
| **Quitar la prosa y no decir nada** | −400 caracteres del prefijo | El modelo ve los *schemas* de sus herramientas igualmente, así que no queda ciego. Pero pierde el mapa: «tienes lecturas **sobre la consola**» es contexto que el schema no da |
| **Derivarlo del catálogo real, por familia** | ≈150-300 caracteres | Una lista de familias (lecturas / propuestas / aplicar / máquina) con lo que hay y lo que no, generada de `for_teammate`. **No se mantiene a mano: sale del mismo sitio que el catálogo** |
| **Enumerar los 44 nombres** | ≈900 caracteres | Duplica el schema que el modelo ya recibe. Caro y redundante |

**Lo que esto deja visto**: derivar por familia. Y el prefijo deja de afirmar —
pasa a decir *«lo que puedes hacer te lo dice tu propio bloque»*, que es una
afirmación que nunca caduca.

### D-3 · La puerta, pensada al revés

El research demostró que el lint por nombres **da cero hallazgos hoy**: el prompt
nombra tres herramientas y las tres existen. Un test así nacería verde y
vigilando nada — y esta sesión acaba de pagar el precio de uno de ésos.

Así que la forma sale de escribir primero **qué cambio futuro tiene que ponerlo
rojo**:

| Cambio futuro | ¿Lo caza un lint de nombres? | ¿Lo caza la puerta propuesta? |
|---|---|---|
| Alguien añade una herramienta al catálogo y no toca el prompt *(pasó el 2026-09-20 con `shell_local`)* | **No** | **Sí** — la familia nueva no tiene frase |
| Alguien mueve una herramienta de familia *(pasó: `console.apply` salió de `write`)* | No | **Sí** |
| Alguien vuelve a poner prosa incondicional en el prefijo | No | **Sí** — el prefijo no puede afirmar capacidades |
| Alguien renombra una herramienta que el prompt cita | Sí | Sí |

**Lo que esto deja visto**: la puerta tiene **dos mitades**. Una afirma que el
prefijo **no promete capacidades** (barrido de texto sobre `SYSTEM_PROMPT`). La
otra recorre **las combinaciones de interruptores** —son pocas y enumerables— y
exige que el bloque generado y `for_teammate` coincidan. La segunda es la que
falla sola cuando alguien toca el catálogo.

### D-4 · La zona horaria — y aquí el código ya contestó

Comprobado en los modelos:

- `tenant.timezone` **existe** (`db/models/tenant.py:66`, `String(64)`, default
  `UTC`) — es la del **cliente del partner**.
- **El partner no tiene zona horaria.** Ninguna columna.
- **La persona tampoco**: `ConsoleAccount` tiene `locale` (`es`/`en`,
  `console_identity.py:58`) y nada más.
- El contexto de página lleva cuatro claves y ninguna es la zona
  (`PAGE_CONTEXT_KEYS = {route, client_ref, tab, selection}`).

| Camino | Qué defiende | Qué cuesta |
|---|---|---|
| **La del `tenant` del contexto de página** | Es la única que existe hoy, y es la correcta cuando se habla *de un cliente* | **No siempre hay cliente en el contexto.** Sin él no hay respuesta, y un teammate mirando el roster no está «en» ningún cliente |
| **Que la aplicación mande la suya** (`Intl.DateTimeFormat().resolvedOptions().timeZone`) | Es la zona de **la persona que escribe**, que es de quien son el «mañana» y el «el viernes». Sin migración | Añade una clave al esquema del contexto de página, que hoy es cerrado y está vallado. Es dato de cliente: entra como dato, no como verdad |
| **Columna nueva en el partner** | Estable y explícita | Migración y una pregunta más en el alta, para algo que el navegador ya sabe |
| **UTC y decirlo** | Cero trabajo, nunca miente | Inútil para «el viernes» |

**Lo que esto deja visto**: la zona de la persona, mandada por la aplicación,
con la del `tenant` como matiz cuando el turno va de un cliente. Y el repliegue
ya está escrito en el otro agente: zona malformada → UTC **con marca visible**,
nunca fingir que se sabe (`pipeline.py:657-662`).

### D-5 · Instrucciones propias y §III — la puerta ya está abierta

El dato incómodo del research: **`job` ya mete 80 caracteres escritos por el
partner dentro de un `role: "system"`, sin vallar**, mientras
`page_context_message` sí valla con `fence_only` **y tiene escrito por qué**:

> «Que llegue con `role: system` lo hace **MÁS** peligroso, no menos — un texto
> con forma de instrucción en un mensaje de sistema es exactamente lo que no
> puede pasar.»

| Camino | Qué defiende, y contra quién | Qué cuesta |
|---|---|---|
| **Vallar como el contexto de página** | Contra un partner comprometido, contra una cuenta robada, y contra el partner que copia y pega algo de internet sin leerlo | Un texto vallado **se lee como dato**, y aquí el partner quiere que se obedezca. Vallarlo entero lo haría inservible |
| **Acotar el tamaño** (p. ej. 2 KB) | Contra nada en concreto: un prompt inyectado cabe en 200 caracteres | Barato, y honesto solo si se dice que es coste, no seguridad |
| **Declarar que el texto del partner es confianza** | Es coherente con lo que ya pasa: el partner **ya** escribe el prompt entero del agente de su cliente, que es mucho más poder que esto | No defiende del **partner comprometido**. Hay que escribirlo, no asumirlo |
| **Confianza declarada + vallar lo que viene de fuera** | Separa dos cosas que hoy están mezcladas: lo que **el partner escribe** (instrucción, a propósito) y lo que **el teammate lee** de ficheros y salidas (dato, siempre) | Obliga a decir la frontera por escrito en la spec, que es exactamente lo que §III pide |

**Lo que esto deja visto**: la cuarta. El principio no dice «nada es
instrucción»: dice que **lo leído** es dato. El texto del partner no es leído por
el agente — es configuración, igual que el prompt del agente de canal que ese
mismo partner ya escribe entero. Lo que hay que hacer es **decirlo en un
requisito** en vez de dejarlo implícito, como está hoy con `job`.

---

## Options

### Option A — Solo el bloque de entorno

- **Sketch**: el teammate recibe un segundo mensaje de sistema justo antes del
  turno con fecha, hora, zona y si su máquina está conectada. Nada más cambia:
  la identidad sigue donde está, el prefijo sigue prometiendo lo que promete.
- **Appetite**: **small** (días).
- **Trade-offs**: gana la métrica 3 (fechas) entera y parte de la 2. **Sacrifica
  las otras cinco.** Es copiar `_now_note` a otro agente, con el modelo ya
  probado en producción.
- **Rabbit holes**: la zona horaria (D-4). Si se intenta resolver «bien» —columna
  en el partner, pregunta en el alta— un tramo de días se convierte en uno de
  semanas por una decisión que el navegador ya contesta gratis.

### Option B — El mensaje propio del teammate, con puerta

- **Sketch**: el teammate gana **dos** mensajes de sistema. Uno en la posición 2,
  inmediatamente después del prefijo: su nombre, su oficio, **sus instrucciones
  propias** (campo nuevo que escribe el partner) y **lo que puede hacer de
  verdad**, derivado de su catálogo por familias, con lo que le falta y por qué.
  Otro justo antes del turno: fecha, hora, zona, máquina. El prefijo deja de
  afirmar capacidades. `unknown_tool` pasa a nombrar solo las suyas. Y una puerta
  de dos mitades (D-3) impide que vuelvan a separarse.
- **Appetite**: **medium** (semanas), y se entrega en cuatro tramos sueltos:

  | Tramo | Qué cierra | Suelto vale porque |
  |---|---|---|
  | 1 · **El sitio y la verdad** | Métricas 2 y 4 | Un teammate deja de prometer lo que no tiene y dice qué le falta. Sin migración |
  | 2 · **La puerta** | Métrica 6 | El tramo 1 sin puerta se vuelve a separar; con puerta, no. Es el más barato y el que más dura |
  | 3 · **El entorno** | Métrica 3 | Es la Option A, ya con sitio donde ponerse |
  | 4 · **Instrucciones propias** | Métrica 1 | El único con migración, y el único que toca §III. Va el último **a propósito**: si algo se suelta, que sea esto |

- **Trade-offs**: gana las seis métricas. Sacrifica: sigue sin convertir al
  teammate en trabajador —40 de 44 herramientas administran la consola— y **quien
  espere eso se va a llevar un chasco**. Hay que decirlo al entregar.
- **Rabbit holes**:
  1. **El campo de instrucciones y §III.** Es la discusión larga (D-5) y está en
     el último tramo por eso. Si se mete en el primero, bloquea todo lo demás.
  2. **Reescribir el prefijo «de paso».** Son 7 KB con nueve decisiones anotadas
     y un test que lo congela. Aquí solo hay que **quitarle las afirmaciones de
     capacidad**, no mejorarlo.
  3. **Querer que la puerta cace todo.** El research ya demostró que la versión
     obvia no caza nada; la tentación opuesta —un test que enumere las 44— es
     igual de mala por el otro lado.

### Option C — Esperar a la evaluación de la terminal y hacerlo todo junto

- **Sketch**: no se construye nada ahora. Se cierra primero
  `teammate-que-trabaja-en-la-terminal` —que decide si la unidad es un comando o
  una sesión viva y si entran ficheros, web y conectores— y se hace una sola spec
  con el toolset y la identidad a la vez.
- **Appetite**: **large** (meses), y **bloqueada**: esa evaluación tiene solo
  `intake`, y su pregunta central exige medir antes de diseñar.
- **Trade-offs**: gana coherencia —un solo cambio del prompt en vez de dos—.
  Sacrifica meses, y **empeora la deuda mientras tanto**: cada herramienta que
  añada el toolset agranda la distancia entre lo prometido y lo entregado, que es
  el problema que aquí se resuelve.
- **Rabbit holes**: la evaluación hermana puede decidir *kill* sobre la sesión
  viva, y entonces esto habrá esperado meses por nada.

---

## Recommendation

**Option B**, y los cuatro tramos en ese orden.

El motivo no es que gane las seis métricas — es el orden. **Los tramos 1 y 2 son
los que quitan una mentira**, y una mentira que el sistema cuenta cada turno se
paga con intereses: la Option C la deja creciendo durante meses, y la Option A la
deja intacta mientras añade una verdad al lado.

Y hay un argumento de coste puro: el tramo 2, la puerta, es el **más barato de
los cuatro** y es el único que impide que el trabajo se deshaga solo. Este
repositorio ha visto el desajuste prompt↔catálogo **tres veces**, y la tercera
pasó inadvertida hasta que alguien fue a buscarla.

La Option C se rechaza por una razón concreta y no por prisa: **su bloqueo no
depende de esta evaluación**. Aquella pregunta —comando o sesión viva— exige
medir dónde está el coste real antes de diseñar, y eso es trabajo que nadie ha
hecho todavía. Atar esto a aquello no acelera aquello.

---

## Out of Scope (for the recommended option)

- **El toolset de trabajo**: ficheros, web, conectores. Superficie `3a`, y con
  evaluación propia abierta. Con él sale, explícitamente, **convertir al teammate
  en un trabajador para el cliente del partner**.
- **La unidad de ejecución** (comando suelto vs. PTY/tmux).
- **Hablar con un colega.** La spec 003 lo decidió por escrito y reservó el tipo
  de nota `handoff`. Lo que sí entra es que el teammate **sepa decir que no
  puede**.
- **Reescribir `SYSTEM_PROMPT`.** Solo se le quitan las afirmaciones de
  capacidad.
- **Tocar `not_in_catalog`** ni el gate de modo en `runner.py`.
- **Subagentes.** Decisión escrita en cuatro sitios y por la misma razón.
- **Memoria de equipo**, que la KB lista junto a «instrucciones propias» en la
  fila 015. Es otra cosa: instrucciones son lo que el partner escribe una vez;
  memoria es lo que el sistema acumula. Confundirlas metería una spec de
  persistencia dentro de una de prompt.

---

## Assumptions to Validate

1. **Que un segundo mensaje de sistema en la posición 2 no rompe el caché.** El
   razonamiento es que el caché es encaje de prefijo y el prefijo no cambia — pero
   está sin medir. **Es la primera cosa que la spec tiene que comprobar**, porque
   si falla, D-1 entero cambia de forma.
2. **Que las combinaciones de interruptores son pocas y enumerables.** Son 5
   booleanos + 2 modos + máquina presente. Suficientemente pocas para recorrerlas
   en un test; hay que confirmar que no hay más ejes escondidos.
3. **Que la aplicación puede mandar su zona horaria** sin ampliar de forma
   peligrosa el esquema cerrado del contexto de página.
4. **Que el partner es confianza declarada para su propio texto.** Es coherente
   con que ya escribe el prompt entero del agente de su cliente, pero **no está
   escrito en ningún sitio** y esta spec tendría que escribirlo.
5. **Que los 7.044 caracteres del prefijo le sobran sobre los 512 tokens
   cacheables** aun quitándole las afirmaciones de capacidad. Estimado por
   caracteres, no medido con el tokenizador.
