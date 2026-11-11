# Implementation Plan: Aparcar el router y gobernar el precio por modelo

**Branch**: `059-aparcar-router-y-precios` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/059-aparcar-router-y-precios/spec.md`

## Summary

Seis cambios, en una sola entrega:

1. **Proteger el modelo en uso.** La API impide retirar o marcar «No disponible» un
   modelo en uso, y ofrece el camino de vuelta. Un modelo está en uso si es un
   valor por defecto de la plataforma, sale de un registro único que el worker
   publica en su latido, o si responde algún agente o tiene una asignación de
   cliente.
2. **Aparcar el router en el panel.** El panel lo oculta tras una constante: Router,
   Certificaciones, el bloque de Estado y las piezas de Modelos que dependen de él.
3. **Precio de venta.** Los pesos de venta se editan desde Modelos, y el
   multiplicador objetivo pasa a un ajuste de plataforma con suelo fijo de 1,5. Se
   quitan los avisos de precio a los partners.
4. **Tabla de Modelos.** Se rehace para que quepa en pantalla, con el diálogo de
   coste precargado.
5. **Limpiezas.** Juez, evaluación, beta, galería, «Rotar secret» y modelos del
   Playground.
6. **Números de Auphere.** Se rehace con el estilo del panel.

Las decisiones y su porqué están en [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11 (API y worker, `uv`); TypeScript strict con Next.js 16 y React 19 (panel, `apps/admin`, su propio workspace pnpm).

**Primary Dependencies**: FastAPI, SQLAlchemy async, Alembic, Redis, structlog; `@nexus/ui` y Tailwind v4 en el panel. **Ninguna dependencia nueva.**

**Storage**: PostgreSQL. Columna nueva `model_profiles.status_before_unavailable` y tabla nueva `platform_settings` (migración `0231`). Redis: el valor del latido existente.

**Testing**: pytest (API: unit, integration, isolation; worker: unit), Vitest y Testing Library (panel), `next build`.

**Target Platform**: Servicios en ECS (API, runner, scheduler) y el panel en Vercel.

**Project Type**: Web (API + worker + panel de operador).

**Performance Goals**:
- El barrido de uso recorre todos los clientes, como ya hace `scan_agents`, y solo
  corre al retirar, al marcar «No disponible» y al listar Modelos.
- Para el listado se cachea 60 s en el proceso de la API. Con 15 clientes en
  producción, es una lectura por cliente.

**Constraints**:
- Ni Terraform ni infraestructura (decisión de Luis).
- No se cambia nada del router en la API ni en el worker (2.8).
- Nada en producción hasta pasar a `main`.

**Scale/Scope**: 14 modelos y unos 15 clientes en producción. Unas 30 tareas en API, worker y panel.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto; whitelist exhaustiva | ☑ | El barrido de uso (1.2) lee cada cliente con `tenant_scoped_session` y solo devuelve recuentos y nombres de cliente. Test: `tests/isolation/test_model_usage_scan_rls.py` (T004). `platform_settings` no tiene cliente, como `model_profiles`. Nada recibe `tenant_id` del llamante. |
| II | Corte por superficie | ☑ | Superficie `0`, declarada en la spec. No se abre ninguna. |
| III | Lo leído es dato | ☑ | No se lee contenido externo ni de cliente final: el latido lo escribe nuestro propio worker, y la API lo valida como JSON con versión (D2). |
| IV | Acción consecuente con aprobación; auditoría con la persona | ☑ | Toda escritura nueva exige `X-Operator-Id` y un motivo, y queda en la auditoría de plataforma con la persona (data-model). Números de Auphere pasa de `admin:{token[:8]}` a la persona (6.4). Retirar y «No disponible» ganan una guarda, no pierden ninguna. |
| V | Estados honestos; la ausencia se diseña | ☑ | El router aparcado no deja botones apagados ni textos explicativos. Modelos no ofrece las acciones que la API rechazaría. Se quitan los textos que prometen protecciones falsas (4.6). Estados de carga, vacío, error y parcial en Modelos (4.7). |
| VI | Por API, no navegando la consola | ☑ | No aplica: no se añade ninguna automatización de agente. |
| VII | Test primero | ☑ | Cada tarea de implementación tiene antes su tarea de test en rojo (tasks.md). El registro de modelos por defecto se prueba con un barrido, no con una lista (D1). |
| VIII | Licencias | ☑ | No entra ninguna dependencia nueva. |
| IX | KB dueña del porqué | ☑ | `[[decisions/2026-11-11-aparcar-router-y-gobernar-precios]]`, que enlaza a `specs/059-aparcar-router-y-precios`. |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantía 1 (RLS), rozada por el barrido de uso de modelos (1.2) | T004 en `tests/isolation/test_model_usage_scan_rls.py` |
| **Licencias** | Ninguna dependencia nueva | — |
| **Medidor** | No se gasta nada nuevo. Cambia cuánto se cobra por lo ya medido: los pesos (3.2) y el multiplicador (3.6). El partner lo ve en su consumo, como hoy. Se prueba que el turno siguiente cobra con los pesos nuevos. | T027 y T028 |

## Project Structure

### Documentation (this feature)

```text
specs/059-aparcar-router-y-precios/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/admin-api.md
├── checklists/requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/0231_platform_settings.py           # nueva
├── src/nexus_api/
│   ├── services/model_usage.py                          # nueva: uses_of, verificación del latido
│   ├── services/model_lifecycle.py                      # guardas, vuelta, retirada detenida, sin avisos
│   ├── metering/sale_policy.py                          # nueva: target_multiplier, propuesta, suelo
│   ├── metering/pricing_policy.py                       # weight_drift recibe el multiplicador
│   ├── api/admin/models_catalog.py                      # uses, sale, rutas nuevas
│   ├── api/admin/usage_overview.py                      # multiplicador configurado
│   ├── api/admin/sector_tests.py                        # judge_model, bank_size
│   ├── api/admin/whatsapp_login_beta.py                 # configured
│   ├── api/admin/auphere_channels.py                    # operador y motivo
│   ├── api/qa.py                                        # modelos del registro
│   └── services/testing/judge.py                        # juez por modelo
└── tests/{unit,integration,isolation}/…

