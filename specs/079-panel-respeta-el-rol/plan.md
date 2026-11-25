# Plan de implementación: el panel respeta el rol del operador

**Rama**: `079-panel-respeta-el-rol` | **Fecha**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Entrada**: la spec de `specs/079-panel-respeta-el-rol/spec.md`, con las cuatro
decisiones de Luis del 2026-11-25 (§Clarifications).

## Resumen

El panel deja de obedecer a quien no tiene el permiso. Hay nueve permisos y una matriz
que Luis fijó: `admin` lo tiene todo, `qa_operator` lee, prueba y opera, y `viewer` solo
lee, conversaciones incluidas. La matriz se escribe una vez en la API, y el panel guarda
una copia que una prueba compara con el original.

- **Fase 1a, la guarda del servidor** (entra en el envío del 2026-11-26). La guarda de
  la 078 pide el permiso como argumento obligatorio en cada acción, página y ruta, y su
  prueba estructural exige que todo lo declare.
- **Fase 1b, la interfaz.** Oculta lo que el rol no puede hacer, y un operador nuevo
  es `viewer`.
- **Fase 2, la API.** El panel manda en cada llamada la sesión del propio operador
  junto al token de servicio. La API la verifica y aplica la misma matriz en cada ruta
  `/admin/*`. El token de servicio, solo, deja de servir.

## Contexto técnico

**Lenguaje/versión**: TypeScript estricto (Next 16.2, React 19.2) en `apps/admin`;
Python 3.11 (FastAPI, SQLAlchemy async) en `apps/api`.

**Dependencias principales**: las que ya hay. **Ninguna nueva.**

**Almacenamiento**: `operator_auth.principals` y `operator_auth.principal_sessions`, que
ya existen. Una migración que solo cambia el valor por defecto de `role`.

**Pruebas**: Vitest en `apps/admin` (la prueba estructural de la 078, ampliada) y pytest
en `apps/api` (unitarias de la matriz; de ruta en la fase 2).

**Plataforma**: el panel en Vercel; la API en ECS (staging y producción).

**Tipo de proyecto**: web — un BFF de Next delante de una API.

**Rendimiento**: la fase 1 no añade llamadas (el rol ya viene en la sesión). La fase 2
añade una búsqueda por clave primaria por llamada a la API.

**Restricciones**:

- La guarda sigue siendo la primera sentencia, fuera de cualquier `try` (078).
- El panel y la API se despliegan por separado y a distinto ritmo: ningún paso puede
  depender de que uno llegue antes que el otro, salvo el orden explícito de la fase 2
  (research D13).
- El repo es público: ni la spec ni los commits describen cómo aprovechar lo que hoy
  falta.

**Escala**: 131 funciones de Server Action en 30 archivos, 10 rutas (nueve en `app/api`), 63
páginas, 88 componentes de cliente que llaman a acciones y 245 rutas `/admin/*` en 64
routers de la API.

## Constitution Check

