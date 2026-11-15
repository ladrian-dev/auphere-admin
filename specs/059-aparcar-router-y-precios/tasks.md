---

description: "Tareas de la spec 059: aparcar el router y gobernar el precio por modelo"
---

# Tasks: Aparcar el router y gobernar el precio por modelo

**Input**: Design documents from `/specs/059-aparcar-router-y-precios/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/admin-api.md](contracts/admin-api.md)

**Tests**: obligatorios (constitución §VII). Cada tarea de test se escribe y se ve en
rojo antes de la tarea de implementación que la sigue.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **Test primero (§VII)**: rojo antes que implementación.
- **Aislamiento (§I)**: la spec declara la garantía 1, rozada por el barrido de uso. Su test va en T004.
- **Licencias (§VIII)**: no entra ninguna dependencia.
- **Medidor**: no se gasta nada nuevo. Que el cobro use los pesos nuevos se prueba en T027 y se implementa en T028.
- **Una sola entrega** (decisión de Luis). Dentro de ella, el orden importa: el
  bloque Router de Estado (2.4) solo se oculta en T020, después de que la
  protección esté hecha (T010 y T016).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: la historia de la spec (US1…US6)

---

## Fase 1: Base compartida (bloquea US1 y US3)

- [x] T001 Migración `apps/api/alembic/versions/0231_platform_settings.py`:
  - tabla `platform_settings` sembrada con `sale_multiplier = 2.2`, sin RLS y con los permisos de `model_profiles`;
  - columna `model_profiles.status_before_unavailable` con `CHECK` de estados;
  - `downgrade` que lo deshace;
  - el modelo SQLAlchemy de la columna en `db/models/model_profile.py`.

  _Requisitos: 1.7, 3.6_
- [x] T002 [P] Test en rojo `apps/worker/tests/unit/test_platform_default_models.py`. Barre todos los campos `*_model` de `WorkerSettings` y de `nexus_api.config.Settings` y todas las claves de `PLATFORM_MODELS`, y exige que cada uno esté en `default_models()` o en `EXCLUDED` con motivo. También comprueba que `respond_fallback`, `classify_fallback`, `booking_brake`, `qa_classify` y `qa_respond` resuelven lo que usa el runtime.

  _Requisitos: 1.1, 1.5, 5.7_
- [x] T003 Implementar `default_models()` y `EXCLUDED` en `apps/worker/src/nexus_worker/platform_models.py` (research D1).

  _Requisitos: 1.1, 1.5_
- [x] T004 [P] Test de aislamiento en rojo `apps/api/tests/isolation/test_model_usage_scan_rls.py`:
  - dos clientes, cada uno con un agente y una asignación a un modelo distinto;
  - `uses_of` atribuye cada agente y cada asignación a su cliente;
  - lee cada cliente bajo su propio GUC, sin `row_security = off`;
  - solo devuelve recuentos y nombres de cliente (ni ids de agente, ni políticas, ni prompts).

  _Requisitos: 1.2_
- [x] T005 [P] Test en rojo `apps/worker/tests/unit/test_heartbeat_publishes_models.py`. El latido escribe `{"v": 1, "models": default_models()}` con `SETEX 60`, y un fallo de Redis no tumba el bucle.

  _Requisitos: 1.5_
- [x] T006 El latido con su carga, en `apps/worker/src/nexus_worker/health.py`: parámetro `payload`, y en cada punto de entrada que llama a `run_heartbeat`, los modelos de `default_models()`. `/health/workers` de la API sigue funcionando, porque solo mira las claves.

  _Requisitos: 1.5_

---

## Fase 2: US1, nadie deja mudos a los agentes (P1)

- [x] T007 [US1] Tests en rojo `apps/api/tests/integration/models/test_model_usage.py` para `uses_of(key)`:
  - usos por defecto calculados;
  - agentes por asignación de respuesta, por elección propia y por el valor por defecto;
  - clientes con asignación en cualquier rol;
  - verificación: `no_heartbeat` (sin claves), `unpublished` (valor `"1"`), `mismatch` (otro modelo publicado), y la unión de lo calculado con lo publicado.

  _Requisitos: 1.1, 1.2, 1.5_
- [x] T008 [US1] Implementar `apps/api/src/nexus_api/services/model_usage.py`: `ModelUses`, `uses_of`, `verify_defaults` y la caché de 60 s para el listado.

  _Requisitos: 1.1, 1.2, 1.5_
- [x] T009 [US1] Tests en rojo, en `apps/api/tests/integration/models/test_lifecycle_guards.py`:
  - `announce_retirement` y `mark_unavailable` lanzan `model_in_use` o `defaults_unverified` sin cambiar el estado ni auditar;
  - sobre un modelo sin uso se aplican como hoy;
  - `mark_unavailable` guarda `status_before_unavailable`.

  _Requisitos: 1.1, 1.2, 1.3, 1.4_
- [x] T010 [US1] Las guardas, en `apps/api/src/nexus_api/services/model_lifecycle.py`: `uses_of` **sin caché** antes de la transacción, porque la caché de 60 s es solo para el listado, y la columna nueva al marcar.

  _Requisitos: 1.1, 1.2, 1.3, 1.4_
- [x] T011 [US1] Tests en rojo de `cancel_retirement` y `restore_available`, en el servicio y en los endpoints de contrato §4 y §5:
  - estados de vuelta, incluido el de la auditoría antigua y `draft` sin datos;
  - `not_retiring` y `not_unavailable`;
  - auditoría con la persona y el motivo;
  - la publicación del catálogo.

  _Requisitos: 1.6, 1.7_
- [x] T012 [US1] Implementar `cancel_retirement` y `restore_available` en `model_lifecycle.py`, y las rutas `POST …/cancel-retirement` y `POST …/restore` en `api/admin/models_catalog.py`.

  _Requisitos: 1.6, 1.7_
- [x] T013 [US1] Tests en rojo de la retirada detenida (`_retire_due`):
  - con un agente sin sustituto y sin «Automático», ni se mueve ni se retira;
  - audita `deployment.retirement_blocked` una vez por día;
  - emite `model_lifecycle.retirement_blocked`;
  - la fila devuelve `retirement_blocked_agents`;
  - sin agentes atrapados, sigue como hoy.

  _Requisitos: 1.8_
- [x] T014 [US1] Implementar la guarda en `_retire_due` y el cálculo de `retirement_blocked_agents`.

  _Requisitos: 1.8_
- [x] T015 [US1] Tests en rojo de los endpoints `…/retire` y `…/unavailable` en `apps/api/tests/integration/models/test_admin_models_catalog.py`:
  - responden 409 con el detalle del contrato §2;
  - `GET …/deployments` trae `uses` en cada fila.

  _Requisitos: 1.4_
- [x] T016 [US1] `models_catalog.py` traduce `model_in_use` y `defaults_unverified` a 409. `DeploymentRow` gana `uses` y `retirement_blocked_agents`. Se borra `default_respond_model()` del endpoint: lo sustituye el registro.

  _Requisitos: 1.4, 1.8_
- [x] T017 [US1] [P] Tests Vitest en rojo, en `apps/admin/src/app/(dashboard)/models/__tests__/`:
  - un modelo con `uses` no ofrece Retirar ni «No disponible» y enseña «En uso» con los usos;
  - uno en retirada ofrece «Cancelar retirada»;
  - uno no disponible ofrece «Volver a disponible»;
  - «Retirada detenida» se pinta;
  - los diálogos no mencionan el router;
  - el error 409 se muestra con sus palabras.

  _Requisitos: 1.6, 1.7, 1.8, 1.9_
- [x] T018 [US1] El panel: `lib/backend-models.ts` (tipos y llamadas nuevas), `models/actions.ts`, `models/labels.ts` (errores y textos) y los diálogos de cancelar y volver.

  _Requisitos: 1.6, 1.7, 1.8, 1.9_

---

## Fase 3: US2, el router se aparca (P1) — después de T010 y T016

- [x] T019 [US2] [P] Tests Vitest en rojo:
  - con `ROUTER_PANEL_VISIBLE = false`, `NAV` y `allNavItems()` no tienen `/router` ni `/certifications`;
  - las páginas de Router, anomalías y Certificaciones llaman a `notFound()`;
  - Estado no pinta el bloque Router ni sus tres cifras;
  - Modelos no pinta «Nuevo despliegue», «Activar», «Certificado en» ni «Le falta»;
  - con `true`, todo vuelve.

  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
- [x] T020 [US2] Crear `apps/admin/src/lib/router-panel.ts` y aplicarlo en `components/shell/nav.ts`, `router/page.tsx`, `router/anomalies/page.tsx`, `certifications/page.tsx`, `status/page.tsx` y `models/*`, sin tocar API ni worker. Quitar el enlace «Abrir en Router».

  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

---

## Fase 4: US3, Auphere decide el precio de venta (P2)

- [x] T021 [US3] [P] Tests en rojo `apps/api/tests/unit/metering/test_sale_policy.py`:
  - lectura del multiplicador y `None` si falla;
  - propuesta `round(m × coste ÷ 10, 6)`;
  - los carriles por debajo del suelo;
  - el multiplicador menor que 1,5;
  - `weight_drift` con el multiplicador recibido y no la constante.

  _Requisitos: 3.3, 3.4, 3.7, 3.10_
- [x] T022 [US3] Implementar `apps/api/src/nexus_api/metering/sale_policy.py`. `weight_drift` recibe el multiplicador; lo usan `apps/worker/src/nexus_worker/metering/pricing.py` (la comprobación al cargar) y `api/admin/usage_overview.py`.

  _Requisitos: 3.3, 3.4, 3.7, 3.10_
- [x] T023 [US3] Tests en rojo de los endpoints `PUT …/weights` y `GET`/`PUT /admin/models/sale-policy` (contrato §6 y §7):
  - `partial_weights`, `below_floor` con carriles, `per_minute` y `reason_required`;
  - auditoría;
  - `apply_to_all` con una auditoría por modelo y en una transacción;
  - las filas traen `sale` con su `state`.

  _Requisitos: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8, 3.11_
- [x] T024 [US3] Implementar las rutas y `DeploymentRow.sale` y `sale_policy` en `models_catalog.py`.

  _Requisitos: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8, 3.11_
- [x] T025 [US3] Tests en rojo:
  - `add_price` no crea notificaciones `model.price_change`;
  - rechaza `valid_from` anterior a hoy;
  - `POST …/prices` responde sin `alerts`;
  - `run_lifecycle` no emite avisos de precio.

  Se borran los tests de los avisos de precio.

  _Requisitos: 3.12, 4.4_
- [x] T026 [US3] Quitar `_price_alerts`, `message_price_ratio`, `PriceAlert` y `price_notices` de `model_lifecycle.py`, `in_the_past` en `add_price`, y `PriceOut` sin `alerts`.

  _Requisitos: 3.12, 4.4_
- [x] T027 [US3] Test en rojo del medidor. Tras `CATALOG_CHANGED`, `promote_subscriber` invalida `metering.pricing`, y la valoración siguiente del consumidor usa los pesos nuevos sin esperar la caducidad. Lo mismo en la API (`publish_catalog_change`).

  _Requisitos: 3.2_
- [x] T028 [US3] Implementar la invalidación en `apps/worker/src/nexus_worker/runtime/promote_subscriber.py` y en `api/admin/models_catalog.py:publish_catalog_change`.

  _Requisitos: 3.2_

---

## Fase 5: US4, una tabla de Modelos que se lee (P2)

- [x] T029 [US4] [P] Tests Vitest en rojo:
  - la tabla tiene cinco columnas (Modelo, Proveedor, Coste, Venta y Acciones), con «Precio» visible y un menú con las destructivas al final;
  - el diálogo de coste viene precargado con la fecha de hoy y la frase del margen (4.5), y rechaza fechas pasadas;
  - el diálogo de pesos trae la propuesta, rechaza el suelo por carril y exige motivo;
  - el diálogo del multiplicador ofrece «aplicar a todos»;
  - los chips «Desfasado» y «Bajo el suelo»;
  - el modelo por minuto sin pesos;
  - el estado parcial sin multiplicador;
  - la cabecera no promete protecciones.

  _Requisitos: 3.1, 3.3, 3.8, 3.9, 3.11, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
- [x] T030 [US4] Rehacer `models/page.tsx`, `deployments-table.tsx`, `deployment-dialogs.tsx`, `labels.ts` y `actions.ts`, y añadir los tipos en `lib/backend-models.ts`, con los tokens de `@nexus/ui`, sin colores ni estilos en línea.

  _Requisitos: 3.1, 3.3, 3.8, 3.9, 3.11, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

---

## Fase 6: US5, terminar o quitar lo que está a medias (P3)

- [x] T031 [US5] [P] Tests en rojo:
  - `judge_calibrated(session, model=…)` ignora la calibración de otro modelo;
  - el worker (`jobs/handlers/agent_tests.py`) y la consola (`api/console/agent_tests.py`) le pasan el juez del registro;
  - `GET /admin/builder/judge-calibration` trae `judge_model` y `judge_calibrated`.

  _Requisitos: 5.4, 5.5_
- [x] T032 [US5] Implementar el juez por modelo en `services/testing/judge.py`, en los dos llamantes y en `api/admin/sector_tests.py`, y que `builder/judge-calibration/*` nombre al juez.

  _Requisitos: 5.4, 5.5_
- [x] T033 [US5] [P] Tests en rojo: `GET /admin/builder/eval` trae `bank_size = len(bank())`, y la pantalla dice ese número y no pinta `sector_pass_unedited_pct`.

  _Requisitos: 5.6_
- [x] T034 [US5] Implementar `bank_size` en `sector_tests.py` y retocar `builder/eval/*`.

  _Requisitos: 5.6_
- [x] T035 [US5] [P] Tests en rojo:
  - `GET /admin/whatsapp/login-beta/countries` devuelve `{configured, countries}`;
  - sin configuración, `channels-tabs.tsx` no tiene la subpestaña y su página da `notFound()`.

  _Requisitos: 5.3_
- [x] T036 [US5] Implementar `configured` en `whatsapp_login_beta.py`, `lib/backend-whatsapp-beta.ts` y `channels/*`.

  _Requisitos: 5.3_
- [x] T037 [US5] [P] Test en rojo: el Playground construye su grafo con `default_models()["qa_classify"]` y `["qa_respond"]`, que son los del runtime.

  _Requisitos: 5.7_
- [x] T038 [US5] Implementar en `api/qa.py`: las constantes salen del registro.

  _Requisitos: 5.7_
- [x] T039 [US5] Borrar `apps/admin/src/app/(dashboard)/qa/dev/ucm-gallery`, y lo que solo usa ella si nadie más lo importa (barrido con grep antes de borrar).

  _Requisitos: 5.2_

---

## Fase 7: US6, Números de Auphere como el resto del panel (P3)

- [x] T040 [US6] [P] Tests en rojo en `apps/api/tests/integration/test_endpoint_auphere_channels.py`:
  - `POST`, `PATCH` y `DELETE` exigen `X-Operator-Id`, y `PATCH` y `DELETE` exigen `reason`;
  - la auditoría registra `operator:{id}` y el motivo;
  - `PATCH` cambia el token y el identificador.

  _Requisitos: 6.2, 6.4_
- [x] T041 [US6] Implementar en `api/admin/auphere_channels.py`, con `require_operator` y `operator_actor`.

  _Requisitos: 6.2, 6.4_
- [x] T042 [US6] [P] Tests Vitest en rojo `apps/admin/src/app/(dashboard)/auphere/channels/__tests__/`:
  - cabecera y `metadata.title`;
  - tabla sin «Rotar secret» ni columna de secreto;
  - diálogo de edición con token, identificador y motivo;
  - confirmación dentro de la página, sin `window.confirm` ni `prompt`;
  - el estado vacío con su frase.

  _Requisitos: 5.1, 6.1, 6.2, 6.3, 6.5_
- [x] T043 [US6] Rehacer `auphere/channels/*` con `@nexus/ui`, en español neutro, y con las llamadas de `lib/backend.ts` con operador y motivo.

  _Requisitos: 5.1, 6.1, 6.2, 6.3, 6.4, 6.5_

---

## Fase 8: Cierre

- [x] T044 Spec viva, en el mismo commit:
  - `docs/modelos-y-router.md`: router aparcado en el panel, guardas, vuelta, retirada detenida y registro de valores por defecto;
  - `docs/billing.md`: multiplicador como ajuste, pesos desde el panel y fin de los avisos de precio;
  - `docs/admin.md`: las pantallas.

  _Requisitos: 1.1, 1.8, 2.1, 3.6, 3.12, 6.1_
- [x] T045 Verificación:
  - `./scripts/verify.sh lint`;
  - las suites tocadas de la API (isolation, integration/models, unit), una a una;
  - el worker unit con `uv run --with lupa`;
  - el panel: `vitest` de las carpetas tocadas, `tsc` y `next build`.

  Las suites completas solo corren de camino a `main`.

  _Requisitos: todos_
- [x] T046 Pase vivo en local con `quickstart.md`, pasos 1 a 7, a 1280 px, y la auditoría de UI del workspace (5 estados, a11y, responsive, tokens) sobre Modelos y Números.

  _Requisitos: 4.1, 4.6, CE-003, CE-004_
- [x] T047 Entregar el mensaje de commit (o los mensajes por bloque) en un `.sh` de `.claude/commits/`, sin ejecutar nada.

  _Requisitos: —_

---

## Dependencias

- T001 → T009, T011, T021 y T023 (columna y ajuste).
- T003 → T006, T008 y T037.
- T008 → T010 → T016 → **T020** (2.4 depende de la protección).
- T022 → T024 → T030.
- Las tareas de test [P] de fases distintas pueden escribirse a la vez. Cada
  implementación espera a su test en rojo.
