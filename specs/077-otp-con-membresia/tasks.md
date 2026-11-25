# Tareas: spec 077

Orden de ejecución. Cada tarea de prueba se ve en **rojo** antes de su implementación. Sin suites completas: solo los archivos de prueba tocados, `verify.sh lint` y los typecheck/tests de las apps tocadas al cierre.

## Fase 0 — Datos

- [x] **T001** Migración `0242_service_memberships`: `tenants.send_only` y `service_memberships` con FORCE RLS, política canónica, `UNIQUE (tenant_id, id)` y `GRANT`. Modelos `ServiceMembership` y `Tenant.send_only`. _Requisitos: 1.2, 6.2_
- [x] **T002** [P] Pruebas de aislamiento, una por garantía tocada:
  - `tests/isolation/test_77_service_membership_scope.py` (garantía 1): la membresía de A no se ve bajo B; la puerta de A no corta a B.
  - `tests/isolation/test_78_otp_code_never_logged.py` (garantía 6): un envío de código, enviado y fallido, no deja el código en ningún log ni en la fila al terminar.

  _Requisitos: 9.4, 4.6_

## Fase 1 — Envío de códigos (Historia 2)

- [x] **T003** Pruebas `tests/integration/test_endpoint_direct_messages_otp.py`:
  - 202 con `code` y payload con cuerpo y botón;
  - 422 `code_required`, `code_not_allowed`, `invalid_code` y `variables_not_allowed`;
  - con variables con nombre, igual que hoy;
  - el log no lleva el código;
  - un duplicado responde como hoy.

  _Requisitos: 4.1–4.5, 4.7, 11.1_
- [x] **T004** `TemplateMessageIn.code`, `resolve_template(allow_authentication=)` y la rama de autenticación de `send_template_message`. _Requisitos: 4.1–4.7_
- [x] **T005** Prueba del despachador (worker): una fila `otp` enviada o fallida queda sin código; el adaptador recibe cuerpo posicional y botón. Implementación en `streams/outbound.py`. _Requisitos: 4.6_

## Fase 2 — Plantillas de autenticación

- [x] **T006** Pruebas:
  - `authentication_components`;
  - el admin crea una de autenticación con `otp` y deja Marketing y Utilidad igual;
  - el `TemplateCreateIn` de la consola construye los componentes de autenticación sin `body_text`.

  _Requisitos: 3.2, 3.3, 3.4_
- [x] **T007** Constructor común y los dos `TemplateCreateIn`. _Requisitos: 3.2–3.4_

## Fase 3 — Claves por cliente

- [x] **T008** Pruebas `tests/integration/test_admin_tenant_keys.py`:
  - lista las claves del cliente, incluida una creada a mano como la de New Air;
  - crea una ligada al cliente con `messages_send`, con partner contenedor si no tiene;
  - rota conservando el cliente, también desde `/admin/partners/{id}/keys/{key}/rotate`;
  - revoca;
  - audita al operador;
  - 404 con la clave de otro cliente.

  La rotación que conserva el cliente se prueba en `test_admin_tenant_keys.py` y, por los tres caminos (ficha del cliente, del partner y consola), en `tests/isolation/test_77_service_membership_scope.py`, vista en rojo sin el arreglo. _Requisitos: 5.1–5.5, 11.3_
- [x] **T009** `api/admin/tenant_keys.py`, `ApiKeyOut.tenant_id` y el arreglo de la rotación en `admin/partners.py`. _Requisitos: 5.1–5.5_

## Fase 4 — Solo envío (Historia 1)

- [x] **T010** Pruebas:
  - `POST /admin/tenants` con `send_only`;
  - `PATCH …/send-only` audita y deja sus números sin agente;
  - `GET …/send-readiness` con y sin membresía;
  - activar un número (por enlace o directo) en un cliente de solo envío deja `agent_enabled=false` y `role=notifications`, y en uno normal no cambia nada;
  - la puerta del entrante trata como solo envío cualquier número de un cliente `send_only`.

  _Requisitos: 1.1, 1.2, 1.4, 1.5, 2.1, 2.3, 2.4_
- [x] **T011** Implementación en `admin/tenants.py`, `schemas/tenant.py` y `services/channel_signup_links.py`. _Requisitos: 1.1–1.5, 2.1_

