# Bug Assessment: restaurar o publicar por las rutas viejas se salta la puerta

- **Slug**: restaurar-un-borrador-publica-sin-puerta
- **Created**: 2026-10-29
- **Source**: auditoría del constructor (`research/2026-10-29-auditoria-del-constructor/_index.md`, fallo 5)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

La puerta de la 047 (requisito 23: guardar publica solo si pasan las pruebas, y
saltarla pide owner o admin con motivo) se puede saltar sin motivo por tres
caminos.

## Symptom

1. **Rollback a un borrador.** `POST /console/clients/{ref}/agent/versions/{v}/rollback`
   y el rollback del panel de operador aceptan como destino una versión que nunca
   se publicó (`STAGED`): la ponen en marcha sin pruebas.
2. **Publicar por la ruta vieja.** `POST /console/clients/{ref}/agent/versions/{v}/publish`
   publica en la petición, sin encolar las pruebas.
3. **La puerta da por buena una versión sin pasada.** `evaluate_gate` trata «esta
   versión nunca se probó» como «pasa».

Lo esperado: una versión solo llega a clientes si pasó la puerta o si una persona
con permiso la saltó con motivo, auditado.

## Suspected Code Paths

- `apps/api/src/nexus_api/api/console/agents.py:146-204` (publish) y `:207-226` (rollback).
- `apps/api/src/nexus_api/api/admin/agent_configs.py:141-246` (promote) y `:249-265` (rollback).
- `apps/api/src/nexus_api/services/agent_config_service.py:521-546` `rollback`.
- `apps/api/src/nexus_api/repositories/agent_config.py:337` — permite un destino `STAGED`.
- `apps/api/src/nexus_api/services/publishing.py:132-275` `evaluate_gate`, `ran_here` en `190-198`.
- `apps/api/src/nexus_api/services/partner_provisioning.py:267` — publica al aprovisionar por la API de partners.
- `apps/worker/src/nexus_worker/jobs/handlers/agent_publish.py:103` — el único camino que prueba antes.

## Root Cause Hypothesis

La puerta nació en el trabajo `publish` del worker. Las rutas de antes (spec 030)
siguen publicando por `publishing.publish` en la petición, y el rollback de
siempre no distingue «volver a una versión que ya estuvo activa» de «poner en
marcha un borrador». Confianza: **alta**.

## Proposed Remediation

**Preferred**:
- El rollback solo acepta versiones que estuvieron activas (archivadas tras
  publicarse). Un destino que nunca se publicó responde 409
  `rollback_target_never_published`, con el camino de publicar.
- La ruta vieja de publicar de la consola responde 410 con la nueva: desde
  `73765dd5` todos los partners usan la consola nueva, que publica por el trabajo.
- `evaluate_gate`: una versión con suite y sin pasada propia **no** pasa
  (`tests_not_run`). El trabajo `publish` ya la ejecuta antes, así que no cambia
  nada para la consola nueva.
- El `promote` del panel de operador queda como salto auditado: exige `reason`,
  como el salto de la consola.
- La API de partners: comprobar si aprovisionar todavía publica un agente; si lo
  hace, el agente queda en borrador o pasa por el trabajo `publish`. Decide quien
  arregla, con la spec 047 (requisito 4: crear un cliente nunca crea un agente).

## Test plan

- Integración: rollback a una versión `STAGED` → 409 y nada cambia.
- Integración: rollback a una versión archivada que estuvo activa → sigue funcionando.
- Integración: la ruta vieja de publicar → 410.
- Unitario: `evaluate_gate` con suite y sin pasada → bloqueado `tests_not_run`.
- Integración: `promote` del admin sin `reason` → 422; con `reason`, auditado.
