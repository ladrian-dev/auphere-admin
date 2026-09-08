# Idea Intake: KiroCrew como sustrato del puesto de trabajo del teammate

- **Slug**: kirocrew-como-sustrato
- **Created**: 2026-09-08
- **Source**: https://github.com/kirodotdev/KiroCrew · clon local leído en `/Users/lmatos/Workspace/_oss-research/kirocrew` @ `37933a5`
- **Type**: exploration

## Idea (as captured)

Adoptar **KiroCrew** (Amazon, Apache-2.0) como el runtime que corre en la máquina
del partner (beta 2) y como gateway-por-partner en la nube (beta 5), en lugar de
construir esa mitad desde cero. Nexus se queda como plano de control y dueño de
todo lo que toca datos de cliente final.

La investigación completa está en la KB: `[[15-kirocrew-y-alternativas]]`
(`/Users/lmatos/Work/Auphere/teammates/15-kirocrew-y-alternativas.md`).

## Restated

¿Merece la pena componer una "edición Auphere" sobre un runtime de agentes
open source que ya tiene construido lo caro de nuestras betas 2 a 6, aceptando a
cambio la dependencia de un repositorio de Amazon de ocho semanas de vida?

## Origin & Context

- **Raised by**: Luis, 2026-09-08.
- **Trigger**: KiroCrew publica bajo Apache-2.0 un producto cuya tesis declarada
  (`TENETS.md`, tenet 7: *"Teammates, not tools. Agents have names, roles, and
  memory."*) es literalmente la de teammates, con el sandbox de SO, el
  empaquetado de escritorio firmado, el cron, el TaskRunner, los subagentes, la
  memoria con embeddings, la auditoría encadenada y el lanzador de EC2 ya hechos.
- **Restricción de partida**: la beta 1 **no** se toca. Vive en la superficie 0
  y se apoya en RLS, wallet, herramientas `console.*` y los 44 archivos de UI del
  companion. Esta evaluación es solo sobre las betas 2 y 5.

## Evidencia ya recogida (no hace falta repetirla)

| Hallazgo | Estado |
|---|---|
| Licencia Apache-2.0 pura; marcas Kiro/Kiro Crew **no** licenciadas | Verificado en `LICENSE`, `NOTICE`, `GOVERNANCE.md` |
| Mono-usuario por diseño (owner lock, token único de dashboard, cero noción de tenant) | Verificado en código y en `governance.md` |
| El supuesto mono-usuario **es cierto** en la máquina del partner; en la nube exige un gateway por partner | Análisis, coherente con la decisión 1b del 27-08 |
| Backend `claude` (`claude-agent-acp` + `@anthropic-ai/claude-agent-sdk`) es camino vivo en el build público | `docs/system-specs/modules/claude-code-provider.md` + `acp_backends.py` |
| `env = {**os.environ}` y el scrub solo quita `AWS_SECRET*`, `AWS_SESSION*`, `SSH_AUTH_SOCK`, `GNUPGHOME`, `GIT_ASKPASS` → `ANTHROPIC_API_KEY` pasa | `acp/client.py` + `sandbox.py` |
| Seam de extensión CPP con ~30 puntos, diseñado para "ediciones" que dependen de la rueda pública sin tocar el núcleo | `docs/system-specs/modules/platform-context.md` |
| Sus aprobaciones son un gate **síncrono dentro del turno** (300 s, deny-on-silence, en memoria), no un objeto de dominio durable | `messaging/approval.py` |
| Telemetría anónima **encendida por defecto**; canal de WhatsApp por protocolo no oficial (contra ToS de Meta); instalar una app = privilegios completos del proceso gateway | `beacon.py`, `whatsapp/__init__.py`, `apps.module_loader` |
| No existe base OSS multi-tenant con licencia que permita revenderla: Suna es Elastic License 2.0, Dify prohíbe multi-tenant, n8n es Sustainable Use | Licencias leídas archivo a archivo |

## First-Glance Unknowns — los tres spikes que deciden

- [NEEDS CLARIFICATION: **¿arranca y opera sin kiro-cli?** Instalar con
  `acp_backend="claude"` + `claude-agent-acp` + `ANTHROPIC_API_KEY` y abrir una
  sesión con herramientas, aprobación y subagente. El flujo de setup y `doctor`
  asumen kiro-cli; si lo bloquean, todo el camino se encarece. **Es la puerta.**]
- [NEEDS CLARIFICATION: **¿se compone una edición Auphere sin tocar el núcleo?**
  Paquete mínimo que registre un servidor MCP propio con tres herramientas
  `console.*` contra staging, un agente de catálogo, y telemetría a cero. Si hay
  que parchear el núcleo, es un fork disfrazado y cambia el veredicto.]
- [NEEDS CLARIFICATION: **¿cuánto pesa un gateway por partner?** RSS en reposo y
  con dos sesiones. Reciclan el backend a 500 MiB y cargan un GGUF de ~610 MB en
  proceso. Decide si la beta 5 son 121 $/mes/partner o bastante más, y si Fargate
  es viable.]
- [NEEDS CLARIFICATION: multi-seat dentro de un mismo partner (decisión 9: hilo
  privado por persona). KiroCrew no tiene equivalente. ¿Lo pone Nexus por
  delante, o hay que abrirlo en el gateway?]
- [NEEDS CLARIFICATION: rebranding — las marcas no están licenciadas. ¿Cuánto
  trabajo real es quitar "Kiro" de la UI, los paquetes y el data home
  (`~/.kiro/crew`)?]

## Restricciones que la evaluación no puede ignorar

- Constitución §VIII: la licencia se lee entera. Apache-2.0 pasa; el **NOTICE** hay
  que conservarlo y las marcas no se usan.
- Constitución §II: esto abre la superficie **3a** (y más tarde la **2**). El
  precio de entrada se paga completo.
- Constitución §III: KiroCrew trae navegador **y** shell. Encenderlos a la vez sin
  la contención y sin la regla de "lo leído es dato" está prohibido.
- Un spike **no se fusiona a `develop`** (`docs/spec-driven-development.md` §2).
