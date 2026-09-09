# Problem Definition: el puesto de trabajo del teammate en la máquina del partner

- **Slug**: kirocrew-como-sustrato
- **Created**: 2026-09-09
- **Inputs used**: `intake.md` · `research.md`
- **Nota de KB que lo justifica**: `[[14-mvp-y-fases]]` §3 y `[[15-kirocrew-y-alternativas]]`
  (`/Users/lmatos/Work/Auphere/teammates/`)
- **Etapa anterior**: [`research.md`](./research.md)
- **Superficie de confianza del problema** (Constitución §II): **3a** — ejecutar en
  la máquina del partner

> Esta etapa **enmarca el problema; no propone solución**. Las opciones son de
> `/speckit-assess-shape` y el veredicto de `/speckit-assess-decide`.

**Nota de encuadre.** La idea entró como solución — «adoptar KiroCrew como
sustrato». Esta etapa exige lo contrario: escribir el problema que esa solución
pretende resolver. Por eso KiroCrew casi no aparece aquí. Reaparece en `shape`
como una opción entre varias, junto a construirlo nosotros y a cosechar el
repositorio sin adoptarlo.

**Nota de alcance.** El `intake` abría esto sobre las betas 2 **y** 5. Este
documento lo estrecha a la **beta 2**, por decisión del 2026-09-09 y con la razón
escrita en *Non-Goals*: la evidencia del `research` no es homogénea entre las dos,
y juntarlas arrastraría a la beta 2 al bloqueo de una medición que solo le hace
falta a la beta 5.

---

## Problem Statement

El teammate de la beta 1 **propone; no hace**: vive en la superficie 0 y todo lo
que decide lo ejecuta después una persona a mano. El diferencial que
`14-mvp-y-fases` §3 pone en la beta 2 —que el teammate abra el repositorio del
partner, corra el build, lea el log, arregle y vuelva a correr, en la máquina del
partner y con sus credenciales— exige un **puesto de trabajo del agente** que
Nexus no tiene construido: sandbox de sistema operativo, contención de escrituras
con los seis ataques en macOS **y** Windows, `shell_local` acotado con lista
blanca y directorio fijado, presencia de dispositivo, empaquetado firmado con
autoactualización y ejecución larga.

Duele ahora porque el resto de la plataforma ya está: el plano de control
multi-cliente —RLS por `principal_id`, wallet y medidor, 40+ herramientas
`console.*`, aprobaciones durables, WhatsApp por la API oficial— está construido y
probado, y `07-competencia` no registra a nadie que haga esto para un partner que
gestiona clientes finales. Lo que separa a Nexus de su diferencial no es una
decisión de producto pendiente: es la mitad cara del recorte, sin empezar.

---

## Affected Users & Stakeholders

- **Usuarios — el partner que opera el teammate.** Hoy recibe propuestas y las
  ejecuta él: el ambiente donde el trabajo tiene sentido —sus repos, sus
  credenciales de git, sus CLI, su red interna— está en su máquina, y el teammate
  no llega ahí. Una VM no lo sustituye: ese ambiente habría que reconstruirlo
  entero (`14-mvp-y-fases` §1.2). — [fuente: `14-mvp-y-fases` §3.1]
- **Usuarios — el partner cuando cierra el portátil.** El mismo trabajo, con la
  máquina apagada, es la promesa de la beta 5 y **queda fuera de este documento**
  (ver *Non-Goals*). Se nombra porque es la frontera del alcance, no porque se
  resuelva aquí.
- **Stakeholder — Auphere (Luis).** Decide y financia. Es quien asume el coste de
  construir el puesto de trabajo, o el riesgo de mantenimiento de fijar y seguir
  un sustrato externo.
- **Stakeholder — el cliente final del partner.** No toca el teammate y no es su
  usuario, pero es el titular de los datos que el aislamiento protege. Le alcanzan
  §I (lista blanca exhaustiva por tenant, sin globales) y la restricción de que
  ninguna credencial suya entre nunca en el ambiente de un agente, ejecute donde
  ejecute. — [fuente: `constitution.md` §I y *Restricciones adicionales*]

---

## Goals

- **Acortar el calendario del diferencial** hasta el criterio de aceptación de
  `14-mvp-y-fases` §3.5, sin debilitar ninguna de las 7 garantías de aislamiento.
