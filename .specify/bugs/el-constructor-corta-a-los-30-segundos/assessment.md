# Bug Assessment: el constructor de agentes no termina nunca

- **Slug**: el-constructor-corta-a-los-30-segundos
- **Created**: 2026-11-04
- **Source**: Luis (sesión del 2026-11-04) y logs de staging
- **Verdict**: valid
- **Severity**: high

## Report

Luis pidió comprobar en los logs de staging si el constructor es efectivo.

## Symptom

`agent_draft` falló 8 de 8 veces en 7 días. Quien describe un agente acaba siempre en
«Desde una plantilla» o «En blanco»: el agente nunca sale de lo que se describió. El
constructor del cliente, con el mismo modelo, sí termina (9 de 12).

## Reproduction

Logs de `/nexus/staging/runner`, `da2485dd`, 2026-11-04, trabajo `6ce2adb8`:

1. 19:26:21 sale la llamada a `gpt-5.6-sol`.
2. 19:26:51 y 19:27:22, `Retrying request to /chat/completions`: el SDK la corta a los
   30 s y la repite dos veces.
3. 19:27:53, `jobs.agent_draft.unavailable why=provider_failed`, a los 91 957 ms.

No hay `llm.call_complete` ni `llm.attempt_failed`: `acomplete` no registra el fallo.

De los 8: 3 con este patrón (91 a 105 s, los de después de quitar el proxy), 2 de menos
de 1 s (`missing partner virtual key`, resuelto el 2026-11-03), 2 de unos 13 s sin causa
en los logs y 1 que llegó al tope de 180 s del trabajo.

## Root cause

`LiteLLMProvider.timeout_s = 30.0` vale para un turno de chat. El borrador es un JSON
largo, y `client_profile` mide unos 64 tokens/s: 764 tokens en 11,9 s. Inferido: el
borrador pide varios miles de tokens, así que no cabe. El SDK añade dos reintentos.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/jobs/handlers/agent_draft.py`, `default_complete`.
- `apps/worker/src/nexus_worker/runtime/llm.py`, `LiteLLMProvider.timeout_s`.
