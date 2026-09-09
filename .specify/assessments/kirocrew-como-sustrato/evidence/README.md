# Evidencia de los tres spikes (2026-09-09)

Salida cruda de la sesión que ejecutó la etapa `research`. Se conserva porque
`research.md` la cita: sin ella, sus afirmaciones no serían verificables por nadie
más que por quien estuvo delante.

**Esto no es producto y no se ejecuta.** Un spike responde una pregunta y no
entrega código (`docs/spec-driven-development.md` §2). Aquí no hay nada
instalable: son logs y un apéndice que transcribe el instrumento de medida.

## Saneado aplicado

Dos sustituciones, y ninguna más:

- La ruta del directorio desechable → `$SPIKE`. Era una ruta larga y con el
  identificador de la sesión dentro.
- Cualquier cosa con forma de clave de API → `sk-ant-REDACTED`. Comprobado
  después: no queda ninguna (la clave usada fue de un solo uso y está revocada).

El contenido por lo demás está tal cual salió.

## Los ficheros

| Fichero | Qué demuestra |
|---|---|
| `doctor-1.log` | Spike 1. `kiro-cli: ⏭ not found` y `claude-acp: ✅` — kiro-cli ausente **no** bloquea |
| `chat-tool2.log` | Spike 1. Sesión con backend `claude`: lee un fichero, cuenta bien, nombra la herramienta |
| `chat-approval-deny.log` | Spike 1. El gate deniega en no interactivo y lo dice: *«needs approval, and this invocation cannot ask»* |
| `chat-approval-allow.log` | Spike 1. El gate pregunta en terminal, se aprueba con `a`, y el comando se ejecuta |
| `chat-tools-probe.log` | **El hallazgo.** El catálogo del agente incluye servidores MCP del usuario de la máquina (`chrome-devtools`, `higgsfield`) además de los 7 `mcp__kirocrew-core__spawn_*` de Crew |
| `chat-subagent2.log` | Spike 1. `spawn_run` falla sin gateway: `Connection refused` en `127.0.0.1:5476` |
| `chat-subagent3.log` | Spike 1. Con el gateway arriba, `spawn_run` devuelve id (`eeb9ffa2`) |
| `chat-subagent4.log` | Spike 1. `approval_mode` no existe en el esquema — uno de los tres remedios falsos |
| `notifications.jsonl` | Spike 1. El rechazo real del subagente: `❌`, *«no surface could show the approval prompt»*. Contrástese con el `✅` que mostró `spawn list` |
| `gateway.log` | Spikes 1 y 3. Arranque del gateway, sesiones ACP y el aviso de que no hay techos de recursos fuera de Linux |

## Lo que no se conservó, y por qué

- `security_events.jsonl` (el log encadenado por HMAC, 246 entradas): 196 KB que
  `research.md` no cita. Se comprobó que existe y que registra; no se guarda para
  no meter ruido que nadie referencia.
- Las mediciones de RSS del spike 3 no tienen log: se tomaron con `ps` en vivo y
  están transcritas en `research.md` con su desglose por proceso.
- El venv, el paquete instalado y el directorio desechable: eran efímeros por
  diseño (`KIROCREW_HOME`, `KIRO_HOME` y `KIROCREW_WORKSPACE` redirigidos fuera
  del home real, para no tocar la máquina).

---

## Apéndice — el instrumento del spike 2

Esto es lo que se instaló **aparte** de KiroCrew para comprobar si una edición se
compone sin parchear el núcleo. Se transcribe para que la prueba sea repetible; no
vive como paquete en este repo a propósito.

El seam es un grupo de entry points con un único punto. En `pyproject.toml`:

```toml
[project]
name = "auphere-edition"
version = "0.0.1"
requires-python = ">=3.12"

[project.entry-points."kirocrew.plugins"]
build_enterprise_context = "auphere_edition.edition:build_enterprise_context"
```

Y el módulo entero, que son dos clases y una función:

```python
from dataclasses import replace


class AuphereMcpTooling:
    def extra_mcp_servers(self):
        return {"auphere-console": {"command": "python3", "args": ["-c", "pass"], "env": {}}}

    def extra_skills(self):
        return []

    def extra_mcp_scopes(self):
        return []


class AuphereAgentCatalog:
    def builtin_agents(self):
        return [{"name": "auphere-catalogo", "description": "Agente de catálogo (spike)"}]


def build_enterprise_context(cfg):
    """`PlatformContext` es un dataclass inmutable: la vía es `replace`, no herencia."""
    from kiro_crew.platform.bootstrap import build_default_context

    base = build_default_context(cfg, profile="enterprise")
    return replace(
        base,
        profile="enterprise",
        mcp_tooling=AuphereMcpTooling(),
        agent_catalog=AuphereAgentCatalog(),
    )
```

Con eso instalado y `KIROCREW_PROFILE=enterprise`, el núcleo compuso la edición:

```
profile               : enterprise
mcp_tooling           : AuphereMcpTooling
agent_catalog         : AuphereAgentCatalog
servidores MCP extra  : ['auphere-console']
filas de catalogo     : ['auphere-catalogo']
security authority    : PolicyAuthority      <- el floor ADD-only, intacto
contract_version      : 1 == 1
```

Y `kirocrew doctor` lo reconoció solo: `edition: ✅ enterprise`.

**La comprobación que de verdad importa**: al terminar, el clon del núcleo seguía
en `37933a5` con `git status --porcelain` vacío. Cero archivos modificados.
