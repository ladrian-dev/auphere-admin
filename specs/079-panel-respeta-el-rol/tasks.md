---
description: "Tareas de la spec 079: el panel respeta el rol del operador"
---

# Tareas: el panel respeta el rol del operador

**Entrada**: [`spec.md`](spec.md), [`plan.md`](plan.md), [`research.md`](research.md),
[`data-model.md`](data-model.md), [`contracts/`](contracts/), [`inventario.md`](inventario.md),
[`quickstart.md`](quickstart.md).

**Pruebas**: no son opcionales (§VII). Cada bloque de pruebas se escribe y se ve en rojo
antes de su implementación.

**Cómo se lee**: tres entregas. La **1a** (fases 1 a 4 y las tareas de cierre marcadas
1a) entra en el envío a producción del **2026-11-26, 06:00 UTC**, por decisión de Luis.
La **1b** (fase 5) y la **2** (fase 6) van después. La historia 2 es P1 pero va después
de la 3 por esa misma decisión: la 1a es solo la guarda del servidor.

## Reglas de este repo *(constitución)*

- Cada tarea termina con `_Requisitos: N.m_`.
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado AAAA-MM-DD`.
- Test primero (§VII): rojo antes de implementar; un `skip` no cubre nada.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- **No tocar `apps/admin/src/lib/admin-token.ts`** (enmienda de la 078, PR 61) más allá
  de leerlo.

## Formato: `[ID] [P?] [Historia] Descripción`

- **[P]**: se puede hacer en paralelo (archivos distintos, sin dependencias pendientes).
- **[US1]…[US4]**: la historia de la spec a la que sirve.

---

## Fase 1: Preparación

**Propósito**: partir de la base correcta y con la prueba de la 078 en verde.

- [x] T001 Comprobar que la rama sale de `develop` con la enmienda de la 078 (`adminToken()` en `apps/admin/src/lib/admin-token.ts`, PR 61) y que en `apps/admin` pasan `pnpm vitest run src/__tests__/server-actions-require-operator.test.ts src/lib/__tests__/admin-token.test.ts src/lib/__tests__/session-require-operator.test.ts` antes de tocar nada. Si otra sesión cambió esos archivos después, rebasar primero.
      _Requisitos: 4.3_

---

## Fase 2: Base (bloquea todas las historias) — 1a

**Propósito**: la matriz, la guarda y el aviso. Nada de la fase 3 empieza sin esto.

### Pruebas (en rojo primero)

- [x] T002 [P] Prueba de la matriz en la API, `apps/api/tests/unit/test_operator_permissions.py`: exactamente los nueve permisos de `data-model.md`; la tabla de la spec 1.2 rol por rol (`admin` todo; `qa_operator` solo `read`, `qa` y `operate`; `viewer` solo `read`); un rol desconocido no tiene ninguno. Falla porque el módulo no existe.
      _Requisitos: 1.1, 1.2, 1.4, 4.5_
- [x] T003 [P] Prueba de la copia del panel, `apps/admin/src/lib/__tests__/permissions.test.ts`: lee `apps/api/src/nexus_api/core/operator_permissions.py` desde la raíz del repo, extrae el diccionario `OPERATOR_PERMISSIONS` y lo compara con `PERMISSIONS`. Además fija la tabla de 1.2 con `can()`, y `can()` da `false` con `access: "disabled"` y con un rol desconocido. Falla porque `lib/permissions.ts` no existe.
      _Requisitos: 1.2, 1.4, 1.5, 4.5_
- [x] T004 [P] Ampliar `apps/admin/src/lib/__tests__/session-require-operator.test.ts` (de la 078) con las tres variantes de la tabla de `contracts/permisos-del-panel.md`. Con permiso, las tres devuelven el operador.
      - `requireOperator(p)` y `requirePageOperator(p)`: sin sesión → `/login`; cuenta deshabilitada o rol desconocido → `/sin-acceso`.
      - Sin permiso, `requireOperator(p)` registra `operator.permission_denied` sin los argumentos de la acción, llama a `revalidatePath("/", "layout")` y redirige a la misma página con `sin-permiso=1` añadido a su búsqueda. La página sale del `Referer` solo si es del mismo host y pasa por `safeRedirect()`. Un `Referer` de otro host, `//otro-sitio` o ausente lleva a `/?sin-permiso=1`.
      - Sin permiso, `requirePageOperator(p)` llama a `notFound()`.
      - `routeOperator(p)` **nunca redirige**: 401 `{ "error": "unauthorized" }` sin sesión, y 403 `{ "error": "forbidden" }` con la cuenta deshabilitada, un rol desconocido o sin permiso, siempre sin llamar a `fetch`.
      - En `app/(auth)/sin-acceso/__tests__/`: una cuenta activa con un rol desconocido se queda en `/sin-acceso` y no va a `/tenants`, porque si no habría bucle.
      _Requisitos: 1.4, 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 5.2_
