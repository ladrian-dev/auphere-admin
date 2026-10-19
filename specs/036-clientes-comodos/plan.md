# Implementation Plan: el módulo de Clientes, cómodo y claro

**Branch**: `035-canales-y-conectores` (continúa) | **Date**: 2026-10-19 | **Spec**: [spec.md](spec.md)

## Summary

- **API.** `GET /admin/tenants-health` y `/admin/tenants-health/{id}` (`api/admin/tenants_health.py`) leen cada cliente con su GUC: canales activos y con problemas, el canal principal, la versión publicada del agente principal, conversaciones abiertas y de 7 días, la última actividad y los conectores por reconectar. Sin el Playground. La lista de conversaciones del admin añade `customer_name`, `customer_identifier` y `last_message_at`.
- **Lista.**
  - Vistas en pestañas con contador: Todos, Necesitan atención, Activos, En pausa y Archivados. Los archivados quedan fuera de «Todos».
  - Motivo de atención en palabras (`components/tenants/health.ts`). Por defecto, lo urgente primero.
  - Columnas Canal (logo y número), Agente, Actividad y Estado. La fila entera abre la ficha y el estado vive en la dirección.
- **Ficha.**
  - Cabecera compacta con «Probar agente» y cuatro hechos con forma: canal, agente, última conversación y semana. Pestañas en una fila con separadores de grupo.
  - Resumen a dos columnas: lo pendiente primero, conversaciones recientes, datos y pruebas.
  - Conversaciones con nombres y control explícito.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba |
|---|---|---|---|
| I | Aislamiento | ☑ | Lectura por cliente con su GUC; `tests/integration/test_admin_tenants_health.py` |
| II | Superficie | ☑ | `0` |
| IV | Auditoría | ☑ | Sin escrituras nuevas |
| V | La ausencia se diseña | ☑ | Vacíos con su porqué; «Ningún cliente necesita nada» |
| VII | Test primero | ☑ | API: 3 de integración. Panel: `health.test.ts`, `readiness.test.ts`, `profile-tabs.test.ts`, `crumbs.test.ts` |
| VIII | Licencias | ☑ | Ninguna nueva |
| IX | KB | ☑ | `[[ADR-047-clientes-comodos]]` |
