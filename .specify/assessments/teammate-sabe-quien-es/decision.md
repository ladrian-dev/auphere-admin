# Decision: que el turno diga lo que el partner configuró

- **Slug**: teammate-sabe-quien-es
- **Decided**: 2026-09-22
- **Verdict**: **go** — Option B, en cuatro tramos
- **Artifacts reviewed**: `intake.md` · `research.md` · `problem.md` ·
  `concept.md`

---

## Scorecard

| Criterio | Nota | Justificación |
|---|---|---|
| Validez del problema | **strong** | No es opinión: un teammate de solo-publicar tiene **2 herramientas** y su prompt le promete 26; en modo `consult` sin `read` tiene **cero** y el prompt le sigue prometiendo las dos familias. Contado ejecutando `for_teammate`, no leído |
| Fuerza de la evidencia | **strong** | Todo el `research.md` va con ruta:línea o contado ejecutándolo. **Y corrigió dos afirmaciones del propio encargo** —el lint por nombres no caza nada, y el caché estaba mal planteado—, que es la señal de que la evidencia mandó sobre la expectativa |
| Valor vs. no hacer nada | **strong** | Sin esto, el partner sigue obteniendo el mismo agente con distintos nombres, los interruptores siguen siendo una trampa, y **el desajuste vuelve**: ya ha pasado tres veces, la última inadvertida |
| Viabilidad / apetito | **strong** | `medium`, cuatro tramos sueltos, sin frontera nueva. El mecanismo no se inventa: `page_context_message` y `_now_note` ya existen en este repositorio, probados |
| Encaje estratégico | **adequate** | Es lo que el producto vende —agentes a medida— pero **no es la pieza que más mueve la aguja**: ésa es el toolset, y está bloqueada por su propia evaluación. Esto la prepara; no la sustituye |
| Postura de riesgo | **adequate** | El riesgo único está identificado y acotado —el campo de instrucciones y §III— y va en el **último** tramo a propósito. Queda **un supuesto sin medir** (el caché), reconocido abajo y no glosado |

---

## Verdict & Rationale

**Go**, con Option B y los cuatro tramos en su orden.

Lo que inclina la decisión no es que gane las seis métricas, sino **qué clase de
deuda es**. Los tramos 1 y 2 no añaden una función: **quitan una mentira que el
sistema cuenta en cada turno**. Una mentira así se paga con intereses — cada
herramienta que llegue después agranda la distancia entre lo prometido y lo
entregado.

Y el tramo 2, la puerta, es el **más barato de los cuatro** y el único que impide
que el trabajo se deshaga solo. Este repositorio ha visto el desajuste
prompt↔catálogo tres veces; la tercera entró el 2026-09-20 con `shell_local` y
pasó inadvertida hasta que alguien fue a buscarla.

**Se rechaza esperar** (Option C) por una razón concreta y no por prisa: el
bloqueo de la evaluación hermana —comando suelto vs. sesión viva— exige medir
dónde está el coste real antes de diseñar, y nadie ha hecho esa medida. Atar esto
a aquello no acelera aquello, y deja la deuda creciendo meses.

**Se rechaza solo el entorno** (Option A) porque deja la mentira intacta mientras
añade una verdad al lado.

---

## Las decisiones de la puerta

Canónicas. **No se re-discuten en `specify`.**

### D-A · El número. Esta spec es la **015**

Decisión de Luis, 2026-09-22. El toolset de trabajo —ficheros, web, conectores,
superficie `3a`— toma un número posterior cuando cierre
`teammate-que-trabaja-en-la-terminal`.

> **La fila 015 de la KB se parte en dos y hay que corregirla.** Hoy dice «El
> teammate trabaja» y enumera el conjunto —toolset, continuación autónoma, plan
> visible, compactación, reintentos, barrido de zombis, techos de duración,
> instrucciones propias y memoria de equipo—. De esa lista, esta spec se lleva
> **solo las instrucciones propias**, más lo que la investigación del 2026-09-22
> añadió y la fila no tenía. El resto se queda esperando a su evaluación.

### D-B · El texto del partner es instrucción a propósito; lo leído es dato

Decisión de Luis, 2026-09-22: **confianza declarada, y vallar lo leído.**

La spec escribirá la frontera, que hoy no está escrita en ninguna parte:

- **Lo que el partner configura** —`job`, instrucciones propias— **es
  instrucción**, y se obedece. La razón es de coherencia, no de comodidad: ese
  mismo partner ya escribe **entero** el prompt del agente que atiende a sus
  clientes finales, que es mucho más poder que esto. Negarle instrucciones para
  su propio teammate mientras se le da el prompt del agente de su cliente sería
  una frontera sin sentido.