- [x] T005 [P] Prueba del aviso en `apps/admin/src/components/shell/__tests__/permission-denied-notice.test.tsx` (Testing Library): con `?sin-permiso=1` pinta un aviso con `role="status"` y el texto «Tu rol no permite esa acción; no se hizo nada», y quita el parámetro con `router.replace` sin recargar; sin el parámetro no pinta nada.
      _Requisitos: 2.2_

### Implementación

- [x] T006 Crear `apps/api/src/nexus_api/core/operator_permissions.py` con el diccionario literal `OPERATOR_PERMISSIONS` del contrato y `has_permission(role: str, permission: str) -> bool` (un rol desconocido da `False`). Deja T002 en verde.
      _Requisitos: 1.1, 1.2, 1.4, 1.5_
- [x] T007 Crear `apps/admin/src/lib/permissions.ts` (módulo puro, sin `server-only`) con `Permission`, `PERMISSIONS` y `can(operator, permission)`. Deja T003 en verde.
      _Requisitos: 1.1, 1.2, 1.4, 1.5_
- [x] T008 Reescribir la guarda en `apps/admin/src/lib/session.ts`: `requireOperator(permission)` con el permiso obligatorio, `requirePageOperator(permission)` y `routeOperator(permission)`, según el contrato: `routeOperator` nunca redirige, y la vuelta a la página usa `safeRedirect()` de `src/lib/safe-redirect.ts`, sin otra comprobación de origen.
      - Cada rechazo deja la línea `operator.permission_denied`, y la versión sin argumento desaparece.
      - `app/(auth)/sin-acceso/page.tsx` manda a `/tenants` solo si `can(operator, "read")`, no por `access === "ok"`.
      - La firma nueva rompe las 11 pruebas que simulan `@/lib/session`; actualizarlas en la misma tarea:
        - `auphere/channels/__tests__/numbers.test.tsx`;
        - `certifications/__tests__/certifications-parked.test.tsx`;
        - `channels/__tests__/login-beta-configured.test.tsx`;
        - `models/__tests__/actions.test.ts`, `models/__tests__/models-page.test.tsx` y `models/__tests__/router-parked.test.tsx`;
        - `partners/[id]/audit/__tests__/audit-page.test.tsx` y `partners/[id]/team/__tests__/team-page.test.tsx`;
        - `router/__tests__/router-parked.test.tsx`;
        - `status/__tests__/status-parked.test.tsx`;
        - `tenants/[id]/agent/__tests__/agent-model-actions.test.ts`.
        
        Todas bajo `app/(dashboard)/`.
      
      Deja T004 en verde. Depende de T007.
      _Requisitos: 1.4, 2.1, 2.2, 2.3, 2.5, 2.6, 2.7_
- [x] T009 Crear `apps/admin/src/components/shell/permission-denied-notice.tsx` (cliente, con los tokens y el aviso de `@nexus/ui`) y montarlo en `apps/admin/src/app/(dashboard)/layout.tsx`. Deja T005 en verde.
      _Requisitos: 2.2_

**Checkpoint**: la matriz existe en los dos lados y son iguales; la guarda pide permiso.
A partir de aquí el panel no compila hasta que cada llamada declare el suyo (fase 3).

---

## Fase 2b: Las puertas de la constitución

- **Aislamiento**: sin tarea en `tests/isolation/`. La spec no toca ninguna de las 8
  garantías: decide qué persona de Auphere puede hacer qué, no separa tenants ni
  personas de un tenant. Sus garantías son de autorización, y cada una tiene su prueba
  en la tabla «Garantía → prueba» del final.
- **Licencias**: sin tarea. No entra ninguna dependencia nueva.
- **Medidor**: sin tarea. No gasta modelo, reloj de máquina ni herramientas.

---

## Fase 3: Historia 1 — Cada operador hace solo lo que permite su rol (P1) 🎯 1a

**Objetivo**: toda acción, página y ruta del panel exige el permiso del inventario.

**Prueba independiente**: con una sesión de cada rol, cada acción del inventario se
ejecuta o se rechaza sin llegar a la API según la matriz (T010 y T012).

### Pruebas (en rojo primero)

