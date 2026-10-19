---
description: "Tareas de la spec 035 — canales y conectores"
---

# Tasks: Canales y Conectores

**Input**: [spec.md](spec.md), [plan.md](plan.md)

## Phase 1: API

- [X] T001 Tests de integración `tests/integration/test_admin_channels_and_connectors.py`: catálogo con los seis canales y TikTok según la bandera; canales de todos los clientes con su propio cliente y sin Playground; instalaciones por conector. _Requisitos: 1.1, 1.2, 4.1, 4.2_
- [X] T002 `services/channel_catalog.py` y `api/admin/channels_overview.py` (`/admin/channel-catalog`, `/admin/channels`, `/admin/connectors-installs`). _Requisitos: 1.1, 1.2, 4.1, 4.2_
- [X] T003 `ChannelOut` expone `agent_id` y `last_health_check_at`. _Requisitos: 2.3_
- [X] T004 Constitución §V 1.1.0. _Requisitos: 5.1_
- [X] T005 El callback de TikTok vuelve a `/tenants/{id}/channels` (test `tests/unit/test_tiktok_panel_redirect.py`). _Requisitos: 2.1_

## Phase 2: Canales del cliente

- [X] T010 Mover los diálogos y acciones a `tenants/[id]/_integrations/`; `revalidatePath` del layout del cliente. _Requisitos: 2.1_
- [X] T011 Lista de canales con «Configurar» y «Añadir canal». _Requisitos: 2.1_
- [X] T012 Asistente de cuatro pasos (`new`, `new/[channel]`, `…/agent`, `…/done`) con test de `stepOf` y de la tarjeta del catálogo. _Requisitos: 1.3, 2.2_
- [X] T013 Ficha del canal con Ajustes · Agente · Plantillas · Salud. _Requisitos: 2.3_

## Phase 3: Conectores del cliente

- [X] T020 Rejilla con `CatalogBrowser`, sin `channel_only`, estado en palabras; tests de etiquetas y dirección. _Requisitos: 3.1, 3.2_
- [X] T021 Ficha del conector con acciones según estado y editor de permisos por herramienta (test). _Requisitos: 3.3_

## Phase 4: Global y navegación

- [X] T030 Pestañas del cliente «Canales» y «Conectores»; enlaces del Resumen y del alta de cliente. _Requisitos: 2.1_
- [X] T031 Sidebar Plataforma: Canales · Conectores · Números de Auphere · Playground QA (test de `nav.ts`). _Requisitos: 4.3_
- [X] T032 `/channels` (catálogo + todos los canales con buscador y filtros) y `/connectors` + `/connectors/[slug]`. _Requisitos: 4.1, 4.2_

## Phase 5: Cierre

- [X] T040 `docs/admin.md` y ADR-046.
- [X] T041 Panel: `tsc`, `eslint --max-warnings 0`, `vitest`, `next build`; API: `ruff`, `mypy`, tests de la spec; recorrido en el navegador del asistente, la ficha del canal, los permisos (guardar y deshacer) y las vistas globales.

## Phase 6: Pulido pedido por el owner (2026-10-19)

- [X] T050 Logos reales de las apps (Simple Icons 15.22.0, CC0) en canales y conectores; fuera los glifos de Chatwoot. Test de `brandFor`.
- [X] T051 Migas en la barra superior con el recorrido completo; fuera la miga repetida, la etiqueta «Cliente»/«Partner» y los eyebrows que repetían el grupo del sidebar. Test de `crumbsFor`.
- [X] T052 Ficha del cliente como la del partner: hechos, pestañas en tres grupos (`NavTabs`), Resumen con lo que falta para operar (el endpoint de preparación ya no existía). Pestaña Agente en español neutro y con pestañas subrayadas.
