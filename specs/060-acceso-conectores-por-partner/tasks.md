---

description: "Tareas de la spec 060: acceso a conectores por partner"
---

# Tasks: Acceso a conectores por partner

**Input**: Design documents from `/specs/060-acceso-conectores-por-partner/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/admin-api.md](contracts/admin-api.md)

**Tests**: obligatorios (constitución §VII). Cada tarea de test se escribe y se ve en rojo antes de la tarea de implementación que la sigue.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **Test primero (§VII)**: rojo antes que implementación.
- **Aislamiento (§I)**: la spec declara la garantía 2 (y la 1, rozada). Sus tests son T010–T014.
- **Licencias (§VIII)**: no entra ninguna dependencia.
- **Medidor**: no se gasta nada.
- **Sin commits**: los hace Luis. Al cerrar se entregan los mensajes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: la historia de la spec (US1…US4)

---

## Fase 1: Base compartida (bloquea todo)

- [x] T001 Migración `apps/api/alembic/versions/0232_connector_partner_access.py`:
  - tablas `connector_access_defaults` y `connector_partner_access` (data-model.md), con `CHECK` de slug en minúsculas, FK en cascada a `partners` e índice por `partner_id`;
  - `GRANT` a `nexus_app`;
  - las dos frases de `console_audit_vocabulary`;
  - `downgrade` que lo deshace.

  Modelos en `apps/api/src/nexus_api/db/models/connector_access.py`, exportados en `db/models/__init__.py`.

  _Requisitos: 1.1, 1.2, 2.2, 3.2_
- [x] T002 [P] Test en rojo `apps/api/tests/unit/connectors/test_availability_rule.py`, con un caso por regla:
  - sin filas: todo disponible;
  - valor por defecto `false`;
  - decisión propia `true` sobre un valor por defecto `false`;
  - decisión propia `false` sobre un valor por defecto `true`;
  - cliente sin partner, que sigue el valor por defecto aunque haya decisiones de otros partners;
  - canales y conectores de sistema ignorados aunque haya filas;
  - slug normalizado a minúsculas.

  _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5_
- [x] T003 Implementar `apps/api/src/nexus_api/services/connectors/availability.py`:
  - `unavailable_slugs_for_tenant` y `ensure_connector_available` / `ConnectorUnavailable`;
  - `effective_for_partner` y `access_for_connector`;
  - `affected_by`, que devuelve clientes con conexión viva, agentes con activación y partners cuyo `default_connector_slug` es el slug.

  _Requisitos: 1.3, 1.4, 1.5, 1.6, 4.1, 4.3_

---

## Fase 2: Tests de aislamiento y barridos, en rojo (US3)

- [x] T010 [P] [US3] `apps/api/tests/isolation/test_060_connector_partner_access.py`, por el **camino real del turno** con la sesión del worker (research D3, D5):
  - montaje: dos partners A y B, un cliente en cada uno con WooCommerce conectado, una activación y un agente que nombra sus herramientas, más un conector de Composio con filas en `tool_catalog`;
  - con el conector no disponible para B, el turno de B no ofrece ni ejecuta ninguna de sus herramientas, y el de A sí;
  - lo mismo al pasar el valor por defecto a `false` con decisión propia `true` para A;
  - si la regla no se puede leer, el turno se queda sin herramientas de conectores (fallo forzado);
  - un cliente que pasa de B a A recupera las herramientas en el turno siguiente.

  _Requisitos: 5.3, 5.8_
- [x] T011 [P] [US3] En el mismo fichero, la consola de B no ve el conector en ningún listado:
  - integraciones;
  - integraciones del agente y herramientas de una integración;
  - capacidades;
  - conectores ofrecidos al constructor (`offered_connectors`).

  Pedir su detalle da la misma respuesta que un slug inexistente.

  _Requisitos: 5.1_
- [x] T012 [P] [US3] En el mismo fichero, ninguna alta crea una conexión utilizable para B:
  - por la consola: consentimiento, clave de API y `POST …/connections`;
  - por el panel: `initiate-consent` y `connect-api-key`;
  - por el alta de clientes de la API de partners;
  - por el webhook de Composio que completa un consentimiento iniciado antes, que queda `failed`.

  _Requisitos: 5.2_
- [x] T013 [P] [US3] En el mismo fichero, los cargadores de Amigable Cobro, WooCommerce y Amigable Venta fallan como «sin conexión» para un cliente de B. `cobranza_reminder_cron` y `agent_sales_poll_cron` lo saltan.

  _Requisitos: 5.4_
- [x] T014 [P] [US3] Barridos AST `apps/api/tests/unit/test_060_sweeps.py`:
  - toda construcción de `TenantConnector(` en `apps/api/src` está en una función que llama a `ensure_connector_available`, o en la lista cerrada (`bootstrap_webhook_manual`, canales);
  - todo `select(TenantConnector` en `apps/mcp/src` y `apps/worker/src` está en una función que llama a `connection_is_available`, o en la lista cerrada con su razón (`connector_reconcile_cron`, el pipeline vía `tool_policy`…).

  _Requisitos: 1.6, 5.2, 5.4_
- [x] T015 [P] [US3] Test en rojo `apps/api/tests/integration/connectors/test_connector_access_restore.py`:
  - deshabilitar no cambia la conexión, las credenciales, las activaciones ni las excepciones;
  - rehabilitar devuelve al turno las mismas herramientas.

  _Requisitos: 5.5, 5.6_
- [x] T016 [P] [US3] Test en rojo `apps/api/tests/integration/connectors/test_connector_access_agent_spec.py`:
  - guardar un agente que ya tenía herramientas de un conector no disponible no falla, y `strip_doc` no las quita;
  - añadir una nueva de ese conector da `tool_not_allowed`;
  - guardar desde capacidades conserva las ocultas.

  _Requisitos: 5.7, 1.6_

---

## Fase 3: Implementación de la regla en todos los caminos (US3)

- [x] T020 [US3] `services/activations.py` `tool_policy`:
  - añadir `Connector.slug` al `select`;
  - llamar a `unavailable_slugs_for_tenant` antes del bucle;
  - bloquear antes de cualquier `continue`.

  _Requisitos: 5.3, 5.8_
- [x] T021 [US3] `apps/mcp/src/nexus_mcp/_connector_access.py`, llamado desde `_load_amigable_client`, `_load_woocommerce_client` y `_load_amigable_venta_client`.

  _Requisitos: 5.4_
- [x] T022 [US3] `ensure_connector_available` en `initiate_consent`, `bootstrap_api_key` y `bootstrap_browser_credentials`. `complete_consent_from_webhook` deja la conexión `failed` y lo audita.
  - La consola traduce `ConnectorUnavailable` a `404 integration_unknown`.
  - `partner_provisioning` lo traduce a `ProvisioningError`.

  _Requisitos: 5.2_
- [x] T023 [US3] Catálogo:
  - `audience` obligatorio en `list_catalog` y `get_catalog_entry`, con sus tres llamadas;
  - `capabilities_client._rows` filtra;
  - `validator.load_context` marca `withheld` y carga `kept_withheld`;
  - `validate_spec` y `missing.strip_doc` respetan las retenidas ya guardadas;
  - `_set_spec_tools` conserva las ocultas.

  _Requisitos: 5.1, 5.7, 1.6_

---

## Fase 4: API del panel (US1, US2, US4)

- [x] T030 [P] [US1] [US2] [US4] Test en rojo `apps/api/tests/integration/connectors/test_connector_access_admin.py`, contra contracts/admin-api.md:
  - `GET` de la vista por partner y de la vista por conector;
  - `PUT` de estado (`enabled`, `disabled`, `default`) desde las dos vistas, con el mismo resultado;
  - `422 reason_required` y `422 connector_not_managed`;
  - `409 confirm_required` con afectados, y nada guardado;
  - `409 partner_default_connector`, aunque venga `confirm`;
  - pasar el valor por defecto a `false` afecta a partners sin decisión y a clientes sin partner;
  - un cambio que no cambia nada no audita;
  - el contenido de la auditoría;
  - `access` en `GET /admin/connectors` y `available_for_partner` en los conectores de un cliente;
  - un partner que no es Auphere no llega a estas rutas;
  - las decisiones de un partner borrado desaparecen con él (cascada).

  _Requisitos: 1.7, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4_
- [x] T031 [US1] [US2] [US4] Rutas `apps/api/src/nexus_api/api/admin/connector_access.py`, registradas en el router del admin. Campos nuevos en `admin/connectors.py`, `admin/tool_catalog.py` y en la lista de conectores de un cliente.

  _Requisitos: 1.7, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4_

---

## Fase 5: Panel (US1, US2, US4)

- [x] T040 [US1] [US2] Tipos y llamadas en un módulo aparte, `apps/admin/src/lib/backend-connector-access.ts` (`server-only` e `import { call }`, como `backend-whatsapp-beta.ts`). Campos nuevos (`access`, `available_for_partner`) en los tipos de `lib/backend.ts`.

  _Requisitos: 2.1, 3.1_
- [x] T041 [P] [US4] Test en rojo y componente compartido `apps/admin/src/components/connectors/access-change.tsx`, sobre `ConfirmDialog` de `@nexus/ui`:
  - el motivo va en `children` y se valida con `reasonError` de `lib/levers.ts`;
  - los afectados van en un `Callout` con `<ul>` por partner;
  - el error de la API se traduce con `toFailure` (`lib/action-result.ts`).

  Debe cumplir:
  - un `409 confirm_required` abre la confirmación con la lista, y cancelar no vuelve a llamar;
  - un `409 partner_default_connector` se explica con el partner y qué cambiar antes.

  _Requisitos: 4.1, 4.2, 4.3_
- [x] T042 [P] [US1] Test en rojo de la pestaña «Conectores» del partner, `apps/admin/src/app/(dashboard)/partners/[id]/connectors/`, con sus cinco estados:
  - estado por conector y su origen (propio o heredado);
  - habilitar o deshabilitar con motivo;
  - «Como el valor por defecto».

  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5_
- [x] T043 [US1] Implementar la pestaña (`page.tsx` de servidor, `actions.ts` con `requireOperator` y `revalidatePath`, y la lista de cliente). Registrarla en el grupo `configure` de `partners/[id]/tabs.tsx` y en `CHILD.partners` de `components/shell/crumbs.ts`, con sus tests (`profile-tabs.test.ts` y `crumbs.test.ts`).

  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5_
- [x] T044 [P] [US2] Test en rojo del bloque «Disponible para» en `connectors/[slug]/`:
  - valor por defecto y partners con decisión propia;
  - cambiar el valor por defecto;
  - añadir, cambiar y quitar un partner;
  - los cinco estados.

  _Requisitos: 3.1, 3.2, 3.3, 3.6_
- [x] T045 [US2] Implementar el bloque.

  _Requisitos: 3.1, 3.2, 3.3, 3.6_
- [x] T046 [P] [US2] Marca de acceso en `connectors/connectors-catalog.tsx`, y «No disponible para su partner» en `tenants/[id]/connectors/`, con sus tests.

  _Requisitos: 3.4, 3.5_

---

## Fase 6: Cierre

- [x] T050 Actualizar `docs/admin.md` (Conectores, Partners) y `docs/console.md` (catálogo disponible para el partner) en el mismo cambio.

  _Requisitos: todos_
- [x] T051 Puertas de UI sobre las dos vistas del panel: `ui-states-checklist`, `a11y-audit`, `responsive-audit` y `design-tokens`.
  Pasadas el 2026-11-13 en vivo sobre el panel local (360, 414, 768, 1024, 1280, 1440 y 1920 px; tema claro y oscuro). Lo que se arregló:
  - estados: esqueleto de la pestaña y error con reintento (`ReadError`);
  - accesibilidad: al cerrar el diálogo, el foco caía en `body`. Ahora vuelve al control que lo abrió, y al valor por defecto si guardar quitó la fila (dos pruebas que fallan sin el arreglo);
  - accesibilidad: axe sin incidencias en las dos vistas y con el diálogo abierto; el enlace al partner mide 24 px de alto;
  - responsive: a 375 px el selector de la decisión se encogía a 58 px. Ahora tiene ancho propio, la cabecera «Clientes conectados» pasa a «Conectados» (la tabla cabe a 1024 px) y los motivos y nombres sin espacios se cortan;
  - tokens: sin hex, sin estilos en línea, sin valores arbitrarios, espaciado dentro de la escala.
  Aceptado por Luis para fusionar (2026-11-13), con el arreglo aparte: los campos de `@nexus/ui` (`Input`, `Textarea`, `NativeSelect`) quitan el anillo de foco global de 2 px. Lo sustituyen por un borde de 1 px (6:1) y un halo de 3 px a 1,6:1 en claro y 1,8:1 en oscuro, por debajo de la regla de la casa (≥2 px a ≥3:1). Viene de antes de esta spec, pero son los controles principales de las dos vistas.
  Conocido, sin arreglar: en Chrome de Windows y Linux, las flechas sobre un selector cerrado cambian el valor y abren el diálogo al primer paso. «Deshabilitado» se alcanza con Alt+↓ o tecleando «D». No se pudo probar desde macOS. En móvil y tableta las tablas se desplazan dentro de su marco, como el resto del panel.

  _Requisitos: 2.5, 3.6_
- [x] T052 `/cso` sobre el cambio, porque toca la autorización entre partners. Ningún hallazgo HIGH abierto.
  Pasado el 2026-11-13 en modo diff: ningún hallazgo. Informe en `.gstack/security-reports/2026-11-13-135649.json`. Fuera del diff vio dos cosas:
  - un operador deshabilitado sigue leyendo el panel con su sesión abierta;
  - `connector_reconcile_cron` puede marcar como conectada una conexión retenida, aunque sigue sin poder usarse.

  _Requisitos: 1.6, 1.7_
- [x] T053 Verificación:
  - `./scripts/verify.sh lint`;
  - las suites de los ficheros tocados (API, MCP, worker y panel);
  - `tests/isolation/` completa, que bloquea el merge.

  _Requisitos: todos_
- [x] T054 Prueba en el navegador con el panel en local, siguiendo quickstart.md, con capturas.

  _Requisitos: CE-001, CE-005_
- [x] T055 Mensajes de commit para Luis y nota de estado en la KB.
  Guion en `.claude/commits/2026-11-13-spec-060-acceso-conectores-por-partner.sh`; nota en `decisions/2026-11-13-acceso-a-conectores-por-partner.md` de la KB.

  _Requisitos: —_

## Dependencias

- La fase 1 bloquea todo.
- Las fases 2 y 4 (tests) pueden escribirse en paralelo tras T003.
- La fase 3 va tras la 2; la 5, tras T031.
- T051–T054 van al final.