- [x] T010 [US1] Ampliar `apps/admin/src/__tests__/server-actions-require-operator.test.ts` según «La prueba estructural» del contrato:
      - la guarda que toca en cada superficie: `requireOperator` en acciones, `requirePageOperator` en páginas, layouts y `generateMetadata` que lee la API, y `routeOperator` (devolviendo su rechazo) en `app/api/**/route.ts`;
      - un argumento literal que está en `PERMISSIONS`;
      - la regla de las funciones auxiliares (`guarded` en `models/actions.ts` y en `tenants/[id]/access/actions.ts`, `run` en `tenants/[id]/billing/membership-actions.ts`);
      - solo `loginAction` y `logoutAction` exentas;
      - barre el código, sin lista de sitios.
      
      Verla en rojo sobre el código de hoy: debe nombrar las 129 acciones, las 9 rutas, las 63 páginas y los 4 layouts.
      _Requisitos: 2.1, 2.5, 2.6, 2.8, 4.1, 4.2, 4.3, 4.4_
- [x] T011 [P] [US1] Prueba de la separación del estado del cliente en `apps/admin/src/app/(dashboard)/tenants/__tests__/tenant-status-actions.test.ts`: `setTenantPausedAction` solo acepta `active` y `paused` y pide `operate`; `archiveTenantAction` pide `delete`; ninguna otra acción exportada cambia el estado a `archived`. En rojo.
      _Requisitos: 2.4_
- [x] T012 [P] [US1] Prueba de la matriz aplicada en `apps/admin/src/__tests__/role-matrix-actions.test.ts`. Con la sesión simulada de cada rol y `fetch` simulado, se invoca una acción por permiso:
      - `read`: `checkSlugAction`;
      - `qa`: `testAgentTurnAction`;
      - `operate`: `stageAgentConfigAction`;
      - `money`: `rechargePartnerWallet`;
      - `credentials`: `createPartnerKeyAction`;
      - `impersonate`: `startImpersonationAction`;
      - `people`: `inviteOwnerAction`;
      - `delete`: `deleteTenantAction`;
      - `platform`: `activateAction`.
      
      El rol sin el permiso no hace ninguna llamada a la API y redirige con `?sin-permiso=1`; el rol con él la hace. En rojo.
      _Requisitos: 1.2, 2.1, 2.2 (CE-001)_

### Implementación (por áreas; el permiso de cada función sale de `inventario.md`)

- [x] T013 [P] [US1] **Partners**: primera sentencia `await requireOperator("<permiso>")` en `app/(dashboard)/partners/actions.ts` (21), `partners/_invitation/actions.ts` (3), `partners/[id]/modules/actions.ts` (2) y `partners/[id]/limits/actions.ts` (2).
      _Requisitos: 2.1_
- [x] T014 [P] [US1] **Clientes**: lo mismo en `tenants/actions.ts`, `tenants/new/actions.ts` y `tenants/[id]/sovereign-actions.ts`. Partir `setTenantStatusAction` en `setTenantPausedAction` (`operate`, solo `active`/`paused`) y `archiveTenantAction` (`delete`), y cambiar sus llamadas en los componentes (`grep -rn setTenantStatusAction apps/admin/src`). Deja T011 en verde.
      _Requisitos: 2.1, 2.4_
- [x] T015 [P] [US1] **Integraciones, canales y acceso**: `tenants/[id]/_integrations/actions.ts`, `_integrations/setup-actions.ts`, `tenants/[id]/channels/actions.ts`, `tenants/[id]/backchannel/actions.ts` y `tenants/[id]/access/actions.ts`. En el último, su `guarded` pasa a recibir el permiso como primer argumento literal.
      _Requisitos: 2.1_
- [x] T016 [P] [US1] **Agente, pruebas, claves y cobro del cliente**: `tenants/[id]/agent/actions.ts`, `agent/agent-model-actions.ts`, `agent/evals/actions.ts`, `tenants/[id]/capabilities/actions.ts`, `tenants/[id]/conversations/actions.ts`, `tenants/[id]/api/actions.ts` y `tenants/[id]/billing/membership-actions.ts`, cuyo `run` recibe el permiso como argumento literal.
      _Requisitos: 2.1_
- [x] T017 [P] [US1] **Plataforma**:
      - `models/actions.ts`: `guarded` recibe el permiso, y `previewRespondDefaultAction` pide `read`;
      - `router/actions.ts`, con `previewAction` como `read`;
      - `certifications/actions.ts`, `builder/actions.ts`, `builder/sector-guides/actions.ts`, `connectors/access-actions.ts`, `channels/whatsapp-login/actions.ts`, `auphere/channels/actions.ts`, `signups/actions.ts` y `components/shell/search-actions.ts`.
      _Requisitos: 2.1_
