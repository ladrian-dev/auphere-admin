# Idea Intake: un teammate que sabe quién es, qué día es y qué puede hacer de verdad

- **Slug**: teammate-sabe-quien-es
- **Created**: 2026-09-22
- **Source**: sesión del 2026-09-22 (texto pegado) · investigación propia en
  `/Users/lmatos/Work/Auphere/nexus/research/2026-09-22-que-sabe-un-teammate-de-si-mismo.md`
  · punteros de código: `apps/worker/src/nexus_worker/runtime/companion/prompt.py`,
  `.../companion/graph.py`, `.../companion/runner.py`,
  `apps/api/src/nexus_api/services/teammate_catalog.py`,
  `apps/api/src/nexus_api/api/console/companion.py`
- **Type**: gap + improvement

## Idea (tal como llegó)

Luis, el 2026-09-22, dentro de un encargo más amplio de dejar el producto listo
para los partners:

> «Para esto te pregunto, como hace hoy un teammate para saber quien es?, que
> hace? como editarse su configuracion para mejorar? como sabe que herramientas
> puede usar, como sabe como comunicarse con su colega, como saque que debe
> editar y saber a que tiene acceso y a que no?... Valida esa y otras respuestas
> que encuentres en el camino comparandolo con Grok, Claude Desktop, y otros
> referentes de la industria.»

La investigación que contestó esa pregunta está fechada el mismo día y
contrastada con fuentes primarias de Anthropic, OpenAI, xAI y Sierra. Su
resumen, verbatim:

> De nueve cosas que debería saber, **sabe tres**. Y el sistema está **mejor
> construido de lo que la pregunta sugiere** […] Lo que falla no es el diseño: es
> que **lo que el partner configura no llega entero al turno**.

## Restated

Un teammate de Nexus arranca cada turno sin saber para qué partner trabaja, con
quién habla, qué día es, ni qué herramientas tiene realmente — su prompt promete
un catálogo fijo mientras el catálogo real varía por interruptores. Esta idea
propone que el teammate reciba su propia identidad, su propio bloque de entorno
y sus capacidades reales, y que un test vigile que lo prometido y lo entregado
no vuelvan a separarse.

## Origin & Context

- **Raised by**: Luis, 2026-09-22.
- **Trigger**: la pregunta de arriba, hecha mientras se cerraba la spec 012. Al
  contestarla aparecieron **dos defectos** —el «Cerebro» que el partner elegía no
  llegaba al run, y tres de los cinco interruptores entregaban un teammate que no
  podía terminar— que se arreglaron el mismo día por el flujo de bug
  (`.specify/bugs/lo-que-el-partner-elige-no-llega-al-teammate/`). Lo que queda
  **no son defectos**: es capacidad que nunca se construyó, y por eso va por
  evaluación y no por hotfix.
- **Relación con la evaluación hermana**: `teammate-que-trabaja-en-la-terminal`
  (intake del 2026-09-20) plantea la pregunta cara —¿la unidad pasa a ser una
  sesión viva, PTY o tmux, o sigue siendo un comando?—. **Aquí no se toca**, y su
  intake se queda como está. Las dos comparten el nombre «El teammate trabaja» en
  la KB y **no son el mismo problema**: aquella cambia el modelo de seguridad,
  ésta cambia lo que el teammate sabe de sí mismo.

## Lo que hoy pasa, con lo verificado marcado

Comprobado leyendo el código el 2026-09-22:

| Lo que debería saber | ¿Lo sabe? |
|---|---|
| Qué es Auphere y qué hace el producto | **Sí** |
| Su nombre y su oficio | **Sí**, en cuatro frases |
| Lo que está globalmente prohibido | **Sí**, lista fija |
| Para qué partner trabaja | **No** — gasta una llamada a `console.whoami` |
| Con quién habla | **No** — «la persona que te escribe» |
| **Qué día es** | **No** |
| Qué herramientas tiene **de verdad** | **No** — el prompt promete un catálogo fijo |
| Qué le falta **a él** y por qué | **No** — lo descubre chocándose |
| En qué modo está | **No**, y en la app siempre es `build` |
| Cómo hablar con un colega | **No existe**, y está prohibido a propósito |

