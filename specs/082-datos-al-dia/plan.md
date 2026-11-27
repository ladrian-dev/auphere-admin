# Plan de implementación: datos al día en la consola

**Rama**: `082-datos-al-dia` | **Fecha**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Entrada**: `specs/082-datos-al-dia/spec.md` (borrador decidido sin Luis, 0 marcas abiertas) y `research.md` (R1 a R7).

**Decidido sin Luis.** Luis no aprueba pasos intermedios en este lote. Lo que este plan decide por su cuenta va marcado con **(D)** y resumido en «Decisiones de este plan», al final.

## Resumen

La consola enseña datos viejos en cinco sitios. El arreglo tiene dos mitades:

- **Una fuente de datos que se invalida.** La agenda y la ficha de Reservas, el conocimiento del agente y el contador de la Bandeja pasan a React Query (`@tanstack/react-query` 5). La primera pintura sigue saliendo del servidor (`initialData`). Las relecturas pasan por Server Actions, con las mismas claves que la app del teléfono (`apps/mobile/src/api/query.ts`).
- **Un aviso para lo que cambian otros.** `core.add_event` marca la sesión con el negocio que cambió. Tras el commit sale `reservations.changed` por `inbox:{tenant}`, la línea en vivo que ya existe. Una sola línea por pestaña (`LiveStreamProvider`) la comparten la agenda, el contador, el sonido y la Bandeja. Al reconectar se relee todo.

Por el camino entran el sonido y el título con el número (Bandeja), el resumen del agente que se oculta tras resolver, y el avatar con color por contacto, icono sin letras, `@usuario` y nombre de perfil al día.

## Contexto técnico

**Lenguaje/versión**: Python 3.11 (API y worker, `uv`); TypeScript 5.9 estricto, React 19.2, Next.js 16.2 (consola).

**Dependencias principales**: FastAPI + SQLAlchemy 2 async, Redis pub/sub, `sse-starlette`. En la consola, **nueva**: `@tanstack/react-query` `^5.108.4` (ver Licencias).

**Almacenamiento**: PostgreSQL. **Sin migración**: el nombre de perfil y quién escribió el nombre van en `customers.preferences` (JSONB que ya existe). `customers.username` ya existe (migración 0206).

**Pruebas**: pytest (unit, integration, isolation) con base propia `nexus_test_082` y Redis 12; Vitest + Testing Library en la consola; Playwright con API simulada (`e2e/datos-al-dia.config.ts`).

**Plataforma**: API y worker en ECS; consola en Vercel (BFF). La ruta BFF de la línea en vivo declara `maxDuration = 300`.

**Tipo de proyecto**: web (API + consola), con un toque en el worker.

**Objetivos de rendimiento**: aviso a pantalla < 5 s (R1.7); escritura propia < 2 s (R1.1); contador y título < 2 s (R3.7).

**Restricciones**: el navegador nunca habla con la API (Server Actions y BFF); ningún aviso lleva datos del cliente final; la publicación no puede tumbar ni retrasar una escritura.

**Alcance**: 3 pantallas con datos vivos (Reservas, Agente › Conocimiento, contadores de la Bandeja), el marco de la consola y 4 piezas del backend.

## Constitution Check

