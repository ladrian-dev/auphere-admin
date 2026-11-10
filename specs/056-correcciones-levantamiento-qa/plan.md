# Plan de implementación: Correcciones del levantamiento QA de la consola del cliente

**Rama**: `056-correcciones-levantamiento-qa` | **Fecha**: 2026-11-07 | **Spec**: [spec.md](spec.md)

**Entrada**: `specs/056-correcciones-levantamiento-qa/spec.md`, aprobada por el owner el 2026-11-07 con D3 cambiada.

## Resumen

Diecisiete requisitos sobre la consola del cliente, la consola de partners, el panel, la app y el runtime del agente, sin abrir ninguna superficie:

- **Freno de citas.** Antes de enviar, una respuesta que da por hecha una reserva sin una reserva real detrás se reintenta una vez y, si insiste, pasa a una persona (`research.md` R1).
- **Agentes y Negocio** dejan de ser módulos del cliente. Quedan retirados, no borrados (R2).
- **Pestaña «Acceso»** en la ficha de cada cliente de la consola de partners. Llama a los mismos servicios que el panel (R3).
- **Un juego de reglas** de horario y servicios compartido por la ficha y Reservas, que escribe solo lo tocado (R5).
- **Bandeja, errores, validación, confirmaciones y formatos** (R6 a R16).

Cinco migraciones encadenadas, sin tablas nuevas (`data-model.md`).

## Contexto técnico

**Lenguaje/versión**: Python 3.11 (API y worker, uv). TypeScript con Next.js 16 y React 19 (consola y panel). Expo SDK 58 (app).

**Dependencias principales**: FastAPI, SQLAlchemy 2 y Alembic, LangGraph (worker), `@nexus/ui` (Base UI, Tailwind v4, OKLCH). **Ninguna nueva**: `email-validator` ya está (`apps/api/pyproject.toml:34`).

**Almacenamiento**: PostgreSQL con RLS forzada. Las migraciones van de la 0223 a la 0227.

**Pruebas**:
- pytest: `apps/api/tests/{unit,integration,isolation,release}` y `apps/worker/tests/unit`.
- Vitest: consola, panel y app.
- Playwright contra staging solo para 10.2 (manual).

**Plataforma**: AWS (staging desde `develop`), Vercel para la consola y las tiendas para la app.

**Tipo de proyecto**: monorepo web con API, worker, dos frontales Next y una app nativa.

**Rendimiento**:
- El freno solo llama al modelo cuando el filtro acierta y no hay respaldo, y nunca cuando la reserva se hizo.
- `resolved` se cuenta solo con la página vacía.

**Restricciones**:
- Sin punto y coma en los textos de la consola (`words.test.ts`).
- Sin `partner_id` ni `tenant_id` en los cuerpos.
- Toda acción de servidor con su prueba de permitido y denegado.
- Sin `!important` ni hex en JSX.

**Alcance**: 60 tareas en 4 paquetes de trabajo (A a D) sobre cinco apps: API, worker, consola, panel y app.

## Constitution Check

*Antes de la Fase 0 y repasado después del diseño: todo en verde.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants. `tenant_id` del contexto. Lista blanca exhaustiva | ☑ | `tests/isolation/test_console_scope.py` cubre solo las rutas nuevas (se amplía `_minimal_body`). Nuevas: `test_console_client_access_scope.py` y `test_056_booking_brake_same_conversation.py` (garantía 8). Se actualiza `test_lite_client_vs_client.py`. La FK del lote es compuesta |
| II | Corte por superficie | ☑ | Superficie `0`. No se abre ninguna |
| III | Lo leído es dato | ☑ | El borrador del agente va al clasificador como mensaje `user`, nunca como instrucción. La nota del reintento viaja como `system` |
| IV | Acción consecuente con persona nombrada | ☑ | Cada cambio de acceso se audita con `console:<correo>` u `operator:<correo>`. Revocar, archivar y deshacer piden confirmación. El freno deja `agent.booking_brake` |
| V | La pantalla no miente; la ausencia se diseña | ☑ | «Abiertas», motivos legibles, avisos atendidos, errores traducidos. La pestaña Acceso no existe sin permiso. La sede con horario propio se enseña sin editar |
| VI | Por API, nunca navegando la consola | ☑ | No aplica: el freno es runtime. El Playwright de 10.2 es una prueba de QA, no un agente |
| VII | Test primero | ☑ | Cada tarea de `tasks.md` empieza por su prueba en rojo. Ningún `skip`. La de staging es `manual_only` y se marca así, sin contar como cubierta en CI |
| VIII | Licencias | ☑ | Sin dependencias nuevas |
| IX | La KB es dueña del porqué | ☑ | `[[ADR-041-consola-lite-del-cliente-final]]` § «Enmienda · 2026-11-07 (spec 056)», ya escrita. Spec 047 R50 enmendada |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantía 1 (acceso del partner por `ref` → tenant, FK compuesta del lote). C8: las rutas del partner sin cuerpos. Garantía 8 rozada: el respaldo del freno se lee solo de la misma conversación | T005, T015, T021, T028, T041 |
| **Licencias** | Ninguna dependencia nueva | — |
| **Medidor** | **Modelo**: una llamada `classify` por respuesta candidata sin respaldo, dentro del `usage_turn` y cobrada a la bolsa del cliente como `classify` | T014, T016 |

## Estructura del proyecto

### Documentación

```text
specs/056-correcciones-levantamiento-qa/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md
├── contracts/api.md · contracts/events.md
├── checklists/requirements.md
└── tasks.md            (lo genera /speckit-tasks)
```

### Código que se toca