- [x] T018 [P] [US1] **Rutas** (las nueve de `app/api` y la de la factura, `(dashboard)/partners/[id]/charges/[chargeId]/invoice/route.ts`, con `read`): `routeOperator("read")` en `api/conversations/stream/route.ts` y `api/conversations/[conv_id]/stream/route.ts`, y `routeOperator("qa")` en las siete de `api/qa/**`, en lugar de `requireQAOperator()`.
      _Requisitos: 2.5, 2.9, 1.3_
- [x] T019 [US1] Retirar `apps/admin/src/lib/qa-access.ts` y `QA_ROLES`. Corregir el comentario de `Role` en `apps/admin/src/lib/operator-auth.ts` («Sólo gatean el QA Playground»). `app/(dashboard)/qa/page.tsx` pierde su explicación y empieza por `requirePageOperator("qa")`. Depende de T018.
      _Requisitos: 2.7, 2.9_
- [x] T020 [P] [US1] **Páginas y layout de partners** (18 páginas): `requirePageOperator("read")` en todas salvo `/partners/new` (`operate`), y en `partners/[id]/layout.tsx` (`read`).
      _Requisitos: 2.6, 2.7_
- [x] T021 [P] [US1] **Páginas y layouts de clientes** (22 páginas):
      - `operate`: `/tenants/new` y `/tenants/[id]/channels/new/**` (4), y el layout `tenants/[id]/channels/new/layout.tsx`;
      - `qa`: `/tenants/[id]/playground`;
      - `read`: el resto, conversaciones incluidas, y el layout `tenants/[id]/layout.tsx`.
      _Requisitos: 2.6, 2.7, 1.3_
- [x] T022 [P] [US1] **Páginas de plataforma e instancia** (23 páginas): `qa` en `/qa` y `/qa/[tenantId]/chat`, `read` en el resto, y `read` en `app/(dashboard)/layout.tsx` y su `generateMetadata` si lee la API.
      _Requisitos: 2.6, 2.7_
- [x] T023 [US1] Corregir los textos de la API que dicen que el rol no decide nada en `/admin/*`: el docstring de `services/operator_identity.py`, el comentario de `role` en `db/models/operator_identity.py` y el docstring de `scripts/seed_operator.py`. Deben decir que el panel aplica la matriz de `core/operator_permissions.py` desde la 079 y que la API lo hará en la fase 2. La migración 0089 no se edita: es historia.
      _Requisitos: 5.3_

**Checkpoint**: T010, T011 y T012 en verde; el panel compila.

---

## Fase 4: Historia 3 — Una acción nueva no puede olvidar su permiso (P2) — 1a

**Objetivo**: demostrar que la prueba estructural muerde.

**Prueba independiente**: los ejemplos malos hacen fallar al comprobador con su nombre.

- [x] T024 [US3] Extraer el comprobador de `apps/admin/src/__tests__/server-actions-require-operator.test.ts` a una función que reciba la raíz que barre, y añadir ejemplos malos en `apps/admin/src/__tests__/fixtures/role-guard/`. Fuera del barrido real, cada uno debe salir nombrado:
      - una acción sin argumento, otra con una variable y otra con un permiso inexistente;
      - una guarda dentro de un `try`;
      - una auxiliar llamada sin literal;
      - una página sin guarda;
      - una ruta que no devuelve el rechazo.
      _Requisitos: 4.1, 4.2, 4.4_

---

## Fase 5: Historia 2 — El `viewer` ve un panel de lectura (P1) — 1b, después del envío

**Objetivo**: ocultar lo que el rol no puede hacer, y un operador nuevo es `viewer`.

**Prueba independiente**: con cada rol, las vistas se pintan completas en sus estados y
sin controles que no puede usar (quickstart, recorrido en el navegador).

### Pruebas (en rojo primero)

- [ ] T025 [P] [US2] `apps/admin/src/components/__tests__/operator-can.test.tsx`: `useCan` responde según la matriz dentro del proveedor; fuera de él devuelve `false`.
      _Requisitos: 3.1_
- [ ] T026 [P] [US2] Ampliar `apps/admin/src/components/shell/__tests__/nav.test.ts`: cada entrada declara un permiso de la matriz; `navFor` con un `viewer` omite el Playground QA; la paleta ⌘K usa la misma lista filtrada.
      _Requisitos: 3.3_