*Se rellenó antes de diseñar y se volvió a comprobar después (abajo, «Tras el diseño»).*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | El aviso sale por el canal del negocio de la reserva (`res.tenant_id`, de la fila con RLS) y la línea se suscribe al del negocio de la sesión. Prueba nueva: `tests/isolation/test_082_reservations_changed_scope.py` (T008): canal ajeno, módulo ajeno y escritura real que solo avisa a su negocio. No toca herramientas del agente. |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0` declarada en la spec. No abre ruta nueva: reutiliza `GET /console/lite/inbox/stream` y amplía a quién admite (Reservas sin Bandeja). Las relecturas son Server Actions como las de hoy. |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | No llama al modelo ni lee contenido externo. El nombre de perfil de WhatsApp se guarda como dato y se pinta escapado (React). |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | No hay acciones nuevas. Las escrituras de Reservas siguen como hoy, y el doble clic que mandaba dos órdenes (412 del 20-nov) queda bloqueado (R1.3). |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | La agenda conserva `parcial` y «puede que no esté al día» (spec 064, 2.9). Conocimiento gana carga y error propios. Sin Bandeja no hay sonido, contador ni título con número. Sin línea en vivo se sondea en silencio. Los cinco estados se revisan en T040. |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | No aplica: no hay agente que opere la consola. |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada criterio tiene su prueba en `tasks.md` y se ve en rojo antes del código. Las pruebas de navegador ya escritas se revisan y se ven en rojo (T003). |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ☑ | `@tanstack/react-query` 5.108.4 y `@tanstack/query-core` 5.108.4: MIT, leídas en `node_modules`. Cita abajo y en `docs/licenses/consola-082.md` (T005). |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[research/2026-11-26-beta-jemma-p0-p1]]` (sección 082). |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento**: ¿qué garantías de `architecture/agent-isolation.md` toca? | **Garantía 1** (separación entre negocios) en la línea en vivo. La 8 no: el aviso no lleva datos del cliente final. | `T008` en `tests/isolation/test_082_reservations_changed_scope.py` |
| **Licencias**: ¿qué dependencia nueva entra? | `@tanstack/react-query` `^5.108.4` (con `@tanstack/query-core` 5.108.4), **MIT**. `LICENSE`: «Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software». Sin más dependencias en tiempo de ejecución. `peerDependencies`: `react ^18 \|\| ^19`. | `T005` |
| **Medidor**: ¿qué gasta y dónde lo ve el partner? | **Nada.** No llama al modelo, no gasta reloj de máquina ni herramientas de pago. El sonido se genera en el navegador. | — (no aplica) |

**Complejidad que hay que justificar:** ver Complexity Tracking.

## Diseño

### 1. El aviso `reservations.changed` (API, worker y MCP sin tocar sus rutas)

- `services/inbox_stream.py`: `RESERVATIONS_EVENT = "reservations.changed"` y `publish_reservations_changed(redis, *, tenant_id)`. El cuerpo es `{"event", "at"}`, sin `conversation_id` ni datos de la reserva (R1.6). Como `publish_inbox_event`, nunca lanza.
- `services/reservations/live.py` (nuevo): `mark_changed(session, tenant_id)`. Registra la publicación con `business.writes.after_commit`, que ya existe: corre tras el commit **exterior**, nunca tras un rollback, y descarta lo registrado dentro de un *savepoint* que se deshace (R1.5). **Una vez por negocio y por transacción**: la marca vive en `session.info`, con la transacción raíz en la que se puso. Si se deshace un *savepoint*, la publicación se descarta pero la marca no se borra, así que un `add_event` posterior en la misma transacción no volvería a registrar. Por eso la deduplicación se hace **al publicar**, no al registrar: se registra siempre, y la primera que corre por ese negocio y esa transacción publica.
- `core.add_event` llama a `mark_changed(session, res.tenant_id)`. Toda escritura que cambia lo que enseña la agenda pasa por `add_event` (R2 de la investigación). Lo fija un barrido (`T007`): ningún `ReservationEvent(` se construye fuera de `add_event` en `apps/`.
- El worker y el MCP del agente importan `core` desde `nexus_api`, así que el aviso les llega sin tocar `apps/mcp` (de la 080) ni `runtime/pipeline.py`.

### 2. La línea en vivo

- **API** (`api/console/lite/inbox_stream.py`): la dependencia pasa a `require_client_principal()` sin módulos, y la ruta exige `inbox` **o** `reservas` (403 si no tiene ninguno). Reenvía `conversation.updated`, `message.new` y `message.status` solo si la persona tiene `inbox`, y `reservations.changed` solo si tiene `reservas` (R1.11). El canal sigue siendo `inbox:{principal.tenant_id}`. El teléfono (spec 031) usa la misma ruta y gana el aviso sin cambiar nada.
- **BFF** (`app/api/lite/inbox/stream/route.ts`): admite a la persona de cliente con `inbox` o `reservas`. Declara `export const maxDuration = 300` (R3.12): la plataforma corta limpio y `EventSource` reconecta con un token nuevo.
- **Consola** (`components/live/live-stream.tsx`, nuevo): `LiveStreamProvider`, montado en el marco solo para personas de cliente con Bandeja o Reservas. Abre **un** `EventSource` por pestaña (R3.11) y expone el estado (`connecting · live · reconnecting`) y `subscribe(listener)`.
  - `reservations.changed`: invalida `["reservas"]`, con 300 ms de agrupación (R1.7).
  - `message.new`, `conversation.updated` y `message.status`: invalidan `["inbox","counts"]`, con 400 ms de agrupación (R3.7).
  - **Al volver** (un `ready` o `open` después de un `error`): invalida `["reservas"]` e `["inbox"]` y avisa a los suscriptores con un evento `back`. La Bandeja relee su lista y su conversación (R3.10).
