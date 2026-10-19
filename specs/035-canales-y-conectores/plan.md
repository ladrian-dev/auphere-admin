# Implementation Plan: Canales y Conectores

**Branch**: `035-canales-y-conectores` | **Date**: 2026-10-19 | **Spec**: [spec.md](spec.md)

## Summary

La API gana tres lecturas de operador: el catálogo de canales
(`services/channel_catalog.py`, disponibilidad calculada en el servidor), todos los
canales de todos los clientes y qué clientes tienen cada conector
(`api/admin/channels_overview.py`). Las dos últimas leen **cliente a cliente con su GUC**
(`tenant_scoped_session`) y nombran en `unreadable` al que no se pudo leer.

En el panel, la pestaña «Canales e integraciones» se parte en dos, como Chatwoot separa
Bandejas e Integraciones:

- **Canales**: lista de canales con «Configurar»; asistente «Añadir canal» de cuatro pasos
  (`channels/new/…`) que reutiliza los flujos de Meta y TikTok; ficha por canal con
  pestañas Ajustes · Agente · Plantillas · Salud (`?tab=`).
- **Conectores**: rejilla con el `CatalogBrowser` de `@nexus/ui` (el mismo que la consola
  de partners), sin los conectores `channel_only`; ficha por conector con sus acciones y el
  editor de permisos por herramienta, que la API tenía y ninguna pantalla usaba.

Los componentes que comparten las dos pestañas se mueven a `tenants/[id]/_integrations/`
(carpeta privada de Next, sin ruta). El sidebar pasa a Plataforma: Canales · Conectores ·
Números de Auphere · Playground QA, con una vista global de cada uno. El callback de
TikTok vuelve a Canales.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | Lecturas por cliente con su GUC; `tests/integration/test_admin_channels_and_connectors.py` comprueba que cada fila sale con su propio cliente |
| II | Superficie | ☑ | `0`. Ningún canal nuevo se puede conectar |
| III | Lo leído es dato | ☑ | N/A |
| IV | Auditoría con persona | ☑ | Asignar agente usa `X-Operator-Id`; los permisos por herramienta ya se auditaban |
| V | La ausencia se diseña | ☑ | Enmienda 1.1.0: el panel de operador enseña «Próximamente» en catálogos, sin poder iniciarlos; las consolas no |
| VI | Por API | ☑ | N/A |
| VII | Test primero | ☑ | API: 4 de integración + 2 unitarios del callback de TikTok. Panel: pasos del asistente, tarjeta del catálogo, etiquetas de conector, dirección del catálogo, editor de permisos |
| VIII | Licencias | ☑ | Iconos de canal de Chatwoot (MIT, fuera de `enterprise/`): aviso en `docs/licenses/chatwoot-MIT.txt` y en la cabecera del componente |
| IX | KB | ☑ | `[[ADR-046-canales-y-conectores]]` |

## Archivos

| Área | Archivos |
|---|---|
| API | `services/channel_catalog.py`, `api/admin/channels_overview.py`, `api/admin/tiktok_authorize.py`, `schemas/tenant.py` |
| Panel · cliente | `tenants/[id]/channels/**`, `tenants/[id]/connectors/**`, `tenants/[id]/_integrations/*`, `tenants/[id]/tabs.tsx` |
| Panel · global | `(dashboard)/channels/*`, `(dashboard)/connectors/**`, `components/shell/nav.ts` |
| Compartido | `components/brand/channel-icon.tsx`, `components/channels/*`, `components/connectors/labels.ts`, `components/catalog/*`, `lib/backend.ts` |
