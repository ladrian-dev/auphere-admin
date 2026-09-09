# Decision: el puesto de trabajo del teammate en la máquina del partner

- **Slug**: kirocrew-como-sustrato
- **Decided**: 2026-09-09
- **Verdict**: **go** — acotado a la **beta 2** (superficie 3a). La **beta 5**
  queda **diferida**, no matada, con su condición de reapertura escrita
- **Artifacts reviewed**: `intake.md` · `research.md` · `problem.md` · `concept.md`
- **Opción elegida**: **A — sustrato externo compuesto**, con **C** como forma de
  repliegue
- **Nota de KB**: `[[15-kirocrew-y-alternativas]]` §7bis y §8 ·
  `[[14-mvp-y-fases]]` §3

---

## Scorecard

| Criterion | Rating | Justification |
|---|---|---|
| **Problem validity** | **strong** | El problema está escrito y es del producto, no de la herramienta: la beta 1 propone y no hace, y el diferencial de `14-mvp-y-fases` §3 exige un puesto de trabajo del agente que Nexus no tiene empezado. `07-competencia` no registra a nadie haciendo esto para un partner que gestiona clientes finales |
| **Evidence strength** | **adequate** | Las dos preguntas que abren la puerta de esta beta se respondieron **ejecutando**, con evidencia conservada y reproducible: arranca sin kiro-cli y `doctor` no bloquea; la edición compone por el entry point con el núcleo a **0 archivos modificados**. No llega a `strong` por dos huecos honestos: **no existe cifra de calendario** para ninguna opción, y la mitigación del hallazgo MCP está **identificada pero sin verificar**. Lo que hundía la evidencia —el spike 3, que no sirve para dimensionar— pertenecía a la beta 5, que ya no está en el alcance |
| **Value vs. inaction** | **strong** | Sin esto el teammate se queda en la superficie 0. Con la opción B el diferencial llega, pero pagando con el activo escaso, que es el calendario. A obtiene ya construidas y con tests las piezas más caras del recorte: sandbox de SO, contención de escrituras en macOS y Windows, empaquetado firmado, cron, TaskRunner, subagentes, memoria y log encadenado |
| **Feasibility / appetite** | **adequate** | La talla *medium* la sostiene el `research`: el seam compuso con ~60 líneas y sin tocar el núcleo. La rebaja a `adequate` viene de que **no hay rueda pública** —el wheel lo construimos nosotros desde un commit fijado, mantenimiento recurrente— y de que el calendario sigue sin cifra. El rebranding, que estaba sin cuantificar, se midió en `concept.md` y resultó **pequeño en superficie visible y recurrente en vigilancia** |
| **Strategic fit** | **adequate** | §VIII limpio: Apache-2.0 sin condiciones, `NOTICE` conservado y marcas no usadas. §II se respeta: la 3a se abre una vez y con la mitad cara ya construida. §IX en pie: la KB es dueña del porqué y el repo del cómo. **No llega a `strong` por una tensión real y sin cerrar**: el hallazgo MCP choca con §I (lista blanca exhaustiva por tenant, sin globales) y con §III (el orden de encendido), y la aprobación del sustrato no es durable, así que se puentea en vez de adoptarse (§IV) |
| **Risk posture** | **adequate** | Los riesgos están nombrados uno a uno y el decisivo tiene mitigación identificada, calendario —primera tarea del plan— y **alternativa escrita si falla** (C sobre B). No es `strong` porque esa mitigación **no está verificada**, y en la beta 2 el `~/.claude.json` es del partner |

---

## Verdict & Rationale

**Go**, sobre la beta 2 y con la opción A.

Los dos criterios que la plantilla pone como condición de un `go` están cubiertos:
la validez del problema es `strong` y la fuerza de la evidencia es `adequate` —
nunca `weak` ni `unknown` —, y hay una opción de concepto recomendada. Lo que
sostiene el `go` no es un argumento: son dos spikes ejecutados cuya salida cruda
está en `evidence/`. La puerta estaba cerrada por una pregunta —«¿corre sin
kiro-cli?»— y se abrió; el miedo de fondo era «esto acabará siendo un fork
disfrazado» y el clon terminó a 0 archivos modificados.

Contra eso pesa un hallazgo que no estaba en el guion y que **muerde justo en esta
beta**: el backend hereda los servidores MCP del usuario de la máquina, y en la
beta 2 esa máquina es del partner. No degrada la evidencia —el hallazgo está bien
soportado, es el remedio el que falta—, así que baja `strategic fit` y
`risk posture` a `adequate` y se convierte en la **primera tarea del plan**, con
su repliegue escrito. Ponerla la primera es deliberado: si el envoltorio no basta,
la opción A deja de ser composición antes de que nadie haya construido nada encima.