- **Que Nexus siga siendo dueño de todo lo que toca datos de cliente final**: el
  plano de control, el medidor, las aprobaciones durables y el canal oficial no se
  delegan a nada externo.
- **Que el catálogo de herramientas de una sesión sea exactamente la lista blanca
  del tenant** — ni una entrada más, venga de donde venga (§I).
- **Que, si el puesto de trabajo se apoya en un sustrato externo, no se convierta
  en un fork disfrazado**: núcleo sin modificar y actualizable aguas arriba.
- **Que el precio de abrir la superficie 3a se pague entero y una sola vez** (§II):
  ADR, test de aislamiento, medidor, estado nuevo en la UI y lectura de RGPD.

---

## Non-Goals

- **La beta 1 no se toca.** Vive en la superficie 0 y se apoya en RLS, wallet,
  herramientas `console.*`, aprobaciones durables y los 44 archivos de UI del
  companion. Meter aquí un sustrato externo sería reescribir lo que ya está
  probado. — [fuente: `15-kirocrew-y-alternativas` §8]
- **La beta 5 (VM compartida, superficie 2) queda fuera, y por una razón, no por
  comodidad.** El `research` es explícito: el spike 3 midió 511 MiB en macOS y sin
  cargar el GGUF, y **no sirve para dimensionar Fargate ni para rehacer los
  121 $/mes/partner**. Se reabre como evaluación propia cuando exista la medición
  en Linux, con el modelo de embeddings cargado y con N sesiones; hasta entonces
  esa pregunta es un `[NEEDS CLARIFICATION]` que bloquearía su `/speckit-plan`.
- **El multi-seat dentro de un mismo partner** (decisión 9: hilo privado por
  persona, RLS por `principal_id`). Es nuestro en cualquier escenario y ninguna
  base open source lo regala; no es lo que esta evaluación decide.
- **Las betas 3, 4 y 6.** En particular la **3b** —controlar el escritorio: ratón,
  teclado, lectura de pantalla— que `14-mvp-y-fases` §3.3 saca de la beta 2 a
  propósito, y que en Windows no tiene precedente abierto que copiar.
- **El navegador embebido dentro de la beta 2.** Sin las guardas de §1.3,
  navegador y `shell_local` a la vez es exactamente la combinación que §III
  prohíbe.
- **Reabrir la tabla de licencias** de `15-kirocrew-y-alternativas` §5. Está leída
  archivo a archivo y cerrada: no existe base OSS multi-tenant que permita
  revenderla.
- **Verificar la mitigación `--strict-mcp-config`.** Diferido por decisión del
  2026-09-09: entra como **primera tarea del plan de la beta 2**, no como
  continuación del `research`.
- **El fork completo con rebranding de cabo a rabo** (camino C de
  `15-kirocrew-y-alternativas` §6). Descartado allí con su razón; no se reabre.

---

## Success Metrics

Las cinco primeras son del producto y salen del criterio de aceptación de
`14-mvp-y-fases` §3.5. Las tres últimas son de integridad del sustrato y sus
baselines los midió el `research`.

| Señal | Baseline |
|---|---|
| El teammate corre el build de un proyecto real del partner, falla, lee el log, propone el arreglo y lo vuelve a correr, con aprobación en medio | **No existe.** Hoy el teammate propone y ejecuta una persona |
| Los seis ataques de contención de escrituras pasan en macOS **y** en Windows | **0/6 en ambos** — no construido. Suite de referencia identificada (`desktop-sandbox-write-containment.test.ts`, Apache-2.0) |
| Con el portátil cerrado, la UI lo dice como **estado**, no como error, y las herramientas locales **desaparecen del catálogo** en vez de fallar (§V) | **No existe.** Presencia de dispositivo es nivel 1 de `11-features-que-faltan` |
| Un comando fuera de la lista blanca pide aprobación la primera vez y queda en auditoría con la **persona** que la concedió (`decided_by`, §IV) | Aprobación durable **construida** en Nexus; `shell_local` y su lista blanca **no** — decisión `10-decisiones` §2.7 **abierta** |
| Suite de aislamiento en verde, con un test nuevo por cada garantía que toque la superficie 3a (§I) | **46 en verde** hoy |
| Archivos modificados en el núcleo del sustrato, si es externo | **0** — medido en el spike 2 sobre `37933a5` |
| Servidores MCP en el catálogo de una sesión por encima de la lista blanca del tenant | **4 heredados** de `~/.claude.json` en una máquina de desarrollo — medido en el `research`. Objetivo: **0** |
| Calendario hasta el criterio de aceptación de §3.5 | `[NEEDS CLARIFICATION: no hay estimación escrita. La KB habla de «trimestres» para el camino de construirlo y de «semanas» para el de adoptarlo, sin cifra que soporte ninguna de las dos]` |