## Fase 5 — Membresía (Historias 3 y 4)

- [x] **T012** Pruebas `tests/integration/test_wallet_fixed_fee.py`:
  - cobra una vez por clave;
  - no cobra sin saldo;
  - usa la línea de crédito;
  - no toca el tope del cliente;
  - la conciliación cuadra;
  - no aparece como consumo de conversaciones ni como gasto por agente.

  _Requisitos: 8.1, 8.2, 8.4–8.6, 11.4_
- [x] **T013** Kind `fixed_fee`:
  - en el CHECK (migración 0242) y en `LEDGER_KINDS`;
  - `metering/wallet.charge_fixed_fee`;
  - salida en `reconcile_purchased` y en `attention_live._outflow`.

  _Requisitos: 8.1–8.7_
- [x] **T014** Pruebas de la puerta:
  - 402 en el envío directo y en las difusiones;
  - sin membresía, igual que hoy;
  - el despachador marca fallida la plantilla en cola y no toca una respuesta de agente;
  - activa a la bolsa con el periodo vencido corta.

  _Requisitos: 9.1–9.5, 6.7_
- [x] **T015** `services/service_memberships.blocks_sending`, `api/messages.py`, `services/broadcasts.create_broadcast` y `streams/outbound._drain_tenant`. _Requisitos: 9.1–9.5_
- [x] **T016** Pruebas `tests/integration/test_admin_service_membership.py` (Stripe simulado):
  - PUT, GET y archivar (nunca borrar), con 409 si está activa;
  - `no_partner`;
  - `subscription_in_progress`;
  - enlace de pago con cliente propio y metadata sin `client_reference_id`;
  - actualizar desde Stripe;
  - cancelar;
  - cobrar ahora a la bolsa (con y sin saldo);
  - cobros de Stripe y de la bolsa;
  - auditoría del operador.

  _Requisitos: 6.1–6.6, 7.1, 7.7, 7.10, 8.1, 8.8_
- [x] **T017** `billing/checkout.py` (sesión y cliente), `services/service_memberships.py` y `api/admin/service_memberships.py`. _Requisitos: 6, 7.1, 7.7, 7.10, 8_
- [x] **T018** Pruebas `apps/api/tests/unit/test_service_membership_events.py` sobre `handle_entry`:
  - mapa de estados leído de la suscripción;
  - primer cobro fallido corta;
  - un fallo seguido de un pago (o avisos desordenados) deja el estado de Stripe;
  - metadata de otro cliente o suscripción que no coincide no cambia nada;
  - ningún saldo cambia;
  - un aviso con `partner_id` sigue su camino de hoy.

  _Requisitos: 7.2–7.6, 11.2_
- [x] **T019** Rama de membresía en `nexus_worker/billing/process_event.handle_entry`. _Requisitos: 7.2–7.6_
- [x] **T020** Pruebas del cron:
  - cobra la bolsa al vencer;
  - una caída entre el cargo y la fila no cobra dos veces;
  - reintenta y reactiva;
  - relee Stripe como mucho una vez por hora, incluidas las `pending` con sesión y las `past_due`;
  - un enlace nuevo caduca el anterior.

  Más `test_bootstrap_split` con el nombre nuevo. _Requisitos: 7.7, 7.8, 8.3, 8.4_
- [x] **T021** `streams/service_memberships_cron.py` y su registro en `bootstrap.py`. _Requisitos: 7.8, 8.3_

## Fase 6 — Últimos envíos (Historia 5)

- [x] **T022** Prueba e implementación de `GET /admin/tenants/{id}/template-messages` (enmascarado, sin código). _Requisitos: 10.1, 10.2_

## Fase 7 — Panel

- [x] **T023** `lib/backend` y Server Actions con `requireOperator` y `X-Operator-Id`. _Requisitos: 1.5, 5.4, 6.6_
- [x] **T024** Asistente: tipo de cliente, partner opcional y membresía opcional con quién la paga. _Requisitos: 1.1, 6.1, 6.2, 6.3_
- [x] **T025** Ficha:
  - pestañas y cabecera según `send_only`;
  - puesta en marcha de solo envío;
  - «Marcar como solo envío» con confirmación.

  _Requisitos: 1.3–1.6_