```text
apps/api/
├── alembic/versions/0223…0227_*.py
├── src/nexus_api/
│   ├── api/console/client_access.py (nuevo) · __init__.py · corrections batch (agent_improvement.py)
│   ├── api/console/lite/{inbox,reservas,reservas_schemas,business,agents,notifications}.py
│   ├── api/admin/client_access.py · api/console/schemas_business_sections.py · schemas_auth.py
│   ├── core/{client_auth,console_auth}.py · db/models/{client_access,conversation}.py
│   └── services/{client_access,inbox_view,inbox_lifecycle,console_identity,push_fanout,push_payloads}.py
│       services/business/{rules (nuevo),special_dates,services_catalog}.py · services/improvement/corrections.py
└── tests/{unit,integration,isolation,release}/…
apps/worker/src/nexus_worker/runtime/{booking_brake (nuevo),pipeline,dispatcher}.py · tests/unit/…
apps/console/src/
├── app/(console)/clients/[ref]/access/ (nuevo) · app/(console)/{agentes,negocio}/ (se borran)
├── app/(console)/not-found.tsx (nuevo) · app/not-found.tsx · app/error.tsx (nuevo) · app/(auth)/layout.tsx
├── components/{clients/v2,shell,inbox,reservas,business/sections,business/history,lite,error-boundary}
├── lib/{amount,business-rules,waiting-reasons}.ts (nuevos) · lib/{permissions,principal-access,backend}.ts
├── instrumentation.ts (nuevo) · i18n/lanes/client-access.ts (nueva)
apps/admin/src/app/(dashboard)/tenants/[id]/access/
apps/mobile/src/{app,features,lib}/…
docs/{consola-lite,console,admin,ficha-del-negocio,reservas,agentes,app-movil}.md
specs/047-la-fabrica-de-agentes/contracts/events.md
```

**Decisión de estructura**: monorepo existente. Nada se mueve de paquete. Lo compartido entre ficha y Reservas va en `services/business/rules.py` y `lib/business-rules.ts`.

## Orden de trabajo y paralelismo

1. **Fase 1 · Base** (en serie, la hace una sola mano):
   - las cinco migraciones 0223–0227 con sus modelos;
   - el permiso `client_access:manage`;
   - las reglas compartidas (`rules.py`, `business-rules.ts`);
   - `waiting-reasons.ts` y `amount.ts`.

   Así nadie crea una cabeza de Alembic en paralelo ni redefine una constante.
2. **Fase 2**: cuatro paquetes que pueden ir en paralelo, con propiedad de archivos disjunta:
   - **A · Freno de citas** (Historia 1): `apps/worker`, `dispatcher.py`, `capability_names.py`.
   - **B · Módulos y Acceso** (Historias 2 y 3): `client_access*`, `client_auth.py`, `console_identity.py`, `lite/agents.py`, `lite/business.py`, `push_*`, `notifications.py` (`LITE_LINKS`), `clients/v2`, `shell`, `agentes`/`negocio`, el panel y la app (salvo la Bandeja).
   - **C · Horario y servicios + pulido de Reservas** (Historias 4 y 6, Requisitos 5, 11, 12 y 13.1–13.2): `reservas*`, `business/sections`, `business/history`, `services/business/*`, `lib/amount.ts` (llamadas).
   - **D · Bandeja y transversales** (Historias 5 y 6, Requisitos 6–10, 13.3, 14–16): `inbox_view.py`, `inbox_lifecycle.py`, `lite/inbox.py`, `lite/notifications.py`, `corrections.py`, `agent_improvement.py`, `components/inbox`, `error-boundary`, `instrumentation.ts`, `(auth)`, `not-found`, la sesión, y la Bandeja de la app.
3. **Fase 3 · Cierre**:
   - los documentos;
   - `contracts/events.md` de la 047;
   - `verify.sh lint`;
   - las pruebas tocadas, una suite cada vez;
   - `pnpm gen` y `gen:check` de la app;
   - la comprobación de `quickstart.md` que se pueda hacer en local.

**Archivos compartidos con dueño único**:
- `apps/console/src/i18n/messages.ts` (registrar lanes) es de B. Los demás añaden claves en sus propias lanes.
- `apps/console/src/lib/backend.ts` (`backendFor`) es de B. C y D usan `lib/backend/*.ts` por módulo.
- `apps/mobile/src/api/lite.gen.ts` lo regenera el cierre.

## Riesgos

- **El aviso de cambio de reglas de horario puede marcar «Revísalo» en clientes reales** con minutos que no son múltiplo de 5. Se informa, no se cambia (5.5).
- **La rama de Reservas sin fusionar** tendrá que renumerar su migración desde la 0228 (`research.md`, coordinación).
- **El fallo intermitente de Reservas** puede no reproducirse. El plan deja el registro (`console.request_error`) y el reintento de sesión. Si no aparece en las diez repeticiones, 10.2 se da por cumplido con la prueba y el registro sigue vivo.
- **El freno puede escalar de más** si el filtro es demasiado amplio. Lo acota la llamada al clasificador, y `booking.brake` deja medirlo tras desplegar.

## Seguimiento de complejidad

| Añadido que la spec no pedía | Por qué | Alternativa descartada |
|---|---|---|
| Límite de invitaciones por partner y minuto (`console_client_invites_per_minute`, 429) | Abrir las invitaciones a todos los partners sin límite gasta el cupo compartido de Resend (100 al día, staging y prod) | Sin límite: un partner o un error en bucle deja sin correos a todos |
| `instrumentation.ts` con `onRequestError` | Sin él, la causa de 10.2 no se puede encontrar: los registros de Vercel caducan en una hora | Solo reintentar: taparía el síntoma sin saber la causa |
| Mover `REASONS` a `lib/waiting-reasons.ts` | El Requisito 7 necesita la misma tabla en la Bandeja y en el constructor | Copiarla: dos tablas que divergen |