*Puerta: se rellena antes de la Fase 0 y se vuelve a comprobar después del diseño.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto; lista blanca exhaustiva | ☑ | No toca ninguna de las 8 garantías: decide qué persona de Auphere puede hacer qué, no separa negocios ni clientes finales. Aplica la lección de §I: las pruebas **barren** (todas las funciones `"use server"`, páginas y rutas del panel; todas las rutas `/admin/*` registradas en la API) en vez de enumerar sitios conocidos. En la fase 2, el `app.operator_id` que usa la RLS de QA sale de una sesión verificada, no de una cabecera. |
| II | Corte por superficie de confianza | ☑ | No abre superficie: acota quién usa el panel (ya abierto) y sus rutas `/admin/*`. Declarado en la spec. |
| III | Lo leído es dato, nunca instrucción | ☑ | No aplica: no hay contenido leído que llegue a un agente. |
| IV | Acción consecuente con aprobación durable; la auditoría nombra a la persona | ☑ | La lista cerrada de §IV (borrar un cliente, rotar claves) queda solo para `admin` (`delete`, `credentials`). Fase 1: cada rechazo deja rastro con el operador. Fase 2: toda escritura de `/admin/*` nombra a la persona que la hizo, verificada (spec 6.4). |
| V | Estados honestos; la ausencia se diseña | ☑ | Los controles sin permiso no se pintan, ni apagados ni explicados. La explicación de hoy del Playground QA se retira. El aviso tras un intento rechazado es un estado de error, no una explicación previa. Conflicto con el encargo («deshabilitados con explicación») escrito en la spec: gana §V. Entre la 1a y la 1b hay controles a la vista que el rol no puede usar: excepción temporal decidida por Luis, justificada y acotada en Complexity Tracking. |
| VI | Por API, nunca navegando la consola | ☑ | No aplica: no hay agentes ni navegador. |
| VII | Test primero; nada de `skip` | ☑ | Cada criterio nace como prueba en rojo (ver `tasks.md`). La prueba estructural se amplía primero y debe fallar sobre el código de hoy antes de tocar una acción. |
| VIII | Licencias leídas | ☑ | Ninguna dependencia nueva. |
| IX | La KB es dueña del porqué | ☑ | `[[decisions/ADR-009-operator-only-panel]]` y `[[decisions/ADR-034-identidad-del-panel-de-operador-en-la-api]]`. Esta spec cambia la premisa «god-mode» de ADR-009: una tarea escribe la ADR que la sustituye y enlaza `specs/079-panel-respeta-el-rol/`. |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Ninguna de las 8 garantías. Las garantías de esta spec son de autorización y cada una tiene su prueba (ver `tasks.md`, columna «Garantía»). Ninguna va a `tests/isolation/` porque no separa tenants ni personas de un tenant. | Pruebas de la fase 1 en `apps/admin/src/__tests__/` y `src/lib/__tests__/`; de la fase 2 en `apps/api/tests/`. |
| **Licencias** | Ninguna dependencia nueva. | — |
| **Medidor** | Nada: no gasta modelo, reloj ni herramientas. | — |

## Estructura

### Documentación

```text
specs/079-panel-respeta-el-rol/
├── spec.md
├── inventario.md            # qué permiso pide cada acción, ruta y página
├── plan.md                  # este archivo
├── research.md              # decisiones D1–D13
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── permisos-del-panel.md        # fase 1
│   └── credencial-del-operador.md   # fase 2
├── checklists/requirements.md
└── tasks.md                 # /speckit-tasks
```

### Código

```text
apps/api/src/nexus_api/
├── core/operator_permissions.py        # NUEVO: la matriz (autoridad)
├── services/operator_identity.py       # DEFAULT_ROLE = "viewer"; resolver la sesión (fase 2)
├── db/models/operator_identity.py      # server_default y comentario del rol
├── api/admin/operator.py               # fase 2: require_panel_operator(permission)
├── api/admin/*.py                      # fase 2: cada ruta declara su permiso
├── core/qa_security.py, api/qa.py      # fase 2: el operador de QA sale de la sesión
└── core/security.py                    # fase 2: el token de servicio solo ya no basta
apps/api/alembic/versions/              # NUEVA: server_default de role → 'viewer'
apps/api/scripts/seed_operator.py       # docstring: rol por defecto y qué decide el rol
apps/api/tests/unit/                    # matriz; fase 2: barrido de rutas y credencial

apps/admin/src/
├── lib/permissions.ts                  # NUEVO: copia de la matriz + can()
├── lib/session.ts                      # requireOperator(p), requirePageOperator(p), routeOperator(p)
├── lib/qa-access.ts                    # se retira (D5)
├── lib/operator-auth.ts                # comentario de Role
├── lib/backend.ts, lib/qa-api.ts       # fase 2: añaden la sesión junto a adminToken()
├── lib/admin-token.ts                  # enmienda de la 078: no se toca
├── components/shell/                   # nav.ts (permiso por entrada), command-palette, aviso de rechazo
├── components/operator-can.tsx         # NUEVO: proveedor de contexto + useCan()
├── app/(dashboard)/**                  # 63 páginas y sus layouts; 88 componentes de cliente
├── app/**/route.ts                     # 10 rutas (9 en app/api)
└── __tests__/server-actions-require-operator.test.ts   # la prueba de la 078, ampliada

docs/admin.md                           # «Quién puede operar»
```

