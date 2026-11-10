# Bug Assessment: el agente dice que pasa la conversación y no la pasa

- **Slug**: el-agente-dice-que-pasa-y-no-pasa
- **Created**: 2026-11-08
- **Source**: QA de Jemma's Hair (H-02) y certificación en staging del 2026-11-08
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

El agente dice «Te paso con alguien del equipo», pero en la consola no aparece «Necesita humano» ni
llega ningún aviso. La clienta se queda esperando a nadie.

## Symptom

Reproducido en staging (20:28 UTC): «me gustaría agendar para mañana lunes una manicura básica a
nombre de Lola Mento» → Ana: «Para agendar a nombre de Lola Mento, te paso con alguien del equipo».
`handler.turn_complete` con `intent: book` y `tool_calls: 0`. La Bandeja no tiene la conversación en
«Necesita humano» y la campana no tiene aviso.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/runtime/pipeline.py` — `_INTENT_CATEGORIES`: `escalate.escalate_to_human`
  solo está en `escalate`; `_filter_tools_for_intent` no la ofrece en `book`, `info`, `queue` ni
  `fallback`, aunque el agente la tenga en su lista blanca.

## Root Cause Hypothesis

Pasar a una persona se decide a menudo en mitad de una reserva o de una pregunta (una regla del
agente, algo que no puede hacer). El clasificador etiqueta bien el mensaje (`book`), pero el turno
no tiene la herramienta, y el modelo dice la frase que su texto le manda decir. Confianza: alta.

## Proposed Remediation

Ofrecer `escalate.escalate_to_human` en todas las intenciones cuando el agente la tiene. La lista
blanca sigue siendo el techo. Un freno para la frase sin la herramienta queda como mejora aparte.