---

## Cost of Inaction

Si no se construye nada, el teammate se queda en la superficie 0: propone y una
persona ejecuta. El diferencial que `14-mvp-y-fases` llama «la fase del
diferencial» no llega, y con él no llega la razón por la que un partner elegiría
esto sobre un asistente de consola cualquiera.

Si se construye pero por el camino largo, el coste está escrito pieza a pieza en
`14-mvp-y-fases` §3.2: cáscara Electron, puente saliente, presencia de
dispositivo, `shell_local` acotado, herramientas separadas por destino, la suite
de contención de los seis ataques, la misma contención en Windows con rutas
relativas NT, y firma con autoactualización. Más las dos puertas de entrada de
§3.4, de las que una **tiene plazo de entrega y hoy no está**: los certificados de
distribución —en esta máquina solo hay «Apple Development», que no sirve para
distribuir, y los OV de Windows duran 460 días desde marzo de 2026—. Eso se pide
cuando arranca la beta 1, no cuando arranca la 2.

Y hay un suelo que se pisa decidamos lo que decidamos: el camino B de
`15-kirocrew-y-alternativas` §6 —leer la suite de contención, el modelo
`POLICY ∩ PROFILE`, la escalera de aprobaciones y los specs de módulo— ahorra
semanas de diseño, no de construcción, y no tiene riesgo. Por eso no aparece en
las métricas de arriba: no es una alternativa, es el piso.

---

## Open Questions

Ninguna bloquea `shape` ni `decide`. Bloquean el `/speckit-plan` de la spec que
salga de aquí, en la puerta de cero `[NEEDS CLARIFICATION]`, y ahí es
`/speckit-clarify` quien las cierra.

- [NEEDS CLARIFICATION: **el `~/.claude.json` del partner.** En la beta 2 ese
  fichero es suyo y puede contener cualquier cosa; el backend hereda sus servidores
  MCP y el gateway lanza sus procesos. La mitigación —`--strict-mcp-config` a
  través de un envoltorio apuntado por `CLAUDE_CODE_EXECUTABLE`— está identificada
  y **sin verificar**, y entra como primera tarea del plan de la beta 2.]
- [NEEDS CLARIFICATION: ¿puede el partner añadir a propósito sus propios servidores
  MCP? Es la variante deliberada del punto anterior, y es una decisión de producto,
  no un hallazgo técnico.]
- [NEEDS CLARIFICATION: **el coste real del rebranding.** Las marcas Kiro/Kiro Crew
  no están licenciadas y aparecen en la UI, en los paquetes (`kiro_crew`), en el
  data home (`~/.kiro`), en el workspace (`~/workplace/kirocrew-workspace`) y en los
  mensajes de error. Solo aplica si el sustrato es externo; `shape` pondrá una talla
  aproximada, no una cifra.]
- [NEEDS CLARIFICATION: **¿crece el RSS con los turnos?** Se observó en todos los
  turnos que procesos hijos sobreviven al teardown. Un gateway de vida larga en el
  portátil del partner también lo sufre, no solo el de la nube.]
- [NEEDS CLARIFICATION: **¿subagentes sin cliente de dashboard?** El spawn se
  rechaza cuando ninguna superficie puede contestar la aprobación. En la beta 2 la
  cáscara de escritorio podría ser esa superficie, pero está sin comprobar.]
- [NEEDS CLARIFICATION: **sin techos de recursos fuera de Linux.** El propio
  arranque lo avisa. La beta 2 corre en el portátil del partner —macOS o Windows—,
  donde no hay contención de fork-bomb ni de memoria.]
- [NEEDS CLARIFICATION: **`shell_local` sigue abierto** (`10-decisiones` §2.7). Es
  puerta de entrada de la beta 2 según `14-mvp-y-fases` §3.4, y no depende de qué
  sustrato se elija.]

---

**Siguiente etapa**: `/speckit-assess-shape slug=kirocrew-como-sustrato`
