# Bug Assessment: en staging, el constructor y sus vecinos no llegan al modelo

- **Slug**: el-constructor-no-llega-al-modelo-en-staging
- **Created**: 2026-10-29
- **Source**: auditoría del constructor (`research/2026-10-29-auditoria-del-constructor/_index.md`, fallo 9)
- **Verdict**: valid (por lectura de código; sin reproducir en vivo)
- **Severity**: critical (en staging)

## Report (verbatim or summarized)

Staging obliga a pasar por el proxy LiteLLM (`NEXUS_LLM_PROXY_REQUIRED=true`), que
exige saber de qué partner es cada llamada. Varias llamadas a modelos nuevas de la
047 no abren ese ámbito.

## Symptom

En staging, «Generar borrador», la lectura de la web, el constructor del cliente,
las pruebas (el juez), el copiloto y las correcciones fallan siempre
(`builder_unavailable`, `extract_failed`), aunque el modelo exista. En producción
no pasa, porque no hay proxy.

## Reproduction

Por lectura: `WK/runtime/llm.py:1000-1016` `_proxy_kwargs` llama a
`require_current_llm_proxy_partner()` si `proxy_required()`, y estas llamadas no
tienen el partner atado.

## Suspected Code Paths

| # | Llamada | Dónde | De dónde sale el partner |
|---|---|---|---|
| a | constructor del agente | `apps/worker/src/nexus_worker/jobs/handlers/agent_draft.py:61-79` | `ctx.tenant_id` → `partner_id_for_tenant_standalone` |
| b | constructor del cliente | `jobs/handlers/client_builder.py:36-49` | ídem |
| c | extracción de la lectura | `jobs/handlers/client_read.py:82-101` | ídem |
| d | visión de documentos | `jobs/handlers/business_sources.py:66-102` | ídem |
| e | juez de las pruebas | `jobs/handlers/agent_tests.py:63-79` | ídem |
| f | juez dentro de publicar | `jobs/handlers/agent_publish.py:88-103` | ídem |
| g | sugerencias semanales | `streams/weekly_suggestions_cron.py:52-68` | `due.partner_id` |
| h | copiloto | `apps/api/src/nexus_api/api/console/agent_copilot.py:46-68` | `scope.principal.partner.id` |
| i | `paraphrase` | `apps/api/src/nexus_api/services/improvement/paraphrase.py:52-73` | `conversation.tenant_id` → `partner_id_for_tenant` |
| j | evaluación y calibración del operador | `apps/api/src/nexus_api/api/admin/sector_tests.py:106-121, 223-250` | ninguno: lo paga Auphere |
| k | calificador de resultados | `apps/worker/src/nexus_worker/streams/grade_consumer.py` | tenant → partner |

## Root Cause Hypothesis

`jobs/consumer.py` no ata ningún partner, y cada manejador nuevo llama al modelo
sin abrir `llm_proxy_partner_scope`. Las pruebas corren sin proxy, así que nada lo
detecta. Confianza: **alta**.

## Proposed Remediation

**Preferred**:
- El consumidor de trabajos (`jobs/consumer.py`) abre `llm_proxy_partner_scope`
  con el partner del cliente del trabajo antes de llamar al manejador. Cubre a–f de
  una vez y a cualquier trabajo futuro.
- g, h, i y k abren el ámbito donde ya tienen el partner.
- j: un ámbito de plataforma con una clave virtual propia de Auphere en el proxy,
  para las llamadas que paga Auphere sin partner.
- Una prueba de barrido: con `proxy_required()` forzado, cada trabajo y cada ruta
  que llama a un modelo lo hace con un partner (o con el ámbito de plataforma)
  atado. Barre, no enumera.

## Test plan

- Unitario del consumidor: un trabajo de un cliente corre con el partner atado.
- Barrido: con el proxy obligatorio y un modelo falso que exige el ámbito, cada
  manejador de `jobs/handlers/` llega al modelo.
- Unitario: copiloto, `paraphrase` y sugerencias semanales con el proxy obligatorio.