**Decisión de estructura**: no hay módulos nuevos salvo la matriz (dos archivos, uno
por lado) y el proveedor de contexto. Todo lo demás cambia código que ya existe.

## Fases de implementación

### Fase 1a — la guarda del servidor (envío del 2026-11-26, 06:00 UTC)

Requisitos 1 (salvo 1.6), 2, 4 y 5.

1. **La matriz y su prueba** (API y panel). Primero en rojo: la prueba de la matriz y
   la prueba estructural ampliada fallan sobre el código de hoy.
2. **La guarda** con sus tres variantes y el aviso de rechazo (contrato).
3. **Declarar el permiso** en las 129 acciones, 10 rutas y 63 páginas según
   `inventario.md`, área por área. Al final de cada área, la prueba estructural no
   nombra ningún archivo de esa área. Se separa `setTenantStatusAction` (D6). El
   Playground QA pasa a la guarda común (D5).
4. **Documentación viva** y los comentarios que dicen que el rol no decide nada.
5. **`/cso`** sobre el cambio, y `./scripts/verify.sh lint` más las pruebas de lo
   tocado.
6. **Despliegue**: los roles de producción ya están revisados (nadie pierde acceso).
   En staging, Luis decide si las cuentas `qa_operator` pasan a `admin`. El recorrido
   en staging (T057) es la puerta antes del PR a `main`.

Mientras no llegue la 1b, los controles siguen a la vista para todos los roles y un
intento sin permiso acaba en el aviso de 2.2 (spec, casos límite).

### Fase 1b — la interfaz (después del envío)

Requisito 3 y criterio 1.6.

1. **Ocultar los controles**: proveedor `useCan`, menú, paleta, vacíos y suplantación
   (D4, D7), área por área con las mismas áreas que la 1a.
2. **El rol por defecto** `viewer`, con su migración (D8).
3. **Puertas de UI**: `ui-states-checklist`, `a11y-audit`, `responsive-audit` y
   `design-tokens`, más un recorrido con cada rol (quickstart).

### Fase 2 — la API (requisito 6)

1. **El panel manda la sesión** en cada llamada, junto a `adminToken()` (D10). Se
   despliega antes que el paso 3.
2. **La dependencia única** `require_panel_operator(permission)` y su prueba de barrido
   en rojo (D11).
3. **Cada ruta `/admin/*` declara su permiso**: las 245, con el mismo criterio que el
   inventario del panel. Las cuatro rutas de servicio, con su razón (D12).
4. **Auditoría**: toda escritura nombra al operador verificado.
5. **QA**: el operador de la RLS de QA sale de la sesión.
6. **Guiones manuales** que llaman a `/admin/*`: entran como operador o se retiran
   (D12).
7. `/cso` y `tenant-security-audit` antes de dar la fase por terminada.

## Complexity Tracking

| Excepción | Por qué hace falta | Alternativa más simple, descartada porque |
|---|---|---|
| **§V, temporal.** Entre la 1a y la 1b, un `qa_operator` o un `viewer` ve controles que su rol no permite; al pulsarlos, la página se vuelve a pintar con un aviso. | Luis quiere la guarda del servidor en el envío del 2026-11-26. Ocultar los controles toca 88 componentes y sus puertas de UI, y no cabe esa noche. A quién afecta: a ningún operador de producción (revisado el 2026-11-25) y a las cuentas `qa_operator` de staging. | *Esperar a la fase 1 entera*: el panel seguiría obedeciendo a cualquier rol en producción. *Ocultar esa noche*: sin las puertas de UI que exige el repo. |

**Límite**: la 1b (fase 5, T025–T038) es lo siguiente después del envío, y su
checkpoint cierra la excepción.

Fuera de eso no hay nada que justificar: no hay dependencias, tablas ni superficies
nuevas. La única pieza que la spec no pedía es el aviso tras un rechazo (research D2),
y es lo mínimo para cumplir su criterio 2.2.
