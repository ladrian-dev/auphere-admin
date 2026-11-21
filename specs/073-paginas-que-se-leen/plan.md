# Plan: Páginas que se leen

**Spec**: [spec.md](spec.md) · **Rama**: `073-paginas-que-se-leen` · **Fecha**: 2026-11-21

## Resumen

La spec toca cinco zonas. Cada una cambia poco de la API y casi todo de la consola:

| Zona | API | Consola |
|---|---|---|
| Auditoría (§1) | `actor_name`, `actor_scope`, `view`, origen del teléfono | Tabla fija, días en grupo, rol, «Solo cambios» |
| Menú del cliente (§2) | `delete_blocked` en lista, ficha y panel | ⋯ siempre; «Eliminar…» explica antes |
| Menú del agente (§3) | Nada | Deshacer al pausar y al archivar |
| Configuración del agente (§3b) | Nada | Filas en una columna, pruebas sin scroll propio, avisos una vez |
| Negocio (§4) | Nada (D1: se revisa por sección, como hoy) | Buscador, grupos plegados, columnas resumidas, preguntas plegadas, barra de revisión |

## Decisiones técnicas

- **§1.4, los nombres.** `audit_people()` lee las personas del equipo (`partner_memberships`) y de los clientes (`client_memberships`) con `partner_id` explícito. Así, por construcción, no puede traer a nadie de otro partner (garantía 1).
  - `actor` sigue siendo el correo, que es lo que usa el filtro por persona.
  - El nombre va en `actor_name` y en la frase (`summarise(..., actor_label=...)`), también en el CSV.
- **§1.5, el origen.** `client_phones._audit` escribe `origin: "app"` cuando quien actúa es la persona del cliente. `origin_of()` lo deduce también para las filas de antes (`client_phone.*` con `client:`).
- **§1.6, los accesos.** Son una lista de acciones (`ACCESS_ACTIONS`), no una categoría. `client_phone.revoked` y `client_account.deletion_requested` tienen categoría `auth`, pero son cambios.
  - Renovar la sesión y los intentos fallidos **no se escriben hoy en `audit_log`**, así que no hay nada que apartar. Si un día se escriben, se añaden a la lista.
  - La API sin `view` lo da todo, como hoy; la consola siempre manda `view`.
- **§2.2.** `client_delete_blocked()` devuelve `archive_first`, el mismo código con que el servidor ya rechaza eliminar un cliente activo.
- **§3.2, deshacer un archivado.** Restaurar devuelve el agente en pausa y no recupera sus números. La página ya cambió a la del agente archivado, así que Deshacer recarga la página (`router.refresh()`).
- **§3b.3, el coste.** Se lee antes de pulsar con la misma estimación que pregunta al ejecutar (`estimateTestsAction`, `scope: "all"`). Sin precio, dice «No se puede calcular el coste».
  - La cabecera solo enseña «sin ejecutar» cuando no hay tarjeta de pruebas.
- **§4.5, «Marcar todo como correcto».** Confirma cada sección leída con `POST /sections/{section}/confirm`.
  - **Cambio sobre la spec:** pregunta antes, en lugar de ofrecer Deshacer. La API no sabe «desconfirmar» (confirmar no deja historial), y D1 pide no tocar la API.
  - La barra cuenta solo lo **leído** (web, documentos, redes). Lo escrito por una persona no cuenta.
- **§4.1.** La búsqueda vive en `?q=` y se actualiza con `history.replaceState`, sin recargar la página.

## Ficheros

- **API**:
  - `api/console/audit.py`, `api/console/schemas.py`;
  - `services/client_phones.py`;
  - `services/console_home_blocks.py`, `api/console/schemas_clients.py`, `api/console/tenants.py`.
- **Consola, Auditoría**:
  - `app/(console)/audit/*`;
  - `components/audit/*`;
  - `app/api/audit/{page,export}/route.ts`;
  - `lib/backend.ts`, `lib/backend/home-usage.ts`.
- **Consola, menú del cliente**:
  - `components/clients/v2/{client-menu,client-header-v2,clients-list-v2}.tsx`;
  - `lib/backend/client-records.ts`.
- **Consola, agente**:
  - `components/builder/{agent-menu,agent-rows,agent-builder,tests-box,publish-bar,review-panel,agent-proto-model}.tsx|ts`.
- **Consola, Negocio**:
  - `components/business/sections/{business-sections,services-section,faqs-section,basics-section,policies-section,section-frame}.tsx`;
  - `business-search.ts`, `review-model.ts`, `services-model.ts`;
  - `app/(console)/clients/[ref]/business/page.tsx`.
- **Textos**: `i18n/lanes/*`.
- **e2e**: `e2e/audit-page.spec.ts`, `e2e/mock-api.mjs` (Auditoría) y `e2e/shell.config.ts`.

## Constitución

- **§I, aislamiento.** Garantía 1, rozada. Su test es `tests/isolation/test_073_audit_names.py`.
- **§VII, test primero.** Cada cambio llegó con su test en rojo. Hubo una excepción: el `delete_blocked` de la API. La ejecución se quedó colgada (conexión cerrada a la base de pruebas) y la implementación entró antes de ver el rojo. Sus aserciones fallan sin la implementación, porque el campo no existía.
- **§VIII, licencias.** No entra ninguna dependencia.