- `components/inbox/use-inbox-stream.ts` deja de abrir su propio `EventSource`: se suscribe a la línea compartida, con la misma firma y un `onBack` nuevo.

### 3. React Query en la consola

- `lib/query.ts` (nuevo, cliente):
  - `makeQueryClient()`: `staleTime` 15 s (R1.9), `gcTime` 10 min, sin reintentar un 4xx, relectura al recuperar el foco o la conexión, solo en memoria.
  - `keys`, con la misma forma que el teléfono: `["reservas", …]`, `["inbox","counts"]`, `["agent", ref, id, "knowledge"]`.
  - `ActionError` y `unwrap()`: convierten un `ActionResult` en error de consulta.
- `components/query-provider.tsx` (nuevo): un cliente por pestaña. `ConsoleFrame` lo monta alrededor de los dos marcos (v1 y v2), porque el constructor del agente vive en los dos.
- **Pruebas**: `src/test/query.tsx` envuelve los renders en un proveedor nuevo por prueba. Sin cliente de reserva escondido: en producción el proveedor siempre está.

### 4. Reservas (Historia 1)

- La lectura de la página sale a `app/(console)/reservas/read.ts` (`server-only`): `readReservas(principal, searchParams, nowIso)`. La comparten la página (primera pintura) y una Server Action nueva, `reservasScreenAction({ query })`, que relee la misma URL.
- `reservas-view.tsx`: `useQuery(["reservas","screen",urlKey], …, { initialData, initialDataUpdatedAt })`.
  - Si el servidor repinta la página con una lectura más nueva que la de la caché, se adopta.
  - `refetchInterval` 45 s, que solo corre con la pestaña visible (R1.8). Al volver a la pestaña o recuperar la conexión, relee si la lectura tiene más de 15 s (R1.9).
  - `useLastGood` se aplica a lo que trae la consulta (R1.10).
  - «Puede que no esté al día» cuando la lectura en pantalla tiene más de 150 s (R1.8).
  - `ctx.refresh` pasa de `router.refresh()` a `invalidateQueries(["reservas"])`. Las 32 llamadas que ya escriben y luego releen siguen igual (R1.1).
- `booking-detail.tsx`: la ficha lee con `useQuery(["reservas","booking",id])`, bajo la misma raíz que la agenda: una invalidación relee las dos (R1.2). Mientras se guarda un cambio de estado, sus botones están ocupados, y una referencia impide el segundo envío antes del repintado (R1.3).
- `docs/reservas.md` § «La pantalla se pone al día sola» se reescribe (T037).

### 5. Conocimiento del agente (Historia 2)

- `builder/use-agent-knowledge.ts` (nuevo): `useQuery(["agent",ref,id,"knowledge"])` con `initialData` del servidor. Mientras alguna fuente está en `pending` y la pestaña está visible, relee cada 5 s, y para a los 10 minutos desde que vio la primera en `pending` (R2.4).
- `agent-knowledge.tsx` lee de ahí. Añadir, quitar, restaurar o enseñar invalida la consulta y llama a `onChanged`. El constructor ya hacía `refreshAll` al enseñar, y ahora lo hace en los cuatro casos (R2.3).
  - **(D)** `onTaught` pasa a llamarse `onChanged`.
  - **(D)** Mientras la primera lectura carga, sin datos del servidor, se pinta un esqueleto con `role="status"`; si falla, el aviso de hoy con «Reintentar».
- `agent-builder.tsx`: «Qué sabe» cuenta `visibleSources(items).live` de la misma consulta, no `items.length` de la copia del servidor (R2.2).
- Subida con plazo de 120 s y web con plazo de 60 s (R2.5): si no responde, se dice «No respondió a tiempo» y se relee la lista. La Server Action no se puede abortar: se deja de esperarla.