- **Lo que el teammate lee** —ficheros, salidas de programas, contexto de
  página— **es dato, siempre**, y se valla. El modelo ya está escrito en este
  repositorio y con su razón anotada (`page_context_message` +
  `fence_only`): *«Que llegue con `role: system` lo hace MÁS peligroso, no
  menos»*.

**Y lo que esto NO defiende, escrito y no dejado implícito**: no defiende del
**partner comprometido**. Quien controle una cuenta de partner con permiso para
editar teammates puede escribirles instrucciones, igual que hoy puede reescribir
el prompt del agente de su cliente. La mitigación de ese caso es de otra capa
—autenticación, permisos, auditoría— y esta spec no la mejora ni la empeora.

> **Consecuencia inmediata: esto regulariza `job`.** Hoy el campo mete 80
> caracteres escritos por el partner dentro de un `role: "system"` **sin que
> ninguna spec lo haya dicho nunca**. No es un defecto nuevo que se introduzca:
> es uno existente que pasa de supuesto a escrito.

### D-C · Dos mensajes, no uno

Identidad en la **posición 2**, justo tras el prefijo — hoy va detrás de la
historia entera, así que en un hilo de cuarenta mensajes llega en la 42 mientras
«Eres el Companion de Auphere» sigue en la 1, y **empeora según se trabaja**.
Entorno **justo antes del turno**, que es donde vive lo fresco. Quieren sitios
opuestos; juntarlos obliga a elegir mal para una de las dos.

Descartado meter la identidad en el prefijo: daría **un prefijo por teammate**,
ninguno reutilizado, y `test_companion_graph.py:49` lo congela por esa misma
razón. Descartados dos prefijos: 7 KB copiados que divergen — este repositorio
acaba de pagar por un vocabulario escrito dos veces.

### D-D · Las capacidades se derivan, no se afirman

Por **familia** (lecturas / propuestas / aplicar / máquina), desde el mismo sitio
del que sale el catálogo. Ni enumerar los 44 nombres —duplica el schema que el
modelo ya recibe— ni mantener prosa a mano. **Y el prefijo deja de afirmar
capacidades**: pasa a remitir al bloque propio, que es una afirmación que nunca
caduca.

### D-E · La puerta tiene dos mitades

Una afirma que **el prefijo no promete capacidades**. La otra recorre las
combinaciones de interruptores y exige que **lo generado coincida con
`for_teammate`**.

> La versión obvia —un lint que compare nombres citados contra catálogo— **da
> cero hallazgos hoy**, comprobado: el prompt nombra tres herramientas y las tres
> existen. Nacería verde vigilando nada. Esta sesión acaba de pagar el precio de
> un test así, y la lección se aplica aquí antes de escribirlo: **primero se
> escribe qué cambio futuro tiene que ponerlo rojo, y de ahí sale la forma.**

### D-F · La zona horaria la manda la aplicación

La de **la persona que escribe**, con la del `tenant` como matiz cuando el turno
va de un cliente, y repliegue a **UTC con marca visible** si viene malformada —
copiando `pipeline.py:657-662`, que ya resolvió ese caso feo.

Razón, comprobada en los modelos: **el partner no tiene columna de zona horaria
y la persona tampoco**. Solo la tiene el `tenant` (`db/models/tenant.py:66`). Una
columna nueva es una migración y una pregunta más en el alta para algo que el
navegador ya sabe.

---

## Lo que esta spec NO entrega, dicho aquí y no al final

**El teammate seguirá sin ser un trabajador para el cliente del partner.**

De sus 44 herramientas, **40 administran la consola de Auphere**. Fuera de
`shell_local` no tiene ficheros, ni web, ni conectores. Esta spec hace que sepa
quién es, qué día es y qué tiene de verdad — **no le da nada nuevo que hacer**.

Quien lea «El teammate trabaja» y espere un trabajador se va a llevar un chasco,
y es mejor que ese chasco ocurra aquí, leyendo esto, que al entregar. Lo que
convierte al teammate en trabajador es el toolset, y está en la otra evaluación.

---

## Supuestos que hay que validar en `specify`

1. ~~**Que un segundo mensaje de sistema en la posición 2 no rompe el caché.**~~
   **COMPROBADO el mismo día, y la respuesta refina D-C.** Ver abajo.
2. **Que las combinaciones de interruptores son pocas y enumerables** (5
   booleanos + 2 modos + máquina presente). Confirmar que no hay más ejes
   escondidos, o la puerta de D-E tendrá un agujero por donde no se mira.
3. **Que la aplicación puede mandar su zona horaria** sin ensanchar de forma
   peligrosa el esquema cerrado del contexto de página, que hoy tiene cuatro
   claves y está vallado.
