# Tareas: Correcciones de QA de la consola

**Entrada**: `specs/055-correcciones-qa-consola/`, con [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md) y [contracts/console-api.md](contracts/console-api.md).

**Pruebas**: test primero, por la constitución (§VII). Cada test nace rojo.

**Orden**: de menor a mayor, como pidió el owner. `[USn]` es la Historia n de la spec.

## Fase 1: Preparación

- [x] T001 Comprobar el stack local (`.claude/launch.json`, `apps/api/.env`, `apps/console/.env.local`) y que `demo-audit` existe en la base local

## Fase 2: Base

No hay base compartida: cada corte se entrega solo.

## Fase 3: Marcas (US3, P1)

**Objetivo**: el índice de Negocio cambia al guardar, sin recargar. **Prueba independiente**: guardar cada sección y mirar la marca.

- [x] T002 [US3] Test: guardar Datos básicos, Horarios, Servicios, Políticas y Preguntas frecuentes, y «Es correcto», cambian la marca del índice; un fallo no, en `apps/console/src/components/business/sections/__tests__/business-page.test.tsx` _Requisitos: 4.1 a 4.5_
- [x] T003 [US3] `onStateChange` en `basics-section.tsx`, `hours-section.tsx`, `services-section.tsx`, `policies-section.tsx` y `faqs-section.tsx` de `apps/console/src/components/business/sections/` _Requisitos: 4.1 a 4.3_
- [x] T004 [US3] El índice pinta el último estado avisado en `apps/console/src/components/business/sections/business-sections.tsx` _Requisitos: 4.1, 4.4, 4.5_

## Fase 4: Ejemplos (US4, P1)

**Objetivo**: un ejemplo no borra lo escrito. **Prueba independiente**: escribir, pulsar un ejemplo y ver los dos textos.

- [x] T005 [US4] Test de `withExample`: vacío, con texto, repetido y sin sitio, en `apps/console/src/components/builder/__tests__/builder-model.test.ts` _Requisitos: 5.1 a 5.4_
- [x] T006 [US4] Test de pantalla: conserva lo escrito y el nombre, y dice que no cabe, en `apps/console/src/components/builder/__tests__/builder-new.test.tsx` _Requisitos: 5.2, 5.4, 5.5_
- [x] T007 [US4] `withExample` en `apps/console/src/components/builder/builder-model.ts` _Requisitos: 5.1 a 5.4_
- [x] T008 [US4] `pickExample` usa `withExample` y su comentario deja de decir «sustituye», en `apps/console/src/components/builder/builder-new.tsx` _Requisitos: 5.5, 5.6_
- [x] T009 [P] [US4] Texto `agentProto.new.example.noRoom` en `apps/console/src/i18n/lanes/agent-proto.ts` _Requisitos: 5.4_
- [x] T010 [P] [US4] §3.1 dice que el ejemplo se añade, en `specs/047-la-fabrica-de-agentes/evidence/prototipo/agente.md` _Requisitos: 5.6_

## Fase 5: «Señal» (US5, P2)

**Objetivo**: la política se entiende. **Prueba independiente**: abrir Políticas en los dos idiomas.

- [x] T011 [US5] Test: etiqueta y ayuda en lectura y en edición, en `apps/console/src/components/business/sections/__tests__/negocio-enmienda.test.tsx` _Requisitos: 6.1_
- [x] T012 [US5] Test: lo compilado dice «Señal o anticipo» y conserva el valor, en `apps/api/tests/integration/business/test_055_qa_consola.py` _Requisitos: 6.2, 6.3_
- [x] T013 [US5] Textos en `apps/console/src/i18n/lanes/amendment.ts` y `apps/console/src/i18n/lanes/builder-life.ts`, con ayuda «Lo que el cliente paga por adelantado para reservar.» _Requisitos: 6.1, 6.2_
- [x] T014 [US5] La ayuda en `apps/console/src/components/business/sections/policies-section.tsx` _Requisitos: 6.1_
- [x] T015 [US5] Etiqueta en `apps/api/src/nexus_api/services/business/compilation.py` y `apps/api/src/nexus_api/services/builder/agent_draft.py` _Requisitos: 6.2_

