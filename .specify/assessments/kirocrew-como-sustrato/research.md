# Idea Research: KiroCrew como sustrato del puesto de trabajo del teammate

- **Slug**: kirocrew-como-sustrato
- **Created**: 2026-09-09
- **Evidence confidence (overall)**: medium-high — los spikes 1 y 2 son ejecución
  directa y reproducible; el spike 3 da orden de magnitud, no cifra de
  dimensionado (se midió en macOS, y el modelo de embeddings no se cargó).
- **Nota de KB que lo justifica**: `[[15-kirocrew-y-alternativas]]`
  (`/Users/lmatos/Work/Auphere/teammates/15-kirocrew-y-alternativas.md`)
- **Etapa anterior**: [`intake.md`](./intake.md)

> Esta etapa **recoge evidencia, no decide**. El veredicto es de
> `/speckit-assess-decide`.

---

## Los tres spikes, en una tabla

| Spike | Pregunta | Respuesta | Confianza |
|---|---|---|---|
| **1 — la puerta** | ¿Arranca y opera sin kiro-cli? | **Sí.** Instala, `doctor` no bloquea, abre sesión, llama herramientas y pasa por el gate de aprobación en ambos sentidos. El subagente se lanza pero lo rechaza una **segunda** aprobación que el CLI no puede contestar — y eso no depende del backend | alta |
| **2 — la edición** | ¿Se compone sin tocar el núcleo? | **Sí.** Un paquete aparte con un entry point compuso la edición: `profile=enterprise`, servidor MCP propio y fila de catálogo activos, con el núcleo a **0 archivos modificados** | alta |
| **3 — el peso** | ¿Cuánto pesa un gateway por partner? | **511 MiB con dos sesiones**, de los que el gateway propio son 49. El coste lo domina el binario `claude` (~156 MiB por sesión). Sin el GGUF cargado | media |

---

## Montaje medido (para reproducirlo)

Todo en un directorio desechable, con `KIROCREW_HOME`, `KIRO_HOME` y
`KIROCREW_WORKSPACE` redirigidos y `KIROCREW_TELEMETRY_DISABLED=1` puesto **antes
del primer arranque**. Sin `curl | sh` y sin instalar nada global.

| Pieza | Versión | Licencia |
|---|---|---|
| KiroCrew | `0.7.0` @ commit `37933a5` (clon local) | Apache-2.0 |
| `@agentclientprotocol/claude-agent-acp` | `0.75.1` (npm, local al spike) | Apache-2.0 |
| `claude` CLI | `2.1.224` (ya en la máquina) | — |
| CPython | 3.12.12 · Node 24.11.1 | — |

---

## Data & Constraints

### Spike 1 — la puerta está abierta

- **`doctor` no bloquea por kiro-cli**: `kiro-cli: ⏭ not found (the default agent
  backend)` y `claude-acp: ✅ resolved off PATH`. Sale con código 1, pero por
  `ffmpeg` y las dependencias de voz — nada que ver con el backend.
  — [fuente: ejecución, `logs/doctor-1.log`] (confianza: alta)
- **Herramienta**: con `agent.acp_backend=claude`, el agente leyó un fichero del
  workspace, contó bien y nombró la herramienta (`Read`).
  — [fuente: ejecución] (confianza: alta)
- **Aprobación, las dos direcciones.** No interactivo (`chat -m`) deniega y lo
  dice: `Denied automatically: … needs approval, and this invocation cannot ask`.
  En terminal (conducido por pty) el gate pregunta
  `[a] allow once [d] deny (default):`, se aprueba, y el comando **se ejecuta** —
  verificado con un fichero canario que solo podía escribir una ejecución
  aprobada. — [fuente: ejecución] (confianza: alta)
- **Las herramientas de Crew SÍ llegan al harness.** El riesgo que marcaba
  `ACP_BACKENDS_SESSION_MCP_ARRAY` —que el array por sesión llegara vacío y Crew
  quedara mudo— **no se materializa**: las 7 `mcp__kirocrew-core__spawn_*` están
  presentes y el gate las intercepta. — [fuente: ejecución] (confianza: alta)
