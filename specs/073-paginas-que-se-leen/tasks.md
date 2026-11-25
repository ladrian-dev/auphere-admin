---

description: "Tareas de la spec 073: páginas que se leen"
---

# Tasks: Páginas que se leen

**Input**: [spec.md](spec.md), [plan.md](plan.md)

**Tests**: obligatorios (constitución §VII). Cada tarea de test se escribió y se vio en rojo antes de su implementación, salvo la excepción que dice el plan.

## Fase 1: Auditoría (§1)

- [X] T001 `apps/api/tests/integration/clients/test_audit_073.py`:
  - nombre y alcance de cada persona;
  - la frase con el nombre;
  - lo del teléfono es «app»;
  - «Solo cambios» deja fuera los accesos, también en el CSV.

  _Requisitos: 1.3, 1.4, 1.5, 1.6_
- [X] T002 `apps/api/tests/isolation/test_073_audit_names.py`: el nombre de una persona de otro partner no sale, ni en la lista ni en el CSV, aunque coincida el correo.

  _Requisitos: encabezado (garantía 1)_
- [X] T003 La API: `audit_people`, `actor_display`, `actor_scope`, `ACCESS_ACTIONS`, `view` en la lista y en el CSV, y `origin_of` para `client_phone.*`. `client_phones._audit` escribe `origin: "app"`.

  _Requisitos: 1.3–1.6_
- [X] T004 La consola, tests:
  - `audit-model.test.ts` (`dayLabel`, `timeLabel`, `groupByDay`, `actorName`);
  - `audit-query.test.ts` (`view`);
  - `audit-table.test.tsx` (tabla fija, días en grupo, rol de cada persona).

  _Requisitos: 1.1–1.4, 1.6_
- [X] T005 La consola:
  - la tabla `table-fixed` con anchos;
  - los días como filas de grupo y la hora sola;
  - «tú · partner», «partner», «cliente · …» y «plataforma»;
  - la cápsula «Solo cambios» / «Todo, con accesos»;
  - `view` en las rutas de página y CSV.

  _Requisitos: 1.1–1.7_
- [X] T006 `e2e/audit-page.spec.ts`: a 1280 px, `scrollWidth <= clientWidth`; dos días; «Solo cambios» y «Todo, con accesos»; axe en claro y en oscuro.

  _Requisitos: 5.2_

## Fase 2: Menú del cliente (§2)

- [X] T010 Tests: `delete_blocked` en la lista, el detalle y el panel (API); el ⋯ siempre en la cabecera; «Eliminar…» con «Primero hay que archivarlo» y «Archivar ahora», sin campo de nombre (consola).

  _Requisitos: 2.1–2.4_
- [X] T011 `client_delete_blocked` y `DeleteBlocked` en la API; `deleteBlocked` en `ClientMenu`, la cabecera y la lista.

  _Requisitos: 2.1–2.5_

## Fase 3: El agente (§3, §3b)

- [X] T020 Tests: Deshacer al pausar (reanuda) y al archivar (restaura y recarga); si Deshacer falla, lo dice y no toca la cabecera.

  _Requisitos: 3.1–3.3_
- [X] T021 Deshacer en `agent-menu.tsx`.

  _Requisitos: 3.1–3.4_
- [X] T022 Tests:
  - la fila con la etiqueta encima y «Editar» con su palabra;
  - la columna de pruebas sin `sticky`, `max-h` ni `overflow-y-auto`;
  - la barra sin «Ejecutar pruebas»;
  - «Ejecutar las N pruebas» con lo que cuestan;
  - los servicios sin precio en una línea (`groupNoPrice`).

  _Requisitos: 3b.1–3b.4_
- [X] T023 Implementación:
  - `agent-rows.tsx`, `agent-builder.tsx`;
  - `publish-bar.tsx` y `barState`;
  - `tests-box.tsx` (coste y botón);
  - `review-panel.tsx`.

  _Requisitos: 3b.1–3b.5_

## Fase 4: Negocio (§4)

- [X] T030 Tests de los modelos (`business-073-model.test.ts`): buscar sin tildes, columnas que nadie usa, grupos plegados y progreso de la revisión.

  _Requisitos: 4.1–4.3, 4.5_
- [X] T031 Tests de componentes:
  - Servicios: grupos plegados, resumen de columnas y búsqueda;
  - Preguntas: plegadas, con ⋯;
  - la página: buscador con su cuenta, barra de revisión, número en el índice, «Marcar todo», zona horaria y moneda por separado, «Leído en inglés».

  _Requisitos: 4.1–4.6_
- [X] T032 Implementación:
  - `business-search.ts`, `review-model.ts`, `services-model.ts`;
  - `services-section.tsx`, `faqs-section.tsx`;
  - `business-sections.tsx`, `section-frame.tsx`, `basics-section.tsx`, `policies-section.tsx`;
  - `?q=` en la página.

  _Requisitos: 4.1–4.6_

## Fase 5: Comprobación

- [X] T040 Consola: tests, typecheck y lint en verde.
- [X] T041 API: los tests de Auditoría, clientes, teléfono y aislamiento tocados, en verde.
- [ ] T042 Staging: contra el recorrido del estudio, antes del lote 6.

  _Requisitos: 5.4_