- [x] **T026** Pestaña «Envío por API»: claves (crear, rotar y revocar con confirmación; texto completo una vez), cómo llamar y últimos envíos. _Requisitos: 5.1–5.6, 10.1, 10.2_
- [x] **T027** Facturación:
  - tarjeta de membresía (quién paga, importe, estado, enlace con caducidad, actualizar, cobrar ahora, cancelar, quitar);
  - cobros;
  - lo de hoy, intacto.

  _Requisitos: 6.1–6.7, 7.1, 7.7, 7.10, 8.8_
- [x] **T028** Diálogo de plantillas: campos de autenticación y texto fijo de Meta. _Requisitos: 3.1, 3.3_
- [x] **T029** Conexión de canal de un cliente de solo envío sin pasos de agente. _Requisitos: 2.2_

## Fase 8 — Consola

- [x] **T030** Página pública `/pago-recibido`. _Requisitos: 7.9_
- [x] **T031** Formulario de plantillas con autenticación (ES/EN). _Requisitos: 3.1, 3.4_

## Fase 9 — Revisión `/cso` (2026-11-24)

- [x] **T034** La consola no maneja claves de cliente: `api/console/keys.py` filtra `tenant_id IS NULL` al listar y responde 404 al rotar o revocar una; vuelve a rotar sin copiar el cliente. Prueba en `tests/isolation/test_77_service_membership_scope.py`, vista en rojo. _Requisitos: 5.7_
- [x] **T035** Rotar desde la ficha del cliente cuelga la nueva del partner actual del cliente. Prueba en `tests/integration/test_admin_tenant_keys.py`. _Requisitos: 5.8_
- [x] **T036** El despachador, en su barrido, marca `code_expired` y borra los códigos caducados de los clientes que no visita. Prueba en `tests/integration/test_outbound_otp_and_membership.py`. _Requisitos: 4.9_
- [x] **T037** Un enlace abierto se caduca en Stripe antes de cambiar importe o pagador, archivar o cancelar (503 si Stripe no responde, sin guardar), y un enlace nuevo no se abre si el anterior ya se pagó. Pruebas en `tests/integration/test_service_memberships.py`. _Requisitos: 7.13, 7.14_

## Fase 10 — Cierre

- [x] **T032** `docs/envio-directo.md`, `docs/billing.md`, `docs/admin.md` y `seed_tenant_direct.py`. _Requisitos: 12.1, 12.2_
- [x] **T038** `tests/unit/v1_contract.json`: `POST /v1/messages/template` gana `code`, opcional. `/v1` está congelada; es un cambio aditivo y ninguna petición de hoy (Facelad, New Air) cambia. Solo se regeneró esa ruta. Lo encontró `ci` en el PR 58. _Requisitos: 4.1, 4.5, 11.1_
- [x] **T033** Verificación (2026-11-24/25): `verify.sh lint` en verde; worker 1254 (con `lupa`), panel 748 y consola 2568 con tipos limpios, `next build` de las dos; recorrido en el navegador contra la API local; `/cso` sin HIGH ni CRITICAL (sus tres hallazgos, en la fase 9) y las cuatro puertas de UI sin rojos. La API, en local, llegó a 7200 de 8718 pruebas: dos fallaron por el orden de la suite y pasan solas (`test_064_context_cut`, `test_console_identity`), y `test_openapi_contract.py` se quedó colgado en rutas de la consola ajenas a la 077. Luis pidió cortar ahí y dejar el resto a la tubería. Lo que corre:
  - `./scripts/verify.sh lint`;
  - las pruebas tocadas de API y worker;
  - las vecinas que no escribí:
    - envío directo: `test_endpoint_direct_messages`, `test_direct_message_log_trail`;
    - difusiones;
    - aislamiento: `test_14`, `test_21`, `test_43`;
    - Stripe: `test_billing_event_routing`, `test_no_external_debit`, `test_billing_boundary`;
    - libro y conciliación del monedero;
    - `test_bootstrap_split`;
  - typecheck y tests de `apps/admin` y `apps/console`.

  _Requisitos: 11.1–11.4_