- **El subagente arranca pero no corre**: `spawn_run` devuelve id (`eeb9ffa2`) y
  el gateway lo rechaza — *«the spawn approval prompt reached no surface that
  could answer it (no dashboard client is connected, parent=cli_chat)»*. Es
  arquitectura de aprobación, **no** una consecuencia de prescindir de kiro-cli.
  — [fuente: `home/gateway.log`, `home/notifications.jsonl`] (confianza: alta)

### Spike 2 — se compone sin tocar el núcleo

El seam es un grupo de entry points `kirocrew.plugins` con **un** punto
(`build_enterprise_context`), cargado cuando el perfil no es `standalone`.
`PlatformContext` es un dataclass inmutable, así que la vía es `dataclasses.replace`
sobre `build_default_context(cfg, profile="enterprise")` — sin herencia y sin
parchear nada.

Con un paquete de ~60 líneas instalado aparte, el núcleo compuso:

```
profile               : enterprise
mcp_tooling           : AuphereMcpTooling
agent_catalog         : AuphereAgentCatalog
servidores MCP extra  : ['auphere-console']
filas de catalogo     : ['auphere-catalogo']
security authority    : PolicyAuthority     <- el floor ADD-only, intacto
contract_version      : 1 == 1
```

Y `kirocrew doctor` lo reconoce solo: `edition: ✅ enterprise`.

**La comprobación que importa**: al terminar, el clon del núcleo sigue en
`37933a5` con **0 archivos modificados**. No es un fork disfrazado.
— [fuente: ejecución + `git status --porcelain`] (confianza: alta)

**Pero la premisa del spike era falsa y hay que corregirla**: el intake decía
«un paquete que dependa de **la rueda pública**». No existe rueda pública.
`pypi.org/pypi/kirocrew` devuelve 404 (y `kiro-crew`, y `kiro_crew`), y los
releases de GitHub publican **solo** bundles de escritorio
(`.dmg/.exe/.deb/.rpm/AppImage`) — ningún `.whl` ni sdist. El instalador oficial
hace `git clone` + venv + `pip install -e .`. Una edición Auphere dependería de
un wheel **que nosotros construimos** desde un commit fijado, que es trabajo
recurrente de mantenimiento, no una dependencia declarada.
— [fuente: PyPI 404, API de releases de GitHub, `install.sh`] (confianza: alta)

### Spike 3 — el peso, con los dos caveats por delante

Árbol del gateway con dos sesiones vivas, PIDs deduplicados:

| Grupo | RSS | Procesos |
|---|---|---|
| Crew | **392 MiB** | gateway Python 49 · dos `claude` (155 + 157) · dos adaptadores node (15 + 17) |
| MCP heredados del usuario | **119 MiB** | 10 procesos: `chrome-devtools-mcp` y `@playwright/mcp`, duplicados por sesión |
| **Total** | **511 MiB** | 15 |

Lo que enseña la estructura, que vale más que el total: **el gateway propio es
barato (49 MiB) y el coste es por sesión**, ~156 MiB del binario `claude` más
~16 del adaptador. Un gateway por partner escala con sesiones concurrentes, no
con el hecho de existir.

Dos caveats que impiden usar esta cifra para dimensionar:

1. **Medido en macOS.** El RSS de macOS no es comparable con el límite de memoria
   de un contenedor Linux, y el propio arranque avisa de que no hay techos:
   *«cgroup v2 scope enforcement unavailable (not Linux); agent subprocess
   fork-bomb / memory-DoS ceilings are NOT enforced on this host»*. **Para decidir
   sobre Fargate hay que repetir esto en Linux.**
2. **El GGUF de ~610 MB no se cargó** — no se ejercitó la memoria vectorial. La
   cifra de arriba es un piso, no un techo.

Con eso: **los 121 $/mes/partner de [[14-mvp-y-fases]] §1.1 hay que rehacerlos**,
y la pregunta de Fargate sigue abierta por falta de una medida en Linux.

---

## Evidence Against the Idea

Esta sección es obligatoria y aquí hay material de verdad. Lo de abajo no mata el
camino A, pero es el precio que nadie había contado.