apps/worker/src/nexus_worker/
├── platform_models.py                                   # default_models()
├── health.py                                            # latido con modelos
├── runtime/promote_subscriber.py                        # invalida precios
├── metering/pricing.py                                  # drift con el ajuste
└── jobs/handlers/agent_tests.py                         # juez por modelo

apps/admin/src/
├── lib/router-panel.ts                                  # nueva: ROUTER_PANEL_VISIBLE
├── lib/backend-models.ts · lib/backend.ts · lib/backend-whatsapp-beta.ts
├── components/shell/nav.ts
└── app/(dashboard)/
    ├── models/*            # tabla, diálogos, cabecera del multiplicador
    ├── router/** · certifications/*   # notFound() aparcado
    ├── status/page.tsx     # sin bloque Router aparcado
    ├── channels/*          # beta según configured
    ├── builder/{judge-calibration,eval}/*
    ├── auphere/channels/*  # rehecha
    └── qa/dev/ucm-gallery  # se borra

docs/modelos-y-router.md · docs/billing.md · docs/admin.md   # spec viva, mismo commit
```

**Structure Decision**: el monorepo existente: `apps/api`, `apps/worker` y
`apps/admin`. No se crea ningún paquete.

## Complexity Tracking

| Añadido que la spec no pedía literalmente | Por qué hace falta | Alternativa descartada |
|---|---|---|
| Tabla genérica `platform_settings` | El multiplicador editable (3.6) necesita guardarse en algún sitio | Una tabla de una sola fila: obligaría a una migración nueva por cada ajuste futuro |
| Invalidar la caché de precios con `CATALOG_CHANGED` | El 3.2 da 5 minutos, pero sin esto el cambio de pesos tarda hasta 5 minutos y no es comprobable en un test | Esperar la caducidad: no se puede probar de forma determinista |
| Caché de 60 s del barrido de uso en el listado | Listar Modelos no puede recorrer todos los clientes en cada carga | Sin caché: una lectura por cliente en cada visita |
