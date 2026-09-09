# Fase 0 — Investigación: el puesto de trabajo del teammate en la máquina del partner

**Rama**: `001-puesto-trabajo-partner` · **Fecha**: 2026-09-09 ·
**Spec**: [`spec.md`](./spec.md)

Resuelve las incógnitas del Contexto Técnico de [`plan.md`](./plan.md). Todo lo de
aquí sale de la evaluación ya cerrada
([`decision.md`](../../.specify/assessments/kirocrew-como-sustrato/decision.md)) o
de lectura del repo; **no se reabre nada que la evaluación ya decidiera**.

---

## D1 — Sustrato: KiroCrew `0.7.0` fijado a `37933a5`, con rueda construida por nosotros

- **Decisión**: se compone una «edición Auphere» sobre KiroCrew fijado a un commit.
  Como **no existe rueda pública**, la construimos nosotros desde ese commit y la
  publicamos en nuestro índice interno.
- **Razón**: `pypi.org/pypi/kirocrew` devuelve 404 y los releases de GitHub
  publican solo bundles de escritorio; el instalador oficial hace `git clone` +
  `pip install -e .`. Verificado en la evaluación.
- **Alternativas descartadas**: depender de una rueda pública (no existe);
  vendorizar el código en nuestro repo (es un fork disfrazado, y pierde el
  seguimiento aguas arriba, que es la única razón de usar el seam).
- **Consecuencia**: construir la rueda es **trabajo recurrente**, y va al plan como
  tarea de infraestructura, no como una línea en un fichero de dependencias.

## D2 — Composición por el seam CPP, sin tocar el núcleo

- **Decisión**: un paquete Python aparte registra el entry point
  `kirocrew.plugins` → `build_enterprise_context`, y compone con
  `dataclasses.replace` sobre `build_default_context(cfg, profile="enterprise")`.
- **Razón**: es el camino del fabricante —Amazon compone así su propia edición— y
  el spike 2 lo ejecutó: perfil `enterprise`, servidor MCP propio y fila de
  catálogo activos, el floor de seguridad intacto, y el clon del núcleo a **0
  archivos modificados**.
- **Alternativas descartadas**: herencia de `PlatformContext` (es un dataclass
  inmutable); parchear el núcleo (deja de ser composición y cambia el veredicto).
- **Invariante que el plan debe sostener**: si alguna tarea obliga a modificar un
  fichero del núcleo, se detiene y se replantea. Es la línea entre la opción A y un
  fork.

## D3 — Motor `claude`, sin kiro-cli

- **Decisión**: `agent.acp_backend=claude`, con
  `@agentclientprotocol/claude-agent-acp` `0.75.1` y el CLI `claude`.
- **Razón**: spike 1 — `doctor` no bloquea (`kiro-cli: ⏭ not found`,
  `claude-acp: ✅`), la sesión abre, llama herramientas y el gate de aprobación
  funciona en las dos direcciones.
- **Alternativas descartadas**: kiro-cli (dependencia que la evaluación demostró
  innecesaria y que ata a otro producto de Amazon).

## D4 — Contención del catálogo: envoltorio con `--strict-mcp-config` — **SIN VERIFICAR**

- **Decisión provisional**: `CLAUDE_CODE_EXECUTABLE` apunta a un envoltorio de la
  edición que añade `--strict-mcp-config` al CLI, de modo que el harness use
  **solo** los servidores que Crew le pasa en `session/new`.
- **Razón**: el CLI documenta el flag (*«Only use MCP servers from
  --mcp-config»*), y el punto de inyección existe. Ninguna de las dos cosas exige
  tocar el núcleo.
- **Estado**: **no verificado.** Falta comprobar que el adaptador tolera el
  envoltorio y que Crew sigue viendo sus propias herramientas.
- **Es la primera tarea del plan (`T001`), no la última.** Si falla, la edición
  tendría que intervenir el lanzamiento del harness — y eso sería lo primero que
  obligue a tocar el núcleo, con lo que se aplica el repliegue escrito en la
  evaluación (opción C sobre B) y esta spec se replantea antes de construir nada
  encima.
- **Alternativas si falla**: restringir el catálogo del lado de Crew (sin punto de
  extensión conocido); ejecutar el harness bajo un usuario dedicado sin
  `~/.claude.json` (no vale en la beta 2: la máquina es del partner).

## D5 — Superficie de aprobación de subagentes: la app de escritorio — **SIN VERIFICAR**

- **Decisión provisional**: la aplicación de escritorio se conecta como cliente de
  dashboard y es quien contesta la aprobación de `spawn`.
- **Razón**: la evaluación observó que el rechazo del spawn dice literalmente que
  *ninguna superficie podía contestar*, y que la única salida real de las cuatro
  que sugiere su mensaje de error es **conectar un cliente de dashboard**. Las
  otras tres (`approval_mode="auto"`, `hooks.auto_approve_subagent_spawn`,
  `hooks.auto_approve_sources`) **no existen en su código**: no se intentan.
- **Estado**: **no verificado**, y es el riesgo que la spec asume a propósito.
- **Es la segunda tarea del plan (`T002`).** Si falla, se retira el Requisito 11 y
  la beta 2 entrega ejecución de un solo agente.

## D6 — Aislamiento del sustrato: tres variables, puestas antes del primer arranque