## Fase 6: Moneda (US2, P1)

**Objetivo**: la moneda elegida es la que se usa. **Prueba independiente**: crear un cliente con USD con un navegador de la zona euro.

- [x] T016 [US2] Tests de API: sin moneda no hay importe (`price_currency_required`), moneda elegida en el servicio, la fila toma la del negocio, `exponent` por fila, en `apps/api/tests/integration/business/test_055_qa_consola.py` _Requisitos: 3.1, 3.2, 3.7_
- [x] T017 [US2] Tests de API: `prices_would_change` con `count` y `rounds`, confirmar repreciar con el mismo número, cancelar no cambia nada, reservas intactas, auditoría, revisión de Servicios sube, en `apps/api/tests/integration/business/test_055_qa_consola.py` _Requisitos: 3.3 a 3.6, 8.6_
- [x] T018 [US2] `known_currency`, `reprice` y moneda al escribir en `apps/api/src/nexus_api/services/business/services_catalog.py` _Requisitos: 3.1, 3.2, 3.4, 3.6_
- [x] T019 [US2] `update_basics` repreciar al cambiar la moneda, en la misma transacción y auditado, en `apps/api/src/nexus_api/services/business/profile_edits.py` _Requisitos: 3.4, 3.5, 8.6_
- [x] T020 [US2] `confirm_price_change`, 409, `exponent`, `currency` opcional y `price_currency` en `apps/api/src/nexus_api/api/console/business.py` y `schemas_business_sections.py` _Requisitos: 3.2, 3.3, 3.7_
- [x] T021 [US2] `price_currency` y `currency_set` en `apps/api/src/nexus_api/api/console/lite/reservas.py` y `reservas_schemas.py` _Requisitos: 3.1, 3.2_
- [x] T022 [US2] Test de consola: «Más ajustes» con dos campos y el resumen con la de los precios, en `apps/console/src/components/clients/__tests__/client-modal.test.tsx` _Requisitos: 2.1, 2.2, 2.5_
- [x] T023 [US2] Test de consola: Datos básicos con listas y confirmación, en `apps/console/src/components/business/sections/__tests__/business-page.test.tsx` _Requisitos: 2.4, 3.3_
- [x] T024 [US2] Test de consola: los modales con moneda, sin moneda y con decimales, en `apps/console/src/components/business/sections/__tests__/services-section.test.tsx` y `apps/console/src/components/reservas/model/__tests__/money.test.ts` _Requisitos: 3.1, 3.2, 3.7, 3.8_
- [x] T025 [US2] «Más ajustes» en `apps/console/src/components/clients/client-modal.tsx` y sus textos en `apps/console/src/i18n/lanes/business.ts` _Requisitos: 2.1 a 2.3, 2.5_
- [x] T026 [US2] Listas y confirmación en `apps/console/src/components/business/sections/basics-section.tsx` y sus tipos en `apps/console/src/lib/backend/business-sections.ts` _Requisitos: 2.4, 3.3_
- [x] T027 [US2] Modal y filas en `apps/console/src/components/business/sections/services-section.tsx` _Requisitos: 3.1, 3.2, 3.7, 3.8_
- [x] T028 [US2] Modal de Reservas, con ejemplo y error según los decimales, en `apps/console/src/components/reservas/settings/services-settings.tsx`, `apps/console/src/lib/backend/reservas.ts` y `apps/console/src/i18n/lanes/reservas.ts` _Requisitos: 3.1, 3.2, 3.8_

## Fase 7: Recuperar con invitación (US1, P1)

**Objetivo**: quien fue invitado puede entrar. **Prueba independiente**: pedir «Recuperar» con una invitación sin aceptar y usar el enlace nuevo.