- [ ] T027 [P] [US2] Pruebas de render por área con un `viewer` (Testing Library), en un `__tests__/viewer-*.test.tsx` por área: ficha del partner (sin «Recargar», «Rotar clave», «Suplantar» ni invitar), ficha del cliente (sin pausar, archivar ni borrar), claves vacías sin «Crear clave», y lo mismo con `qa_operator` para las delicadas.
      _Requisitos: 3.1, 3.2, 3.5_
- [ ] T028 [P] [US2] Prueba de la suplantación en `apps/admin/src/app/(dashboard)/partners/[id]/__tests__/impersonation-cookie.test.ts`: sin `impersonate`, el layout ignora y borra la cookie de suplantación.
      _Requisitos: 3.6_
- [ ] T029 [P] [US2] Prueba del rol por defecto en `apps/api/tests/unit/test_operator_default_role.py`: un alta sin rol da `viewer`; la migración no cambia el rol de las cuentas que existen.
      _Requisitos: 1.6_

### Implementación

- [ ] T030 [US2] Crear `apps/admin/src/components/operator-can.tsx` (proveedor y `useCan`) y montarlo en `app/(dashboard)/layout.tsx` con el rol y el estado del operador. Deja T025 en verde.
      _Requisitos: 3.1_
- [ ] T031 [P] [US2] Añadir un permiso a cada entrada de `apps/admin/src/components/shell/nav.ts` (`qa` para `/qa`, `read` el resto). `navFor` filtra por operador, y `app-sidebar.tsx` y `command-palette.tsx` usan la lista filtrada. Deja T026 en verde.
      _Requisitos: 3.3_
- [ ] T032 [P] [US2] Ocultar los controles de **partners**: componentes de cliente de `app/(dashboard)/partners/**` que llaman a acciones. Cada uno pinta su control solo si `useCan(<permiso de su acción>)`. Sin huecos donde iban: si una sección se queda sin acciones, se pinta en lectura.
      _Requisitos: 3.1, 3.2, 3.5_
- [ ] T033 [P] [US2] Lo mismo en **clientes, integraciones, canales y acceso**: `app/(dashboard)/tenants/**`, salvo agente y cobro.
      _Requisitos: 3.1, 3.2, 3.5_
- [ ] T034 [P] [US2] Lo mismo en **agente, pruebas, claves y cobro del cliente**: `tenants/[id]/agent/**`, `tenants/[id]/api/**` y `tenants/[id]/billing/**`.
      _Requisitos: 3.1, 3.2, 3.5_
- [ ] T035 [P] [US2] Lo mismo en **plataforma**: `models`, `router`, `certifications`, `builder`, `connectors`, `channels`, `auphere`, `signups` y `tickets`. Deja T027 en verde.
      _Requisitos: 3.1, 3.2, 3.5_
- [ ] T036 [US2] Suplantación sin permiso en `app/(dashboard)/partners/[id]/layout.tsx`: sin `impersonate`, ignorar y borrar la cookie. Deja T028 en verde.
      _Requisitos: 3.6_
- [ ] T037 [US2] Rol por defecto `viewer`:
      - `DEFAULT_ROLE` en `apps/api/src/nexus_api/services/operator_identity.py`;
      - el `server_default` en `db/models/operator_identity.py`;
      - una migración nueva en `apps/api/alembic/versions/` que solo cambia el `server_default` de `operator_auth.principals.role` (el `downgrade` vuelve a `qa_operator`) y no toca ninguna fila;
      - el docstring de `scripts/seed_operator.py`.
      
      Deja T029 en verde.
      _Requisitos: 1.6_
- [ ] T038 [US2] Puertas de UI sobre las vistas tocadas: `ui-states-checklist`, `a11y-audit`, `responsive-audit` y `design-tokens`. Después, el recorrido del quickstart con los tres roles. Ningún 🔴 abierto.
      _Requisitos: 3.1, 3.2, 3.4, 3.5_

### De la revisión independiente del 2026-11-25 (después de la 1a)

Se arregló en la 1a: crear un partner y vincularle un cliente pasan a `people`, y reactivar un cliente archivado pide `delete`. Queda esto:

- [ ] T059 [US2] `updatePartnerAction` (`operate`) cambia el correo de facturación (efecto de `money`) y también suspende un partner. Separarlo como se hizo con el estado del cliente (criterio 2.4), con el permiso que Luis decida para cada parte.
      _Requisitos: 2.4_
- [ ] T060 [US2] Alta de un cliente de solo envío con un `qa_operator`: `createTenantAction` (`operate`) crea el cliente y `finishSendOnlySetupAction` (`money`) se rechaza, así que el cliente queda a medias. Ocultar la opción de solo envío a quien no tiene `money`, o pedir `money` antes de crear.
      _Requisitos: 3.1, 2.2_