- **Decisión**: el empaquetado fija `KIROCREW_HOME`, `KIRO_HOME` **y**
  `KIROCREW_WORKSPACE`, más `KIROCREW_TELEMETRY_DISABLED=1`, antes de la primera
  ejecución.
- **Razón**: `KIROCREW_HOME` **no** gobierna el workspace del agente —eso es
  `KIROCREW_WORKSPACE`, que por defecto cae en `~/workplace/kirocrew-workspace/`,
  fuera del data home—. Durante la evaluación el home real se materializó dos
  veces, una de ellas con un simple `--version`.
- **Alternativas descartadas**: fijar solo el data home (demostradamente
  insuficiente).

## D7 — Las aprobaciones durables ya existen: se reutilizan, no se inventan

- **Decisión**: la aprobación de argumentos (Requisito 2.5) y toda acción que toque
  a un cliente final (Requisito 7.1) usan el objeto durable que ya está en el repo,
  `companion.actions` — con `state_hash`, `status`, `decided_at`, `decided_by` y
  UPSERT idempotente.
- **Razón**: §IV pide exactamente eso y ya está construido y probado. Añadir un
  segundo mecanismo de aprobación sería complejidad que la spec no pidió.
- **Alternativas descartadas**: usar el gate del sustrato para lo que toca a un
  cliente final — es síncrono, vive en memoria y muere con el turno; §IV lo
  prohíbe.
- **Frontera**: el gate del sustrato se queda **solo** para lo que ocurre dentro de
  la máquina (Requisito 7.2).

## D8 — Techos de recursos: los ponemos nosotros

- **Decisión**: límite de reloj por ejecución y recogida del **árbol de procesos**
  al vencer el límite y al cerrar la sesión (Requisito 12).
- **Razón**: el propio arranque del sustrato avisa de que fuera de Linux no hay
  contención de fork-bomb ni de memoria, y la beta 2 corre en macOS o Windows.
  Además la evaluación observó en **todos** los turnos procesos hijos que
  sobreviven al teardown.
- **Alternativas descartadas**: confiar en cgroups (no existen en el destino);
  aceptar el riesgo y documentarlo (deja sin respuesta el caso límite del comando
  que no termina).

## D9 — Lo que se apaga el primer día

- **Decisión**: telemetría a cero; canal de WhatsApp del sustrato **desactivado**;
  cargador de apps **desactivado**; navegador y `computer_use` **fuera del catálogo
  y no cargables**.
- **Razón**: la telemetría viene encendida por defecto; su canal de WhatsApp usa un
  protocolo no oficial contra los ToS de Meta y nosotros tenemos el oficial en
  producción; instalar una app concede privilegios completos del proceso gateway; y
  encender navegador junto a ejecución local es la combinación que §III prohíbe sin
  pagar las guardas de las dos.
- **Consecuencia**: no basta con no ponerlos en la lista blanca — el plan incluye
  una comprobación de que no son alcanzables.

## D10 — Licencias

| Dependencia | Versión | Licencia | Párrafo que la permite |
|---|---|---|---|
| KiroCrew | `0.7.0` @ `37933a5` | Apache-2.0 | §2 *Grant of Copyright License*: licencia perpetua, mundial, irrevocable para reproducir, preparar obras derivadas y distribuir, en forma fuente u objeto |
| `@agentclientprotocol/claude-agent-acp` | `0.75.1` | Apache-2.0 | Ídem |

- **Obligaciones que el plan asume**: conservar el `NOTICE` (§4.d) y **no usar las
  marcas** — §6 *Trademarks* excluye expresamente los nombres comerciales del
  otorgamiento. Las marcas Kiro/Kiro Crew no están licenciadas, de ahí el
  rebranding de la superficie visible.
- **AGPL**: ninguna. §VIII satisfecho.

## D11 — Medidor

- **Decisión**: el consumo de modelo de las sesiones locales entra en el medidor
  que ya ve el partner. **No se factura reloj de máquina** en esta superficie.
- **Razón**: la máquina es del partner y ya está pagada — es la ventaja económica
  de la superficie `3a` frente a la `2`, donde los $121/mes/partner salen
  precisamente de facturar reloj.

## D12 — Dónde vive cada cosa

- **La edición** es un paquete Python aparte (requiere **Python ≥3.12**, que es lo
  que el sustrato exige). **No entra en `apps/api`**, que sigue en `>=3.11`: viaja
  con la aplicación de escritorio.
- **El plano de control** (lista blanca, presencia de dispositivo, aprobaciones,
  auditoría) vive donde ya vive todo lo demás: `apps/api`, con Alembic en
  `apps/api/alembic/versions/` — la última migración es `0105`.
- **Las herramientas `console.*`** llegan al agente por un servidor MCP de la
  edición, no por navegador (§VI).

---

## Incógnitas que quedan, y dónde se resuelven

| Incógnita | Se resuelve en |
|---|---|
| ¿Basta el envoltorio para contener el catálogo? | `T001`, antes de construir nada |
| ¿Puede la app de escritorio contestar la aprobación de spawn? | `T002`, antes de comprometer el Requisito 11 |
| Coste real de retirar las marcas de la superficie visible | Tarea de rebranding; la evaluación midió la superficie (catálogo inglés, empaquetado, constantes de ruta) pero no el trabajo |
| Certificados de firma y notarización | **Fuera de este plan**: tienen plazo de entrega y se piden aparte |