- [x] T029 [US1] Test: crear un partner desde el panel envía la invitación y su enlace deja registrarse, en `apps/api/tests/integration/test_055_recuperar_con_invitacion.py` _Requisitos: 1.1_
- [x] T030 [US1] Tests del reenvío: propietario, equipo y cliente, enlace anterior muerto, rol y partner conservados, partner apagado, envío que falla, auditoría, en `apps/api/tests/integration/test_055_recuperar_con_invitacion.py` _Requisitos: 1.2 a 1.5, 1.7, 1.8_
- [x] T031 [US1] Extraer el envío de `team_invite` a una función sin `principal` en `apps/api/src/nexus_api/api/console/team.py` _Requisitos: 1.2_
- [x] T032 [US1] `resend_for_forgot` en `apps/api/src/nexus_api/services/invitation_reissue.py`, con su propia sesión y sin lanzar nunca _Requisitos: 1.2, 1.3, 1.7, 1.8_
- [x] T033 [US1] Añadir la tarea en segundo plano cuando no hay cuenta en `apps/api/src/nexus_api/api/console/password_reset.py` _Requisitos: 1.2, 1.4, 1.6_

## Fase 8: Categorías (US6, P2)

**Objetivo**: los servicios se agrupan. **Prueba independiente**: dos servicios en una categoría y uno sin ella.

- [x] T034 [US6] Migración `apps/api/alembic/versions/0220_service_category.py`: «`category VARCHAR(40) NULL`», y `category` en `apps/api/src/nexus_api/db/models/reservation.py` _Requisitos: 7.1, 7.7_
- [x] T035 [US6] Tests: normalizar, mayúsculas, vacía, más de 40, duplicar, ficha exportada, lista y agente, en `apps/api/tests/integration/business/test_055_qa_consola.py` _Requisitos: 7.1, 7.3, 7.5, 7.6, 7.7_
- [x] T036 [US6] Categoría en `services_catalog.py`, `client_spec.py` y `compilation.py` de `apps/api/src/nexus_api/services/business/` _Requisitos: 7.1, 7.3, 7.5, 7.6_
- [x] T037 [US6] Categoría en `business.py`, `schemas_business_sections.py`, `lite/reservas.py` y `lite/reservas_schemas.py` de `apps/api/src/nexus_api/api/console/` _Requisitos: 7.2, 7.5_
- [x] T038 [US6] Test de consola: agrupar, «Sin categoría» al final, sin grupos si no hay ninguna, en `apps/console/src/components/business/sections/__tests__/services-section.test.tsx` _Requisitos: 7.2, 7.4_
- [x] T039 [US6] Campo y grupos en `apps/console/src/components/business/sections/services-section.tsx`, `apps/console/src/components/reservas/settings/services-settings.tsx`, sus tipos y textos _Requisitos: 7.2, 7.4_

## Fase 9: Aislamiento y cierre

- [x] T040 Tests en `apps/api/tests/isolation/test_055_services_currency_category.py`: la moneda de un cliente no toca los servicios de otro, las categorías no cruzan, un agente con lista no ve las categorías que no ofrece, y una categoría con forma de instrucción llega como dato _Requisitos: 8.2 a 8.5_
- [x] T041 Test en `apps/api/tests/integration/test_055_recuperar_con_invitacion.py`: «Recuperar» contesta lo mismo con cuenta, con invitación viva, con invitación vencida, sin nada y pasado el tope _Requisitos: 1.6, 8.1_
- [x] T042 Regenerar lo que dependa de la API (`apps/mobile/src/api/openapi.json` y `schema.gen.ts`), solo si `verify.sh` lo exige
- [ ] T043 Ejecutar los escenarios de [quickstart.md](quickstart.md) en local con `demo-audit` y `./scripts/verify.sh`
- [ ] T044 Integrar en `develop` con fast-forward, previo visto bueno del owner, y dejar C1, C2 y C4 de la spec anotados

## Dependencias

- Cada fase de la 3 a la 8 es independiente de las demás, salvo que T039 y T027 tocan `services-section.tsx`: categorías va después de moneda.
- T040 depende de las fases 6 y 8. T041 depende de la fase 7.
- T043 y T044 van al final.

## En paralelo

Dentro de una fase, las marcadas con `[P]`. Entre fases, marcas, ejemplos y «Señal» no comparten ficheros salvo `policies-section.tsx` y las de Marcas.

## Estrategia

Las fases 3 y 4 son la primera entrega útil: arreglos pequeños, visibles y sin datos. La moneda y «Recuperar» son las de más riesgo. Categorías va la última porque es lo único que migra datos.