### 6. La Bandeja avisa (Historia 3)

- `components/live/inbox-alerts.tsx` (nuevo), montado bajo `LiveStreamProvider` solo con Bandeja:
  - **Sonido** (`components/live/chime.ts`): dos tonos con Web Audio, sin fichero. El `AudioContext` nace al primer `pointerdown` o `keydown` (R3.5). Como mucho uno cada 3 s (R3.3). No suena si el mensaje es saliente (R3.1). Tampoco si esa conversación está abierta (`/inbox?c={id}`) y la pestaña visible (R3.2). Con la pestaña oculta sí suena: es justo cuando hace falta.
  - **(D)** Con `prefers-reduced-motion` el sonido sigue: no es movimiento, y se apaga en Ajustes. La spec lo pide encendido por defecto (R3.4).
  - **Título**: `(N) ` delante, `99+` desde 100, en cualquier pantalla (R3.6). Un `MutationObserver` sobre `<title>` lo vuelve a poner cuando Next cambia el título al navegar.
- `shell/use-inbox-unread.ts` pasa a `useQuery(["inbox","counts"])`. Sondea cada 60 s solo con la línea caída (R3.8), y la Bandeja abierta le pasa sus números con `setQueryData`.
- `app-sidebar.tsx`: con la barra plegada, el número va en la esquina del icono (R3.9). El texto para lectores de pantalla ya está en el enlace. El fondo es `bg-primary`, el verde de la marca, nunca ámbar (R3.13).
- `inbox-settings.tsx`: interruptor «Sonido al llegar un mensaje», guardado en `localStorage` (`nexus.inbox.sound`), encendido por defecto (R3.4).

### 7. Resumen del agente (Historia 4)

`inbox_view.detail` devuelve el resumen del último `escalated` solo si no hay un `resolved` posterior y el escalado no es anterior a `conversation.context_from` (R4.1 a R4.3). Sin modelo (R4.4).

### 8. Avatar y nombre (Historia 5)

- `contact-avatar.tsx`:
  - Color por contacto: seis pares de tokens elegidos por un hash estable del id de la conversación (R5.1). Las tres vistas usan ese id.
  - Sin letras (`·` de la API o vacío), el icono `UserRound` (R5.3).
  - Los pares se comprueban con `@nexus/ui/lib/contrast` sobre `tokens.css` en los dos temas (R5.2).
- API: `ContactDetailOut.username` en el detalle lite. El panel y la cabecera lo pintan como `@usuario` (R5.4).
- `worker/persistence/messages.py` › `upsert_customer(…, profile_name=…)`:
  - Guarda `preferences.profile_name` y actualiza `name` cuando cambia, salvo `preferences.name_by == "person"` (R5.5).
  - Un `name` explícito (agenda del teléfono del negocio) rellena un contacto sin nombre y lo marca `name_by: "person"`.
  - El despachador pasa el nombre de perfil como `profile_name`: un cambio de una línea en `runtime/dispatcher.py`, que no es de ninguna otra spec.
- `core.contact_customer(…, by_person=True)`: un contacto creado con el nombre que escribió una persona queda `name_by: "person"`. `core.create` pasa `by_person=req.origin in {"person","walkin"}`.

## Estructura del proyecto

### Documentación (esta feature)

```text
specs/082-datos-al-dia/
├── spec.md · research.md · plan.md · data-model.md · quickstart.md
├── contracts/realtime-082.md
├── checklists/requirements.md
└── tasks.md
```

### Código

