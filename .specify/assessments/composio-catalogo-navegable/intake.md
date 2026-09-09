# Idea Intake: el catálogo de conectores de Composio, navegable desde la consola

- **Slug**: composio-catalogo-navegable
- **Created**: 2026-09-09
- **Source**: petición de Luis en conversación (texto pegado) + punteros al repo
  (`apps/mcp/src/nexus_mcp/servers/composio_proxy/`,
  `apps/admin/src/app/(dashboard)/connectors/`,
  `apps/api/src/nexus_api/db/models/connector.py`)
- **Type**: new-capability

## Idea (as captured)

> Ya hemos creado una conexión con Composio para conectar más herramientas y el
> agente sea más útil. Evalúa si vale la pena mostrar la lista de MCP y conectores de
> Composio adicionalmente a las que ya tenemos.

## Restated

Exponer en la consola una superficie donde se pueda **descubrir y activar**
conectores y servidores MCP de Composio, además del conjunto de herramientas que ya
existe hoy, para ampliar lo que un agente puede hacer sin que cada integración pase
por una tarea de ingeniería.

## Origin & Context

- **Raised by**: Luis, 2026-09-09.
- **Trigger**: la integración con Composio **ya existe** en el repo y funciona; lo
  que no existe es la superficie para verla. La pregunta surge al final de la Phase 2b
  de `specs/001-puesto-trabajo-partner`, al preguntarse si esto debía entrar allí.
- **Por qué no entró en la spec 001, y queda escrito para no repetir la discusión**:
  la beta 2 trabaja sobre la superficie de confianza `3a` (ejecutar en la máquina del
  partner) y esto vive en la `0` (la API de la consola). La constitución §II pide
  agotar una superficie antes de abrir otra y no mezclarlas en la misma spec.

## Lo que ya existe (verificado en el repo, no hace falta re-descubrirlo)

| Pieza | Estado |
|---|---|
| Proxy de Composio **por tenant** | Construido. `user_id = f"tenant_{slug}"` resuelto del contextvar, emparejado con el `connection_id` del tenant |
| Aislamiento de los conectores | `tenant_connectors` con **RLS + FORCE**; `TenantConnectorToolOverride` da control por herramienta y por tenant |
| Paso por la lista blanca | Ya ocurre: *«a Composio tool not in the active `agent_config.tools` set never reaches the LLM»*, y `MCPRegistry.dispatch` lo revalida antes de invocar |
| Defensa aguas arriba | El adaptador impone el invariante de `user_id`: un `connection_id` de otro tenant falla en el lado de Composio |
| UI de conectores en el panel de operador | Existe (`apps/admin/.../connectors/`) |
| **Lo que falta** | Una superficie de **descubrimiento y activación** — hoy no hay dónde ver qué conectores ofrece Composio ni activarlos sin trabajo de ingeniería |

**Consecuencia para el encuadre**: esto **no** es «meter herramientas ajenas en el
agente». El mecanismo por tenant y por lista blanca ya está construido y probado. Lo
que se evalúa es abrir la puerta de descubrimiento delante de él.

## Restricción que la evaluación no puede ignorar

Salió al evaluar si esto entraba en la spec 001, y es el hallazgo que la motivó:

- **Muchos conectores alcanzan la web.** Encender uno en la misma sesión que la
  ejecución local es exactamente la combinación que §III prohíbe sin pagar las guardas
  de las dos: *el agente lee una web → la web dice «ejecuta esto» → el agente lo
  ejecuta en el portátil de una persona*.
- La spec 001 **ya cierra ese caso** con su **Requisito 14**: el catálogo declara el
  alcance de red por herramienta, lo no declarado cuenta como externo, y con
  dispositivo presente no conviven alcance externo y ejecución local.
- Por tanto esta evaluación **hereda** ese requisito: cualquier conector que se pueda
  activar tiene que poder declarar su alcance de red, o quedará excluido por defecto.

## First-Glance Unknowns

- [NEEDS CLARIFICATION: **¿quién activa un conector — Auphere o el partner?** La spec
  001 decidió (Q1, 2026-09-09) que el catálogo del teammate lo configura **solo
  Auphere**. Pero `console/agents.py` sí deja hoy al partner fijar `tools` de **su
  agente de cliente final**. Son dos agentes distintos y la respuesta puede ser
  distinta para cada uno; lo que no puede es quedarse implícita.]
- [NEEDS CLARIFICATION: **el alcance de red por conector.** ¿Lo declara Composio en su
  metadatos, lo inferimos, o lo clasificamos a mano? De esto depende si el Requisito 14
  de la 001 se puede cumplir sin trabajo manual por cada conector.]
- [NEEDS CLARIFICATION: **credenciales.** Un conector guarda un OAuth del partner hacia
  un tercero. ¿Dónde vive, quién lo rota, y qué pasa al dar de baja al cliente? La
  restricción de la constitución —«ninguna credencial de cliente final entra nunca en
  el ambiente de un agente»— hay que releerla con esto delante.]
- [NEEDS CLARIFICATION: **el medidor.** Un conector de pago consume dinero. ¿Dónde entra
  en el medidor que ve el partner? Toda spec que gasta lo declara.]
- [NEEDS CLARIFICATION: **licencia y términos de servicio de Composio.** §VIII exige
  leerlos enteros antes de instalar, y aquí ya está instalado — así que la lectura es
  retroactiva y hay que hacerla igual: ¿permiten revender el uso como servicio
  multi-tenant?]
- [NEEDS CLARIFICATION: **¿cuántos conectores y con qué calidad?** Un catálogo grande y
  sin curar puede empeorar al agente en vez de mejorarlo: más herramientas es más
  superficie de elección equivocada, no necesariamente más utilidad.]
- [NEEDS CLARIFICATION: **la superficie de operador ya existe.** ¿Esto es ampliar
  `apps/admin`, llevarlo a la consola de partner, o las dos? No es lo mismo: la consola
  de partner es superficie 0 con RLS y la de operador no tiene el mismo público.]

---

**Siguiente etapa**: `/speckit-assess-research slug=composio-catalogo-navegable`