- [ ] T061 [US3] Endurecer `role-guard-checker.ts`. Hoy nada en el código usa estas formas, pero el comprobador las dejaría pasar:
      - los argumentos de una auxiliar, que se evalúan antes de su guarda;
      - una llamada sin `await`;
      - exportaciones de `route.ts` que no sabe leer (`export const GET = …`, `export { h as GET }`);
      - valores por defecto de los parámetros;
      - que `requireOperator` venga de `@/lib/session` y no de una función local con el mismo nombre.
      _Requisitos: 4.1, 4.2_
- [ ] T062 [US2] Las llamadas que envuelven una acción en `try/catch` pueden mostrar un error un instante antes de la redirección de un rechazo. Revisarlas al ocultar los controles.
      _Requisitos: 2.2_

**Checkpoint**: la excepción temporal a §V de la spec queda cerrada.

---

## Fase 6: Historia 4 — La API comprueba al operador (P3) — fase 2

**Objetivo**: la API verifica la sesión del operador en cada llamada y aplica la matriz.

**Prueba independiente**: con el token de servicio y un `viewer`, una escritura recibe
403 y no cambia nada (T040).

### Pruebas (en rojo primero)

- [ ] T039 [P] [US4] `apps/api/tests/unit/test_admin_routes_declare_permission.py`: recorre `app.routes` y, para cada ruta bajo `/admin`, sus dependencias anidadas (como `tests/integration/test_device_bridge_inbound.py`). Toda ruta depende de `require_panel_operator` con un permiso de la matriz, o de `panel_service_route` y está entre las cuatro de `contracts/credencial-del-operador.md`. En rojo debe nombrar las 241 restantes.
      _Requisitos: 6.1, 6.5_
- [ ] T040 [P] [US4] `apps/api/tests/integration/test_panel_operator_credential.py`, una prueba por fila de la tabla de respuestas del contrato:
      - sin sesión → 401 `operator_session_required`;
      - sesión inexistente, caducada o de una cuenta deshabilitada → el mismo 401 `operator_session_invalid`;
      - un `viewer` en una escritura → 403 `permission_denied`, y la base no cambia;
      - un `admin` escribe, y la auditoría dice `operator:<correo>`;
      - si se deshabilita la cuenta a mitad de sesión, la siguiente llamada da 401;
      - el token de servicio sin sesión no escribe nada;
      - el valor de `X-Operator-Session` no aparece en ningún registro capturado.
      _Requisitos: 6.1, 6.2, 6.3, 6.4, 6.8_
- [ ] T041 [P] [US4] `apps/api/tests/integration/test_qa_operator_from_session.py`: las rutas de `/qa/*` exigen `qa` y el `app.operator_id` de la RLS es el id del operador verificado; un `viewer` recibe 403.
      _Requisitos: 6.6_
- [ ] T042 [P] [US4] `apps/admin/src/lib/__tests__/operator-session-header.test.ts`: todo archivo que llama a `adminToken()`, salvo `operator-auth.ts`, manda `X-Operator-Session`; `call()` la toma de la cookie de sesión.
      _Requisitos: 6.3_

### Implementación

- [ ] T043 [US4] **Panel**: añadir `operatorSessionToken()` en `apps/admin/src/lib/session.ts` y mandar `X-Operator-Session` en `lib/backend.ts` (`call`), `lib/qa-api.ts` y las tres rutas de flujo de `app/api`, sin tocar `lib/admin-token.ts`. `X-Operator-Id` se sigue mandando hasta T049. **Se despliega antes que T044–T048.** Deja T042 en verde.
      _Requisitos: 6.3_
- [ ] T044 [US4] **API**: `require_panel_operator(permission)` y `panel_service_route(reason)` en `apps/api/src/nexus_api/api/admin/operator.py`, según el contrato:
      - resuelve la sesión con `services/identity.resolve_session` en una sesión de base propia (el esquema `operator_auth` no da permisos a `nexus_app`) y comprueba `load_operator_view(...).ok`;
      - lee el rol de la base y aplica `has_permission`;
      - falla al importar si el permiso no está en la matriz.
      
      Las tres rutas de `api/admin/auth.py` se declaran con `panel_service_route`.
      _Requisitos: 6.1, 6.2, 6.3, 6.7_
- [ ] T045 [P] [US4] Declarar el permiso en los routers de **partners**: `partners.py`, `partner_*.py`, `receipts.py`, `impersonate.py` (su `_require_operator` desaparece) y `tickets.py`. Criterio del inventario.
      _Requisitos: 6.1, 6.7_
