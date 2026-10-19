# Tasks: módulos por partner

- [X] T001 Tests API `tests/integration/test_admin_partner_access.py` y barrido `tests/isolation/test_partner_access_scope.py`. _Requisitos: 1.2, 2.1–2.3, 3.1_
- [X] T002 `PartnerModule`, `PARTNER_MODULES`, `PARTNER_NAV_MODULES`, `partners.console_modules` + CHECK; migración `0159` con relleno y vocabulario de auditoría. _Requisitos: 1.1–1.3_
- [X] T003 `services/partner_access.py` + `api/admin/partner_access.py`; `PartnerOut.console_modules`. _Requisitos: 2.1–2.3_
- [X] T004 Principal (`/console/auth/session`) y `/console/me` con `modules`. _Requisitos: 3.1_
- [X] T005 Consola: catálogo TS + prueba de deriva, `toResolution` (sin sección = `disabled`), `firstPartnerModulePath`, `navForPartner`, `requirePartnerModule` en layouts de sección y Panel, paleta y Companion filtrados. _Requisitos: 3.2–3.5_
- [X] T006 Panel: pestaña Módulos (catálogo, formulario, acción con operador, mensajes) + pruebas. _Requisitos: 2.1, 2.2_
- [X] T007 Recorrido en local: apagar Facturación la quita y redirige; encender Companion monta la burbuja. _Requisitos: 3.2, 3.3, 3.5_
- [X] T008 Suite completa en verde; `docs/admin.md`, `docs/console.md`; ADR-045.