```text
apps/api/src/nexus_api/
├── services/inbox_stream.py                # + RESERVATIONS_EVENT, publish_reservations_changed
├── services/reservations/live.py           # nuevo: mark_changed tras el commit
├── services/reservations/core.py           # add_event → mark_changed; contact_customer(by_person)
├── services/inbox_view.py                  # resumen vigente; contact_username
├── api/console/lite/inbox_stream.py        # inbox o reservas; filtra por módulo
└── api/console/lite/inbox.py               # ContactDetailOut.username
apps/api/tests/
├── isolation/test_082_reservations_changed_scope.py
├── unit/test_082_reservations_live.py · test_082_add_event_sweep.py
└── integration/{reservas/test_082_datos_al_dia.py, test_082_inbox_detail.py, test_082_customer_name.py}
apps/worker/src/nexus_worker/
├── persistence/messages.py                 # upsert_customer(profile_name)
└── runtime/dispatcher.py                   # una línea: profile_name=
apps/console/src/
├── lib/query.ts · test/query.tsx
├── components/query-provider.tsx
├── components/live/{live-stream.tsx, inbox-alerts.tsx, chime.ts, title-count.ts}
├── components/shell/{console-frame.tsx, app-sidebar.tsx, use-inbox-unread.ts}
├── components/inbox/{use-inbox-stream.ts, inbox-view.tsx, inbox-settings.tsx, contact-avatar.tsx, contact-panel.tsx, thread-header.tsx}
├── components/reservas/{reservas-view.tsx, booking-detail.tsx}
├── app/(console)/reservas/{page.tsx, read.ts, actions.ts}
├── components/builder/{use-agent-knowledge.ts, agent-knowledge.tsx, agent-builder.tsx}
├── app/api/lite/inbox/stream/route.ts
└── i18n/messages.ts
apps/console/e2e/datos-al-dia{.e2e.ts,-mock.mjs,.config.ts}
docs/{consola-lite.md, reservas.md, licenses/consola-082.md}
```

**Decisión de estructura**: la de hoy (API + consola + worker). Solo un módulo nuevo en la API (`reservations/live.py`) y una carpeta nueva en la consola (`components/live/`) para la línea compartida.

## Tras el diseño (segunda comprobación)

- **§I.** El diseño no añade ningún canal ni acepta un negocio del llamante. La ampliación «Reservas sin Bandeja» filtra por módulo dentro del canal del negocio. La prueba de T008 cubre las tres fronteras: otro negocio, otro módulo y la escritura real.
- **§V.** Los estados quedan enumerados en T040, y la ausencia está diseñada: sin línea, sondeo en silencio; sin Bandeja, sin sonido ni número.
- **§VII.** Las pruebas de navegador que trajo la sesión anterior siguen siendo válidas como regresión. La de cancelar ya pasa hoy (R1). Las del aviso de reservas, el contador fuera de la Bandeja y la reconexión fallan hoy, y son el rojo de R1.4, R3.7 y R3.10. `datos-al-dia-probe.e2e.ts` era una sonda de la investigación: dos casos útiles (enlace `?booking=` y vista de lista) pasan a la prueba principal, y el resto se borra **(D)**.
- Sin cambios en la tabla: todas las filas siguen en verde.

## Complexity Tracking

| Añadido | Por qué hace falta | Alternativa más simple descartada porque |
|---|---|---|
| Deduplicación del aviso al publicar, no al registrar | Un *savepoint* que se deshace no puede dejar sin aviso a un cambio posterior de la misma transacción | Deduplicar al registrar pierde ese aviso. No deduplicar manda N avisos por transacción: la consola los agrupa, pero el teléfono y la línea los cargan |
| `read.ts` compartido por página y acción | La relectura de React Query tiene que leer exactamente lo que lee la página | Dos lecturas copiadas divergen |

## Decisiones de este plan (sin Luis)

1. **Sondas fuera.** `datos-al-dia-probe.e2e.ts` se borra. Sus casos útiles pasan a `datos-al-dia.e2e.ts`.
2. **`onTaught` → `onChanged`** en el panel de conocimiento, porque ahora avisa también al añadir, quitar o restaurar.
3. **Sonido y `prefers-reduced-motion`.** El sonido no se apaga con esa preferencia: no es animación, se apaga en Ajustes.
4. **Nombre de la agenda del teléfono del negocio.** El nombre que trae la sincronización de contactos (coexistencia) cuenta como escrito por una persona del equipo, pero solo cuando rellena un contacto sin nombre, dentro de `upsert_customer`. No se toca `meta_state_sync_consumer.py`.
5. **Contactos de antes.** Sin la marca `name_by`, gana el perfil, como dice la spec. Eso incluye los que sincronizó la coexistencia antes de esta spec: no hay forma de distinguirlos.
6. **`·` de la API.** La API sigue mandando `initials: "·"` (la app del teléfono lo lee). La consola lo trata como «sin letras» y pinta el icono.