- [ ] T046 [P] [US4] Lo mismo en **clientes**: `tenants.py`, `tenant_*.py`, `client_*.py`, `send_only.py`, `service_memberships.py`, `unlimited_consumption.py`, `billing.py`, `budget_policies.py`, `backchannel_owners.py`, `opt_outs.py`, `conversations.py`, `channel_signup_links.py`, `whatsapp_pin.py`, `whatsapp_templates.py`, `meta_*.py` y `tiktok_authorize.py` (su callback es ruta de servicio).
      _Requisitos: 6.1, 6.7_
- [ ] T047 [P] [US4] Lo mismo en **agentes, conectores y plataforma**: `agent_configs.py`, `agents.py`, `agent_models.py`, `evals.py`, `connectors.py`, `connector_access.py`, `models_catalog.py`, `model_bindings.py`, `router_policies.py`, `certifications.py`, `sector_*.py`, `platform_settings.py`, `auphere_channels.py`, `whatsapp_login_beta.py`, `prompt_library.py`, `skills.py` y `tool_catalog.py`; y `overview.py`, `usage_overview.py`, `cost.py`, `tenants_health.py`, `channels_overview.py`, `isolation.py`, `audit.py`, `screenshots.py`, `partner_knowledge.py` y `signups.py`, casi todas de lectura.
      _Requisitos: 6.1, 6.7_
- [ ] T048 [US4] **QA y auditoría**:
      - `core/qa_security.py`: `require_qa_operator` resuelve la sesión y exige `qa`, y `api/qa.py` sigue fijando `app.operator_id` con ese id;
      - el actor de toda escritura de `api/admin/*` pasa a ser `operator_actor(operator)`, y desaparecen `_admin_actor` (`partners.py`, `signups.py`) y los actores genéricos escritos a mano.
      
      Deja T039, T040 y T041 en verde.
      _Requisitos: 6.4, 6.6_
- [ ] T049 [US4] **Limpieza, después de desplegar la API**:
      - quitar `require_operator`, `require_enabled_operator` y `operator_from_header`;
      - que el panel deje de mandar `X-Operator-Id` (los `backend-*.ts`, `backend.ts` y `qa-api.ts`).
      _Requisitos: 6.7_
- [ ] T050 [P] [US4] **Guiones manuales**:
      - entran como operador (login y luego la sesión en la cabecera): `scripts/ops/prueba-plantilla-muna.sh`, `apps/api/tests/release/test_release_smoke.py` y `apps/api/tests/release/test_booking_brake_staging.py`;
      - se reescribe el `curl` de `apps/api/RUNBOOK.md`;
      - se borra `scripts/smoke_test_block_n.sh`, que llama a rutas que ya no existen.
      _Requisitos: 6.8_
- [ ] T051 [US4] `/cso` y `tenant-security-audit` sobre la fase 2; ningún HIGH o CRITICAL abierto. Después, `docs/admin.md` cuenta que la API decide, y la ADR de la KB pasa la Fase 2 de ADR-009 a hecha.
      _Requisitos: 6.1, 6.4_

---

## Fase final: cierre de la 1a (antes del envío del 2026-11-26)

- [x] T052 [P] Reescribir `docs/admin.md`, «Quién puede operar», en el mismo cambio que la 1a:
      - la matriz y cómo se declara un permiso;
      - qué pasa al faltar;
      - que la interfaz aún no oculta (hasta la 1b);
      - que la API aún no comprueba el rol (hasta la fase 2).
      
      Quitar «No mira el rol».
      _Requisitos: 5.3_
- [x] T053 [P] Escribir en la KB (`/Users/lmatos/Work/Auphere/nexus/decisions/`) la ADR con el siguiente número libre que sustituye la premisa «god-mode» de ADR-009: la matriz, las cuatro decisiones de Luis y la fase 2. Enlazarla desde ADR-009 y ADR-034, y enlazar `specs/079-panel-respeta-el-rol/` (§IX). Sin detalle explotable.
      _Requisitos: 1.2, 6.3_
- [x] T054 `/cso` sobre el cambio de la 1a. Ningún HIGH o CRITICAL abierto antes del envío.
      _Requisitos: 2.1, 2.5, 2.6_
      Hecho el 2026-11-25: una pasada propia de las fases de código de `/cso`, acotada al diff y en modo diario, sin los verificadores independientes de la skill. Ningún hallazgo con confianza de 8 o más.
- [x] T055 Verificar de camino a `main`: `./scripts/verify.sh lint`; en `apps/admin` la suite entera de Vitest, el typecheck y `next build`; en `apps/api`, `tests/unit/test_operator_permissions.py`.
      _Requisitos: 4.3, 4.5_
