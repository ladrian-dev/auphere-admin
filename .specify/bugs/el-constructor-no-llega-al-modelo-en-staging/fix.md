# Bug Fix: en staging, el constructor y sus vecinos no llegan al modelo

- **Slug**: el-constructor-no-llega-al-modelo-en-staging
- **Fixed**: 2026-10-29
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`jobs-consumer` lee el partner del cliente al empezar cada trabajo y corre el
manejador dentro de `llm_proxy_partner_scope`: cubre a–f y cualquier trabajo
futuro. El grader diferido, las sugerencias semanales, el copiloto y la paráfrasis
abren el ámbito donde ya conocen al partner. Lo que paga Auphere sin partner (la
evaluación del constructor y la calibración del juez) va dentro de un ámbito nuevo,
`llm_proxy_platform_scope`, que sale con la clave `platform` del mapa de claves
virtuales. Dos barridos lo vigilan: uno corre cada tipo registrado detrás del
proxy obligatorio; el otro recorre las fuentes.

## Decisión: la clave de plataforma (j)

- **Dónde vive**: como una entrada más, `"platform"`, del mismo JSON
  `LITELLM_PROXY_VIRTUAL_KEYS` (secreto `nexus/<ws>/litellm-partner-keys`), no en
  una variable nueva. Ese secreto ya solo llega a api y runner, ya tiene su rol de
  ejecución y su ciclo (`/key/generate` y pegar), y la evaluación y la calibración
  corren en la API. Una variable nueva habría pedido terraform, un ARN y otro
  permiso para lo mismo.
- **Explícita, nunca por defecto**: `resolve_litellm_proxy(None)` solo devuelve la
  clave de Auphere dentro de `llm_proxy_platform_scope`; fuera, una llamada sin
  partner sigue siendo `missing partner virtual key`. Si no, un cliente sin
  partner (o un ámbito olvidado) gastaría la clave de Auphere sin que nadie lo viera.
- **Uno paga**: el ámbito de plataforma quita el partner atado mientras dura, y al
  salir vuelve el que hubiera. `LiteLLMProxyTarget.partner_id` pasa a `None` para
  Auphere.
- **Garantía 7**: ningún partner llega a la clave de Auphere (no es un UUID; el
  mapa se busca por `str(partner_id)`), y Auphere nunca usa la de un partner.

**Pendiente fuera del código (Luis)**: generar en el proxy de staging una clave
virtual de Auphere (`/key/generate`, sin `proxy_admin`, con su presupuesto) y
añadirla como `"platform": "sk-…"` al secreto `nexus/staging/litellm-partner-keys`.
Sin ella, la evaluación y la calibración en staging fallan con
`missing platform virtual key` (fail-closed, como debe). En producción no hay
proxy obligatorio y nada cambia.

## Decisión: dónde se lee el partner del trabajo

En `DbJobStore.start`, en la misma transacción que pasa el trabajo a `running`
(`partner_id_for_tenant`: `partner_tenants`, que no tiene RLS, o
`tenants.partner_id`). Viaja en `StartedJob.partner_id` y el consumidor lo ata
alrededor de `wait_for`, cuya tarea copia el contexto. Un cliente sin partner
(Demo Farmacia) corre sin clave: sin proxy obligatorio va al vendor; con él sigue
fallando ruidoso, como hasta ahora.

## Changes

| File | Change | Notes |
|---|---|---|
| `apps/api/src/nexus_api/core/llm_proxy.py` | modified | `llm_proxy_platform_scope`, `in_llm_proxy_platform_scope`, `require_llm_proxy_payer`, `platform_virtual_key`; `resolve_litellm_proxy` resuelve la de Auphere solo dentro del ámbito |
| `apps/worker/src/nexus_worker/runtime/llm.py` | modified | `_proxy_kwargs` exige un pagador (partner o plataforma) con el proxy obligatorio |
| `apps/worker/src/nexus_worker/jobs/registry.py` | modified | `StartedJob.partner_id` |
| `apps/worker/src/nexus_worker/jobs/store.py` | modified | `start` lee el partner del cliente |
| `apps/worker/src/nexus_worker/jobs/consumer.py` | modified | el manejador corre dentro de `llm_proxy_partner_scope` (a–f) |
| `apps/worker/src/nexus_worker/streams/weekly_suggestions_cron.py` | modified | ámbito con `due.partner_id` (g) |
| `apps/api/src/nexus_api/api/console/agent_copilot.py` | modified | ámbito con el partner de quien pregunta (h) |
| `apps/api/src/nexus_api/services/improvement/paraphrase.py` | modified | `paraphrase(..., partner_id=)` abre el ámbito (i) |
| `apps/api/src/nexus_api/services/improvement/corrections.py` | modified | pasa el partner del cliente a la paráfrasis (i) |
| `apps/api/src/nexus_api/api/admin/sector_tests.py` | modified | calibración y evaluación dentro de `llm_proxy_platform_scope` (j) |
| `apps/worker/src/nexus_worker/streams/grade_consumer.py` | modified | ámbito con el partner del cliente de cada veredicto (k) |
| `apps/api/tests/integration/test_jobs_reach_the_model_behind_the_proxy.py` | added | el barrido de `default_registry` detrás del proxy obligatorio |
| `apps/api/tests/integration/builder/test_model_calls_behind_the_proxy.py` | added | copiloto (partner), evaluación y calibración (Auphere) |
| `apps/api/tests/unit/test_llm_proxy_scope_coverage.py` | modified | barrido de fuentes: todo `LiteLLMProvider(...)` abre un ámbito o dice por qué no |
| `apps/api/tests/unit/test_litellm_proxy.py` | modified | el ámbito de plataforma |
| `apps/worker/tests/unit/test_jobs_consumer.py` | modified | el partner del trabajo |
| `apps/api/tests/integration/{test_deferred_grader,improvement/test_corrections,improvement/test_suggestions}.py` | modified | g, i, k con el partner atado |
| `docs/modelos-y-router.md`, `docs/console.md`, `.env.example` | modified | quién paga cada llamada; la entrada `platform` |
| `apps/api/src/nexus_api/services/tenant_lifecycle.py` | modified | solo el orden de imports (ruff I001), que dejó en rojo `verify.sh lint` el arreglo de `el-alta-descarta-la-moneda-de-la-bolsa` |