1. **El backend `claude` hereda los servidores MCP del usuario de la máquina, y
   el gateway lanza sus procesos.** Es el hallazgo más grave de la sesión.
   Evidencia doble: el agente listó `chrome-devtools` y `higgsfield` —
   exactamente los cuatro declarados a nivel raíz en `~/.claude.json`
   (`chrome-devtools`, `higgsfield`, `magic`, `playwright`) — y el árbol del
   gateway contenía sus procesos vivos. Crew pasa su propio array en
   `session/new`; el CLI `claude` **suma** los del usuario, y no se encontró en
   Crew nada que lo restrinja.
   Choca de frente con tres cosas nuestras: §I (*«la lista blanca de herramientas
   es exhaustiva y por tenant: no hay globales»*), §III (el agente acabó con
   `shell` **y** dos navegadores disponibles a la vez, que es justo el orden que
   la constitución prohíbe sin pagar las guardas de ambos) y la restricción
   *«ninguna credencial de cliente final entra nunca en el ambiente de un
   agente»* — `higgsfield` expone `balance` y `confirm_billing_purchase`.
   **Dónde duele, que no es donde primero parece.** Se observó en una máquina de
   desarrollo con Claude Code instalado y configurado — un host que **no**
   representa el despliegue de la beta 5: un contenedor nuestro corre como usuario
   dedicado y no tiene `~/.claude.json`, así que ahí el catálogo debería salir
   limpio (sin verificar). Donde sí duele es en la **beta 2**, que corre en la
   máquina del partner: ahí ese fichero es del partner y puede contener cualquier
   cosa.
   **Y hay mitigación que no exige tocar el núcleo**: el CLI acepta
   `--strict-mcp-config` (*«Only use MCP servers from --mcp-config»*), y el
   adaptador recibe el binario por `CLAUDE_CODE_EXECUTABLE` — que puede apuntar a
   un envoltorio de la edición que añada el flag. Sin verificar todavía.
   — [fuente: ejecución + `~/.claude.json` + árbol de procesos + `claude --help`]
   (confianza: alta en el hallazgo, media en el alcance, **sin verificar** la
   mitigación)
2. **Aislarlo necesita tres variables, no una.** `KIROCREW_HOME` no gobierna el
   workspace del agente: eso es `KIROCREW_WORKSPACE`, y por defecto cae en
   `~/workplace/kirocrew-workspace/<canal>/`, fuera del data home. Durante el
   spike se materializó dos veces en el home real (una de ellas con un simple
   `--version`, que ya crea el data home) y hubo que limpiarlo a mano. Cualquier
   empaquetado nuestro tiene que fijar las tres. — [fuente: ejecución,
   `config/paths.py`, `config/loader.py:455-474`] (confianza: alta)
3. **Sus mensajes de error recomiendan remedios que no existen.** El rechazo del
   spawn sugiere tres salidas: `approval_mode="auto"` (no está en
   `SPAWN_RUN_SCHEMA`), `hooks.auto_approve_subagent_spawn` (`config set` lo
   rechaza: *Unknown key*) y `hooks.auto_approve_sources` (no aparece en la
   config). De las cuatro, la única real es conectar un cliente de dashboard.
   — [fuente: ejecución + `validation.py:1010`, `config/sections.py`] (confianza: alta)
4. **`spawn list` informó `✅` de un subagente rechazado**, cuya notificación real
   dice `❌` con el motivo. Para nosotros eso es §V — la pantalla no miente — y si
   adoptamos esto, es una pantalla nuestra la que mentiría.
   — [fuente: `spawn list` vs `notifications.jsonl`] (confianza: alta)
5. **Procesos hijos sobreviven al teardown de cada turno**: *«Retained tracking
   for N live child PID(s) that survived teardown; orphan sweep will reap them»*
   apareció en todos los turnos. Implica que el RSS de un gateway de larga vida
   crece con el número de **turnos**, no con el de sesiones concurrentes, hasta
   que el barrendero pasa. Para un gateway por partner de vida larga, eso hay que
   medirlo. — [fuente: todos los logs de sesión] (confianza: media — observado
   siempre, no medido en el tiempo)
6. **Sin techos de recursos fuera de Linux**, dicho por el propio arranque (ver
   caveat 1 del spike 3). La beta 2 corre en el portátil del partner, que será
   macOS o Windows: ahí no hay contención de fork-bomb ni de memoria.
   — [fuente: aviso de `kiro_crew.sandbox`] (confianza: alta)

Lo que **no** encontramos en contra, y conviene decirlo porque era un miedo del
intake: el seam aguantó (spike 2), el floor de seguridad ADD-only quedó intacto,
el `contract_version` coincide, y las herramientas de Crew llegan al harness.

