# Bug Assessment: editar la ficha borra lo que sabe el agente

- **Slug**: la-ficha-borra-lo-que-sabe-el-agente
- **Created**: 2026-10-29
- **Source**: auditoría del constructor (`research/2026-10-29-auditoria-del-constructor/_index.md`, fallo 1)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

Al auditar el constructor tras fusionar la spec 047, la recompilación por
cambios de la ficha tira la capa propia del agente («Lo que sabes como este
agente»: sus preguntas frecuentes propias, requisito 22) del prompt activo.

## Symptom

Un agente estructurado publicado lleva en su prompt sus preguntas frecuentes
propias. En cuanto alguien guarda cualquier cosa en la ficha del negocio (un
horario, un servicio), el prompt activo de todos los agentes se recompila y las
pierde: el agente deja de saberlas sin que nadie lo haya tocado. Lo esperado: la
recompilación cambia solo el bloque de la ficha.

## Reproduction

Con el compilador real (`recompile_probe.py`, en el scratchpad de la sesión):

1. Un AgentSpec estructurado con `services.faqs = [{"q": "¿Pedido mínimo?", "a": "50 ramos."}]`.
2. `published = compile_spec(spec, facts)` → contiene «Pedido mínimo».
3. Lo que hace `compile_version` al cambiar la ficha:
   `compile_prompt(instructions_of(published), facts)` → **no** contiene «Pedido mínimo».

Salida: `own FAQ in published prompt: True` / `own FAQ after a ficha edit: False`.

## Suspected Code Paths

- `apps/api/src/nexus_api/services/business/compilation.py:267` `compile_version` — recompila con `compile_prompt(instructions_of(cfg.system_prompt_rendered), facts)`.
- `compilation.py:147` `instructions_of` — corta en la **última** marca de la ficha y tira todo lo que va detrás.
- `apps/api/src/nexus_api/services/agent_spec/compiler.py:162` `compile_spec` — pone la capa del agente (`_agent_layer`) **después** de la ficha, así que `instructions_of` la corta.
- `apps/api/src/nexus_api/api/console/agent_spec_drafts.py:101` `write_spec` — compila bien (`compile_spec(spec, facts)`); el borrador sale correcto y el fallo aparece solo en la recompilación de la versión activa.

## Root Cause Hypothesis

`compile_version` es anterior al AgentSpec: supone que el prompt es
«instrucciones + ficha» y que basta con cambiar la cola. Con la 047 el prompt es
«cuerpo + ficha + capa del agente», y la cola ya no es solo la ficha. Confianza:
**alta** (reproducido).

## Proposed Remediation

**Preferred**: si la versión tiene AgentSpec (`cfg.spec`), recompilarla desde él,
igual que `write_spec`: `compile_spec(AgentSpec.model_validate(cfg.spec), facts)`.
Mismas entradas, mismos bytes (requisito 16.2). Las versiones sin AgentSpec
(anteriores a la 047 y aún sin migrar) siguen con `compile_prompt(instructions_of(…))`,
que para ellas es correcto.

**Alternative**: hacer que `instructions_of` conserve lo que va detrás de la ficha.
Descartada: sigue dependiendo de cortar texto, y un cambio de orden en
`compile_spec` volvería a romperlo.

## Test plan

- Unitario: un AgentSpec estructurado con FAQ propias; `compile_version` tras
  cambiar la ficha conserva la capa del agente y cambia el bloque de la ficha.
- Unitario: el prompt que deja `compile_version` es byte a byte el que da
  `write_spec` con la misma ficha.
- Unitario: una versión en modo «instrucciones» sin AgentSpec sigue compilando
  exactamente igual que hoy (requisito 16.4).
