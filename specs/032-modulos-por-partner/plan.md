# Implementation Plan: módulos por partner

**Branch**: `032-modulos-por-partner` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

## Summary

Columna `partners.console_modules varchar(16)[]` con CHECK (migración **0159**, relleno con
todas las secciones y `companion` donde `companion_enabled`). Servicio
`services/partner_access.py` (lee, valida, escribe, sincroniza `companion_enabled`,
audita) y router `api/admin/partner_access.py` con `require_operator` (compartido en
`api/admin/operator.py` desde la 033). El principal de la consola y `/console/me` llevan
`modules`; `Partner.ordered_console_modules()` lee el Companion de `companion_enabled` para
que la puerta del Companion y la consola nunca discrepen. En la consola: catálogo TS espejo
con prueba de deriva, `navForPartner(role, modules)`, `requirePartnerModule(module)` en un
`layout.tsx` por sección (clients, usage, audit, knowledge, workstation, team, billing,
keys) y en el Panel, paleta filtrada y burbuja condicionada. En el panel: pestaña
**Módulos** con rejilla agrupada a la Chatwoot.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | `tests/isolation/test_partner_access_scope.py`: cambiar A deja a B idéntico. `partners` sin RLS justificado en el docstring |
| II | Superficie | ☑ | `0` |
| III | Lo leído es dato | ☑ | N/A |
| IV | Auditoría con persona | ☑ | `partner_access.updated` con `operator:<correo>`; frase en `console_audit_vocabulary` |
| V | La ausencia se diseña | ☑ | Sin módulo: fuera del menú, del buscador y redirección; sin pantallas de bloqueo; casillas nunca deshabilitadas |
| VI | Por API | ☑ | N/A |
| VII | Test primero | ☑ | `tests/integration/test_admin_partner_access.py` (9), consola `nav.test.ts`, `principal-access.test.ts`, `principal-guards.test.ts`, admin `modules-form.test.tsx` |
| VIII | Licencias | ☑ | Ninguna |
| IX | KB | ☑ | `[[ADR-045-modulos-por-partner]]` |
