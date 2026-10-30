# Bug Fix: restaurar o publicar por las rutas viejas se salta la puerta

- **Slug**: restaurar-un-borrador-publica-sin-puerta
- **Fixed**: 2026-10-29
- **Assessment**: ./assessment.md
- **Status**: applied (con una desviación: la ruta vieja de publicar no responde 410)

## Summary

1. **El rollback solo vuelve a una versión que estuvo activa**
   (`AgentConfigRepository.rollback`, que comparten la consola de antes, el panel
   de operador y «Deshacer»): un destino `staged`, o archivado sin `promoted_at`
   (un borrador descartado), es `RollbackTargetNeverPublished` → `409
   rollback_target_never_published` con la ruta para publicarlo (en la consola,
   `…/agents/{id}/publish`; en el panel, el promote). No cambia nada.
2. **«No se probó» no es «pasa»** (`evaluate_gate`): con pruebas aplicables y sin
   una pasada de **esa** versión, `tests_not_run`, que se salta como una crítica
   (owner, admin u operador, con motivo). Va dentro de la condición
   `critical_tests` para no cambiar las cinco condiciones que pinta la consola.
   La vista previa de «Guardar» pasa `tests_will_run=True`: el trabajo `publish`
   pasa las pruebas antes de decidir, así que la consola nueva no ve nada nuevo.
3. **El promote del panel de operador es un salto auditado**: sin `reason`, `422
   reason_required` (también con `override` y motivo en blanco, que antes era
   400); con él, salta lo que salta un owner y el motivo queda en
   `agent_configs.override_reason` y en `agent.publish`. La puerta de evals
   (Block P) sigue igual.
4. Para que (1) no deje fuera versiones que sí estuvieron activas: al dejar de
   estar activa, una versión guarda `promoted_at` (el suyo, o su creación si nació
   activa: semillas, scripts). Ver «Riesgo».

## Decisión: la ruta vieja de publicar sigue viva (desviación)

El assessment pedía `410` para `POST /console/clients/{ref}/agent/versions/{v}/publish`
porque «todos los partners usan la consola nueva». No es el único llamador: el
**Companion publica por ella** (`companion/tools/proposals.py`,
`APPLY_ROUTES["publish"]`) y verifica en el acto `active_version`, un modelo
síncrono que el trabajo `publish` (202 y después) no cumple. Un 410 rompía esa
acción sin alternativa. Con (2), esa ruta ya no se salta nada: publica en la
petición, pero una versión con pruebas sin pasar queda bloqueada y solo un owner o
un admin la salta con motivo, auditado — lo que pide el requisito 23. Cuando el
Companion publique por el trabajo, la ruta puede responder 410 sin perder nada.

## Decisión: la API de partners

`POST /v2/partners/clients` con plantilla (`default_seed_template` o
`agent_seed_template`) sigue creando y publicando el agente de la semilla. Ya pasa
por la puerta (`publishing.publish`, rol `partner_api`), nace sin pruebas (la
suite empieza vacía) y su contrato lo documenta
(`docs/partner-integration.md`: «La consola y esta API crean distinto»): el
requisito 4.3 es del alta de la consola, que ya no crea agentes
(`tenant_lifecycle.create_client`). Dejarlo en borrador rompería la activación
automática (`activate_tenant_if_ready` exige una versión activa). Sin cambios.

Queda fuera de este fallo, para quien lleve la consola: el cuerpo de antes de
`POST /console/clients` (`ClientCreateIn`) sigue corriendo ese mismo blueprint y
puede crear un agente desde la consola si el partner tiene plantilla.

## Riesgo

- ~~El panel de operador (`apps/admin`) no manda cuerpo al promover.~~ Resuelto
  el mismo día: el diálogo «Publicar la versión N» pide el motivo (3–300
  caracteres, `reasonError` de `lib/levers.ts`) y lo manda como `{reason}`.
  `ConfirmDialog` de `@nexus/ui` gana `children` y `confirmDisabled`, con su
  prueba (`packages/ui/src/components/__tests__/confirm-dialog.test.tsx`).
- Una versión que nació activa sin `promoted_at` y **ya** estaba archivada antes de
  este cambio no se puede recuperar por rollback (fail-closed): «Restaurar» la trae
  como borrador, o el promote con motivo.

## Changes

| File | Change | Notes |
|---|---|---|
| `apps/api/src/nexus_api/core/errors.py` | modified | `RollbackTargetNeverPublished` |
| `apps/api/src/nexus_api/repositories/agent_config.py` | modified | el rollback solo a versiones que estuvieron activas; la degradación guarda `promoted_at` |
| `apps/api/src/nexus_api/services/agent_config_service.py` | modified | `rollback` sin la rama de borrador (ya no llega) |
| `apps/api/src/nexus_api/services/publishing.py` | modified | `tests_not_run`; `tests_will_run` para la vista previa |
| `apps/api/src/nexus_api/api/console/agent_publish.py` | modified | la vista previa con `tests_will_run=True` |
| `apps/api/src/nexus_api/api/console/agents.py` | modified | 409 con código y ruta en el rollback |
| `apps/api/src/nexus_api/api/admin/agent_configs.py` | modified | `reason` obligatorio en el promote; 409 con código y ruta en el rollback |
| `apps/api/tests/integration/builder/test_no_way_around_the_gate.py` | added | los tres caminos y la guarda |
| `apps/api/tests/integration/builder/test_publish_gate.py`, `apps/api/tests/unit/test_endpoint_agent_config.py`, `apps/api/tests/unit/test_endpoint_evals.py` | modified | los promote del panel con motivo; sin él, 422 |
| `docs/agentes.md` | modified | la puerta, el rollback y el promote |