Cuatro observaciones que la evaluación tendrá que pesar, y que no son opinión:

- **Dos identidades en conflicto, y gana la genérica.** El prefijo cacheado
  arranca con «Eres el Companion de Auphere»; la identidad propia llega tres
  mensajes después. La doctrina del Agent SDK de Anthropic dice lo contrario con
  todas las letras: *«the agent shouldn't present itself as Claude Code… needs
  its own name, scope, and persona»*.
- **Este mismo repositorio ya lo hace bien en el otro sitio.** El agente de canal
  recibe fecha, hora, zona y una instrucción de comportamiento —«NUNCA deduzcas
  el año ni la fecha de tu propio conocimiento»—. El teammate no recibe nada de
  eso.
- **El desajuste prompt/catálogo ya ha ocurrido tres veces aquí**: dos corregidas
  a mano y una que entró el 2026-09-20 con `shell_local` sin que nadie revisara
  el prompt. Sierra lo caza con sus «Agent Checks» —*«a tool your prompt
  references but never made available»*—.
- **Cuando el modelo se inventa un nombre de herramienta, se le devuelven las 44
  del catálogo entero**, no las suyas.

Y una donde Nexus está **por delante**, que conviene no romper: `runner.py`
rechaza con `not_in_catalog` toda herramienta fuera del catálogo del teammate.
Hay un caso reproducible en la industria de un modelo que alucinó una
herramienta, se inventó los parámetros, la llamó **y funcionó** —probado contra
Anthropic, Google, xAI y OpenAI—. Esto es respaldo empírico de la garantía 2.

## First-Glance Unknowns

- [NEEDS CLARIFICATION: ¿las instrucciones propias las escribe el partner en
  texto libre, o se eligen de un repertorio? Texto libre es lo que piden los
  referentes y es también una entrada no confiable que acaba dentro del prompt
  de un agente con herramientas — §III dice que lo leído es dato, nunca
  instrucción, y aquí lo leído **es** instrucción a propósito.]
- [NEEDS CLARIFICATION: ¿dónde viaja cada cosa? El prefijo `SYSTEM_PROMPT` tiene
  que seguir siendo estable byte a byte —hay un test que congela `"{" not in
  SYSTEM_PROMPT` porque Anthropic cachea el prefijo—, así que todo lo que varíe
  por turno va fuera. Cuánto cabe fuera sin perder el ahorro del caché es una
  medida, no una opinión.]
- [NEEDS CLARIFICATION: el punto 6 de la nota —el toolset de trabajo: ficheros,
  web, conectores— es superficie `3a` y es el que solapa con la evaluación de la
  terminal. ¿Entra aquí, se parte, o se queda entero en la otra? De esto depende
  si esta evaluación es barata o es la más cara de la ola.]
- [NEEDS CLARIFICATION: la comunicación entre teammates está **prohibida a
  propósito** hoy. Abrirla no es añadir una herramienta: es una decisión de
  aislamiento. ¿Se evalúa aquí o se declara fuera de alcance?]
- [NEEDS CLARIFICATION: ¿cuánto del hueco es «el teammate no sabe» y cuánto es
  «el teammate no tiene»? 40 de las 44 herramientas administran la consola de
  Auphere: decirle mejor lo que tiene no lo convierte en un trabajador para el
  cliente del partner.]

## Licencias, anotado ya para no repetirlo

`elder-plinius/CL4R1T4S` es **AGPL-3.0** e incompatible con la regla 7 del
`CLAUDE.md`: se cita en prosa, **no se vendoriza**. Pasan la puerta
`asgeirtj/system_prompts_leaks` (CC0-1.0), `LouisShark/chatgpt_system_prompt`
(MIT) y `xai-org/grok-build` (Apache-2.0); no pasa `AnRkey/Grok-Desktop`
(GPL-2.0).

## Superficie de confianza, como primera lectura

`0` para los cinco primeros puntos: no hay frontera nueva — cambia lo que el
prompt dice y se añade un test. `3a` solo para el sexto. **Esa separación es
justamente lo que la evaluación tiene que confirmar o tumbar**, porque de ella
depende el precio.
