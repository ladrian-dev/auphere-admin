# T001 — ¿se puede contener el catálogo de herramientas? · **PASA**

Ejecutado el **2026-09-09**. Verifica el Requisito 5 y cierra la decisión D4 de
[`../../research.md`](../../research.md), que entró como *provisional, sin verificar*.

## Montaje

Directorio desechable (`$SPIKE`) con `KIROCREW_HOME`, `KIRO_HOME` y
`KIROCREW_WORKSPACE` redirigidos y la telemetría desactivada **antes del primer
arranque**. El clon del sustrato **no se tocó**: se exportó el commit fijado con
`git archive` y se construyó una rueda desde esa copia, así que el clon terminó —y
empezó— en `37933a5` con **0 archivos modificados**.

| Pieza | Versión | Licencia |
|---|---|---|
| KiroCrew | `0.7.0` @ `37933a5`, rueda construida localmente | Apache-2.0 |
| `@agentclientprotocol/claude-agent-acp` | `0.75.1` | Apache-2.0 |
| `claude` CLI | `2.1.224` | — |
| CPython | 3.12.12 · Node 24.11.1 | — |

La máquina era **sucia a propósito**: `~/.claude.json` declaraba cuatro servidores
a nivel raíz (`chrome-devtools`, `higgsfield`, `magic`, `playwright`). Sin ese caso
sucio la prueba no demostraría nada.

## El resultado

| | Sin envoltorio | Con envoltorio |
|---|---|---|
| Servidores ajenos en el catálogo | `chrome-devtools`, `higgsfield`, `playwright` | **ninguno** |
| Procesos ajenos vivos bajo el gateway | **4** | **0** |
| Herramientas propias de Crew | presentes | **presentes** (74 de `core` + `cron`) |

Las dos mitades importan. Que el agente deje de listarlas no bastaba: **sus
procesos tampoco arrancan**. Y Crew sigue viendo las suyas, que era la forma en que
esto podía fallar — si el flag hubiera restringido también las de Crew, la edición
habría tenido que intervenir el lanzamiento del harness, y eso es lo primero que
obligaría a tocar el núcleo.

## Por qué funciona

`argv-del-adaptador.log` lo enseña, y coincide con la lectura del SDK
(`sdk.mjs:100`):

```
if (K && Object.keys(K).length > 0) Z.push("--mcp-config", me({mcpServers: K}));
...
if (ne) Z.push("--strict-mcp-config");
```

Los `mcpServers` que Crew envía en `session/new` **acaban serializados en
`--mcp-config`**. Por eso `--strict-mcp-config` restringe *a ese conjunto* en vez de
vaciarlo: el conjunto es justamente el de Crew.

Dato secundario, para cuando se implemente: **el SDK sabe empujar el flag por sí
mismo**. Existe una segunda vía si algún día el adaptador expone esa opción; el
envoltorio es la que no toca el núcleo hoy.

## Los ficheros

| Fichero | Qué demuestra |
|---|---|
| `doctor-t001.log` | El primer arranque con las tres variables: `kiro-cli: ⏭ not found`, `claude-acp: ✅`. El home real no se materializó |
| `A-baseline.log` | **El hallazgo, reproducido.** El catálogo incluye `mcp__playwright__*`, `mcp__higgsfield__*` y `mcp__chrome-devtools__*`. El turno declara *«MCP tool inventory: 12 loaded, 253 deferred»* |
| `B-wrapper.log` | Con envoltorio: los únicos prefijos son `mcp__kirocrew-core__` y `mcp__kirocrew-cron__` |
| `argv-del-adaptador.log` | El `argv` real que recibe el binario: `--mcp-config` presente, y el envoltorio anteponiendo `--strict-mcp-config` |
| `sample-process-tree.py` | El instrumento del recuento de procesos, que cuenta **solo descendientes del gateway** |

## Una medición que hice mal antes de hacerla bien

El primer recuento de procesos contaba coincidencias en **toda la máquina** y dio
18 frente a 17 — ruido de la sesión de Claude Code del propio operador, que tenía
esos mismos servidores vivos. Corregido a descendientes del gateway, la diferencia
real es **4 frente a 0**. Se deja escrito porque el instrumento importa tanto como
el número, y quien repita esto puede caer en lo mismo.

## Lo que este spike NO demuestra

- **Nada sobre `T002`** (la app de escritorio como superficie de aprobación de
  subagentes). Sigue sin verificar y sigue siendo el otro riesgo asumido.
- Reapareció el hallazgo 5 del research —*«Retained tracking for 1 live child PID(s)
  that survived teardown»*— en las dos pasadas. Es materia del Requisito 12, y aquí
  solo se observa.
- El aviso de que **fuera de Linux no hay techos de recursos** salió otra vez, tal y
  como el Requisito 13.5 y la restricción del plan anticipaban.
- La clave usada fue de un solo uso y se revoca al cerrar.