4. **Que la confianza declarada de D-B se sostiene** al escribirla como requisito
   con sus límites, no solo como párrafo.
5. **Que los 7.044 caracteres del prefijo le sobran sobre los 512 tokens
   cacheables** aun quitándole las afirmaciones de capacidad. Estimado por
   caracteres; medirlo cuesta media hora y solo importa si el margen aprieta.

### El supuesto 1, comprobado — y D-C necesita una línea más

Se comprobó antes de especificar, porque bloqueaba la forma. Lo que dice el
código (`apps/worker/src/nexus_worker/runtime/llm.py:204-249`):

> `_with_prompt_caching` **fusiona todos los mensajes de sistema iniciales
> contiguos** en un único mensaje con bloques de texto, y pone el
> `cache_control` en **el último bloque**. Un `cache_control` cachea *todo el
> prefijo hasta él*.

**Consecuencia, y no es la que el concepto suponía:** un mensaje de identidad
colocado en la posición 2 —antes de la historia, que es lo que pide D-C— **es un
mensaje de sistema inicial contiguo**. Se fusiona con el prefijo y el punto de
corte se mueve **detrás de él**.

Es decir: la identidad **entraría dentro del prefijo cacheado**, que es
exactamente lo que D-C dijo que evitaba al descartar meterla en `SYSTEM_PROMPT`.
Y con ella dentro, **cada teammate tendría su propia entrada de caché** en vez de
compartir una — los 7 KB se escribirían N veces en lugar de una.

**El arreglo es barato y el propio código ya lo anticipa**, en el docstring de
`_cache_the_tail` (`llm.py:176-179`):

> «Anthropic admite **cuatro** puntos por petición y el prefijo usa uno; este es
> el segundo.»

Quedan **dos libres**. Con un punto de corte tras `SYSTEM_PROMPT` —compartido por
todo el mundo— y otro tras el bloque de identidad —propio de cada teammate—, los
7 KB se cachean **una vez para todos** y lo único que se escribe por teammate es
el delta de la identidad, unos cientos de caracteres.

**Qué cambia en D-C**: la decisión de fondo se mantiene —identidad en la posición
2, entorno antes del turno—, pero **deja de ser gratis por sí sola**. La spec
tiene que tratar el punto de corte como parte del requisito, no como un detalle
de implementación, o el ahorro del prefijo se multiplica por el número de
teammates sin que nadie lo note.

> **Y esto es, otra vez, la misma lección del día**: el supuesto estaba razonado
> y era falso por un motivo que solo se ve leyendo el código de al lado. La
> diferencia es que esta vez se miró antes de construir.

---

## Superficie de confianza

**`0`.** No hay frontera nueva: no se abre ningún puerto, ni ninguna ruta, ni
ninguna credencial. Cambia lo que el prompt dice, de dónde sale, y se añade una
tabla con un campo de texto. El único tramo con migración es el cuarto.

Ninguna de las ocho garantías de aislamiento se debilita. Al contrario: el
cambio de `unknown_tool` —que hoy devuelve las 44 del catálogo entero
(`runner.py:204`)— **reduce** una fuga de superficie existente. Y
`not_in_catalog` no se toca: es el respaldo empírico de la garantía 2 frente a un
fallo que la industria sí tiene documentado y reproducible.

---

## Handoff a `/speckit-specify`

- **Problema**: un teammate afirma en cada turno cosas de sí mismo que no son
  ciertas para él — se llama Companion antes que por su nombre, promete dos
  familias de herramientas sin comprobar si las tiene, y no sabe qué día es.
- **Enfoque elegido**: Option B — dos mensajes de sistema propios (identidad en
  la posición 2, entorno antes del turno), capacidades derivadas por familia,
  el prefijo deja de afirmarlas, `unknown_tool` nombra solo las suyas, y una
  puerta de dos mitades. Más un campo de instrucciones propias en el último
  tramo.
- **Dentro**: identidad propia · bloque de entorno · capacidades reales ·
  `unknown_tool` acotado · la puerta · instrucciones propias del partner.
- **Fuera**: el toolset de trabajo (`3a`, otra evaluación) · la unidad de
  ejecución · hablar con un colega (decisión escrita de la spec 003, con el tipo
  de nota `handoff` ya reservado en su R3.6) · reescribir `SYSTEM_PROMPT` ·
  tocar `not_in_catalog` · subagentes · memoria de equipo.
- **Métricas de éxito**: las seis de `problem.md`, observables por un partner y
  no por un test.
- **Orden de entrega**: (1) el sitio y la verdad · (2) la puerta · (3) el
  entorno · (4) instrucciones propias. Cada tramo vale suelto.
- **Preguntas que viajan**: los cinco supuestos de arriba, y la primera bloquea
  la forma de D-C.