**La beta 5 no se mata: se difiere**, y la razón es de método, no de gusto. El
spike 3 midió 511 MiB en macOS y sin cargar el GGUF, y él mismo dice que no sirve
para dimensionar Fargate ni para rehacer los 121 $/mes/partner. Meterla en este
veredicto habría obligado a una de dos cosas: arrastrar la beta 2 a
`needs-clarification` por un hueco que no es suyo, o declarar `adequate` una
evidencia que el propio `research` llama insuficiente. Ninguna de las dos es
honesta. **Se reabre como evaluación propia cuando exista la medición en Linux,
con el modelo de embeddings cargado y con N sesiones.**

Y una cosa que este veredicto **no** cambia: el camino B se hace igual. La suite
de contención de los seis ataques y el modelo `POLICY ∩ PROFILE` valen la lectura
aunque no usemos una línea de su código. No es la alternativa; es el piso.

---

## If needs-clarification

No aplica al alcance decidido. Se registra lo que quedaría pendiente si el alcance
se reabriera a la beta 5:

- **Revisit stage**: `research`, con su propio slug.
- **Blocking questions**: RSS en Linux con el GGUF cargado y N sesiones · si el
  RSS crece con los turnos en un gateway de vida larga · el precio por partner
  rehecho a partir de las dos anteriores.

---

## If go — Handoff to `/speckit-specify`

- **Problem**: el teammate de la beta 1 propone y no hace; el diferencial exige un
  puesto de trabajo del agente en la máquina del partner —sandbox de SO,
  contención de escrituras en macOS y Windows, `shell_local` acotado, presencia de
  dispositivo, empaquetado firmado— que Nexus no tiene construido.
- **Chosen approach**: opción A — componer una edición Auphere sobre un runtime
  Apache-2.0 fijado a un commit, por su punto de extensión y sin tocar su núcleo.
  Nexus sigue siendo plano de control: las herramientas `console.*` llegan por un
  servidor MCP nuestro y las aprobaciones que tocan a un cliente final siguen
  siendo las durables. Repliegue escrito: opción C sobre B.
- **Superficie declarada** (§II): **3a**. La spec la declara en su encabezado y el
  plan paga el precio de entrada entero.
- **In scope**: beta 2 · superficie 3a · la edición compuesta, el servidor MCP de
  `console.*`, el puente saliente, la presencia de dispositivo y `shell_local`
  acotado.
- **Out of scope**: beta 1 (intacta) · beta 5 (diferida) · betas 3, 4 y 6 · el
  control del escritorio (3b) · el navegador embebido dentro de esta beta ·
  el multi-seat dentro de un partner · renombrar identificadores internos · el
  canal de WhatsApp del sustrato, su cargador de apps y su telemetría, que se
  apagan · la tabla de licencias, cerrada.
- **Success metrics**: las ocho de [`problem.md`](./problem.md), con sus baselines
  medidos. Las que gobiernan son: los seis ataques de contención en verde en
  **ambos** sistemas operativos · **0** servidores MCP por encima de la lista
  blanca del tenant · **0** archivos modificados en el núcleo · la suite de
  aislamiento en verde con un test nuevo por cada garantía que toque la 3a.
- **Primera tarea del plan, no negociable**: verificar que el envoltorio con
  `--strict-mcp-config` vía `CLAUDE_CODE_EXECUTABLE` deja el catálogo solo con las
  herramientas de Crew y que Crew sigue viendo las suyas. Si falla, la spec se
  replantea sobre C antes de construir nada.
- **Carried-forward open questions**: las siete de `problem.md`. Ninguna bloquea la
  redacción de la spec; **todas** bloquean su `/speckit-plan` en la puerta de cero
  `[NEEDS CLARIFICATION]`, y es `/speckit-clarify` quien las cierra. La más
  urgente, porque es puerta de entrada de la beta 2 y no depende del sustrato:
  cerrar `shell_local` (`10-decisiones` §2.7).
- **Aviso de proceso**: la tabla de puertas vive hoy en **dos** documentos que no
  dicen lo mismo —la constitución 1.0.0 y `docs/spec-driven-development.md` §4—.
  La enmienda 1.0.1 que le da un solo dueño está en
  `docs/constitution-gates-single-source` y **sin fusionar**, a la espera del PR
  que §Gobernanza exige. Conviene cerrarla antes de que la spec cite puertas.

---

**Estado**: evaluación cerrada con veredicto **go** para la beta 2.
**Siguiente paso**: `/speckit-specify` con este traspaso como entrada.