- [x] T056 Antes del envío, Luis decide si las cuentas `qa_operator` de staging pasan a `admin` (`seed_operator.py --role admin`). Producción no necesita cambios: se revisó el 2026-11-25.
      _Requisitos: 5.1_
      Hecho el 2026-11-25: Luis pidió pasar a `admin` la única cuenta `qa_operator` de staging. Se cambió con la misma lógica del script de alta, que no viaja en la imagen, y se comprobó leyendo la tabla.
- [ ] T057 **Puerta de `main`**: con la 1a ya en staging (`develop`) y antes de abrir el PR a `main`, hacer el recorrido del quickstart en el navegador:
      - un `admin` opera como antes;
      - una cuenta `qa_operator` que pulsa un botón de `money` (por ejemplo, «Recargar») se queda en la misma página, ve el aviso, el saldo no cambia y el registro de staging tiene `operator.permission_denied`;
      - abrir `/tenants/new` como `viewer` da «no encontrada»;
      - las rutas de QA y los flujos de conversaciones siguen respondiendo.
      
      Si algo falla, la 1a no va a `main`.
      _Requisitos: 2.2, 2.3, 2.5, 2.7, 5.2_
- [ ] T058 Después del despliegue a producción, un `admin` abre una ficha de partner y una de cliente y hace una escritura reversible. El registro de producción no tiene ningún `operator.permission_denied` inesperado.
      _Requisitos: 2.1, 5.1_

---

## Garantía → prueba

| Garantía de la spec | Prueba |
|---|---|
| Una sola matriz; la copia no se desvía (1.5) | T002, T003 |
| La matriz decidida, rol por rol (1.2, 4.5) | T002, T003, T012 |
| Rol desconocido o cuenta deshabilitada: ningún permiso (1.4) | T003, T004 |
| Toda acción, ruta y página exige su permiso como primera sentencia (2.1, 2.5, 2.6) | T010 |
| Sin permiso: no llega a la API, misma página y aviso, rastro sin datos (2.2, 2.3) | T004, T005, T012 |
| Archivar es borrar, separado de pausar (2.4) | T011 |
| Página sin permiso: «no encontrada» (2.7) | T004 |
| La prueba estructural muerde (4.1, 4.2, 4.4) | T024 |
| La interfaz no pinta lo que el rol no puede (3.1–3.5) | T025, T026, T027 |
| La suplantación deja de valer sin el permiso (3.6) | T028 |
| Alta sin rol: `viewer` (1.6) | T029 |
| La API verifica la sesión y aplica la matriz en cada ruta (6.1, 6.2, 6.3, 6.5, 6.8) | T039, T040 |
| La auditoría nombra a la persona (6.4) | T040 |
| QA con el operador verificado (6.6) | T041 |
| El panel manda la sesión desde cada salida (6.3) | T042 |

---

## Dependencias y orden

- **Fase 1 → Fase 2 → Fase 3 → Fase 4 → cierre de la 1a.** Es lo que entra en el envío.
- **Fase 5 (1b)** depende de la 1a fusionada.
- **Fase 6 (fase 2)** depende de la 1a, y conviene después de la 1b. Dentro de ella:
  T043 se despliega antes que T044–T048, y T049 va después de desplegar la API.
- Dentro de cada historia, las pruebas en rojo antes que su implementación.

### Paralelo

- Fase 2: T002–T005 a la vez; luego T006 y T007 a la vez.
- Fase 3: T013–T018 y T020–T022 tocan archivos distintos y van a la vez, en cuanto
  T008 y T010 están hechos. T019 espera a T018.
- Fase 5: T025–T029 a la vez; T032–T035 a la vez después de T030.
- Fase 6: T039–T042 a la vez; T045–T047 a la vez después de T044.

```text
# 1a, fase 3, en paralelo tras T008 + T010:
T013 partners · T014 clientes · T015 integraciones · T016 agente y cobro · T017 plataforma
T018 rutas · T020 páginas de partners · T021 páginas de clientes · T022 páginas de plataforma
```

## Estrategia

1. **Esta noche (1a)**: T001–T024 y T052–T058, con T057 como puerta antes de `main`.
   Al acabar, el panel no obedece a quien no tiene el permiso, y la prueba impide que
   una acción nueva lo olvide.
2. **1b**: T025–T038 y T059–T062. Cierra la excepción temporal a §V.
3. **Fase 2**: T039–T051. La API deja de depender de que el panel no se equivoque.