---

## Prior Art

- El propio Amazon compone su «enterprise companion edition» por este mismo seam
  — el spike 2 usó el camino del fabricante, no un atajo. Eso es a favor de su
  estabilidad, y a la vez el recordatorio de que el OSS es el núcleo de un
  producto comercial de AWS. — [fuente: `platform-context.md`] (confianza: alta)
- La tabla de licencias de `[[15-kirocrew-y-alternativas]]` §5 sigue en pie y no
  se reabre aquí: no hay base OSS multi-tenant que permita revenderla.

---

## Gaps & Open Questions

- [NEEDS CLARIFICATION: **¿basta un envoltorio con `--strict-mcp-config` para que
  el catálogo salga solo con las herramientas de Crew?** El flag existe y el punto
  de inyección (`CLAUDE_CODE_EXECUTABLE`) también; falta comprobar que el
  adaptador lo tolera y que Crew sigue viendo sus propias herramientas. Si NO
  basta, la edición tendría que intervenir el lanzamiento del harness, y eso sería
  lo primero que obligue a tocar el núcleo — estrechando el spike 2.
  **Diferido por decisión de Luis (2026-09-09): entra como primera tarea del plan
  de la beta 2, no como continuación de este research.**]
- [NEEDS CLARIFICATION: y la variante del mismo problema en la **beta 2**, donde el
  `~/.claude.json` es del partner y no nuestro: un envoltorio lo tapa, pero hay que
  decidir si el partner puede añadir sus propios servidores a propósito.]
- [NEEDS CLARIFICATION: **RSS en Linux, con el GGUF cargado y con N sesiones.**
  Sin esto no hay cifra de Fargate ni precio por partner. Es el spike 3 otra vez,
  en la plataforma correcta.]
- [NEEDS CLARIFICATION: **¿crece el RSS con los turnos?** Medir un gateway a lo
  largo de muchos turnos, por los procesos que sobreviven al teardown.]
- [NEEDS CLARIFICATION: **el coste real de rebranding**, que el intake ya
  preguntaba y este research no ha tocado: las marcas no están licenciadas y
  «Kiro» aparece en la UI, en los paquetes (`kiro_crew`), en el data home
  (`~/.kiro`), en el workspace (`~/workplace/kirocrew-workspace`) y en los
  mensajes de error.]
- [NEEDS CLARIFICATION: **multi-seat dentro de un partner** (decisión 9). Sigue
  sin equivalente y este research no lo ha explorado.]
- [NEEDS CLARIFICATION: **¿subagentes sin dashboard?** Si la beta 5 es un gateway
  headless, hoy no puede lanzar subagentes. Hay que ver si un cliente de la API
  basta, o si hace falta una superficie de aprobación nuestra.]

---

## Sources

Todo es ejecución local o lectura de código. No se consultó ninguna web fuera de
los dos registros de paquetes.

- Clon `kirodotdev/KiroCrew` @ `37933a5`, en `/Users/lmatos/Workspace/_oss-research/kirocrew`
  — `src/kiro_crew/{acp_backends.py,acp/client.py,cli_chat.py,cli_doctor.py,cli_setup.py,validation.py,beacon.py}`,
  `src/kiro_crew/config/{paths.py,loader.py,sections.py}`,
  `src/kiro_crew/platform/{bootstrap.py,context.py,defaults.py}`,
  `docs/system-specs/modules/platform-context.md`
- `https://pypi.org/pypi/kirocrew/json` (host: pypi.org, política: registro de
  paquetes, consulta de disponibilidad) → **404**
- `https://api.github.com/repos/kirodotdev/KiroCrew/releases` (host: api.github.com,
  política: allowlisted) → solo bundles de escritorio
- `https://registry.npmjs.org/@agentclientprotocol/claude-agent-acp` (host:
  registry.npmjs.org, política: registro de paquetes) → `0.75.1`, Apache-2.0
- **Salida cruda de la sesión, conservada en [`evidence/`](./evidence/)** — con su
  [`README`](./evidence/README.md) explicando qué demuestra cada fichero, qué
  saneado se aplicó y qué no se guardó. Incluye el instrumento del spike 2
  transcrito, para que la prueba sea repetible.

---

**Siguiente etapa**: `/speckit-assess-define slug=kirocrew-como-sustrato`
