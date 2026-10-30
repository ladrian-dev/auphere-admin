# Tareas: 051 — Correos con oficio

**Entrada**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

Test primero (constitución §VII): la prueba se escribe, se ve en rojo y solo entonces se implementa. Las rutas parten de la raíz del repo. `[P]` = paralelizable. Rama `051-correos-con-oficio`, sin commits: los hace el owner al final. Estado al 2026-10-30: T001–T022, T024 y T025 hechas; T023 espera el OK del owner; T026 es la pasada final; T027 y T028 son del owner, tras el despliegue. Mientras se implementa, solo las pruebas de lo tocado; `./scripts/verify.sh` una vez, al cierre.

## Fase 1 — El núcleo (Historia 1 · bloquea todo lo demás)

- [x] T001 Pruebas en rojo del modo por entorno, en `apps/api/tests/unit/test_email_delivery_mode.py`:
  - `auto` se resuelve a `resend` en `prod`/`production` y a `log` en `staging`, `dev` y `ci`;
  - `production` con `log` no valida y el error nombra `NEXUS_EMAIL_DELIVERY`;
  - `staging` con `resend` sí arranca;
  - `email_delivers` solo es cierta con modo `resend` y clave real.

  _Requisitos: 1.1, 1.3, 1.4_
- [x] T002 Ajustes en `apps/api/src/nexus_api/config.py`:
  - `email_delivery` y su propiedad `email_mode`;
  - la guardia de producción en el validador;
  - `email_delivers`, que sustituye a `email_enabled` (y su uso en `api/console/signup.py`);
  - `notifications_from_email` (renombra `signup_from_email`), `email_reply_to`;
  - se quita `smtp_url`.

  T001 en verde. _Requisitos: 1.1, 1.3, 1.4, 5.1, 5.2_
- [x] T003 [P] Pruebas en rojo del catálogo, en `apps/api/tests/unit/test_email_catalog.py`. Por cada `EmailKind`:
  - tiene ficha y alias `es`, y `en` en todos los tipos menos `internal_alert`;
  - los alias son únicos y siguen el formato;
  - las claves cumplen el formato y el tope, y ninguna es reservada;
  - `link_variables` está contenido en `variables`;
  - `password_changed` no tiene ninguna variable de enlace;
  - `billing` es el remitente de `receipt` y `charge_confirm`, y de ninguno más.

  Además, `format_day_es`, `format_month_es`, `console_link` y `lines_variable`, incluido el recorte con «y N más» dentro de 2 000 caracteres. _Requisitos: 2.1, 2.6, 5.2, 6.1, 6.3_
- [x] T004 `apps/api/src/nexus_api/services/email_catalog.py` con `EmailKind`, `EmailSpec`, `EmailLines`, `CATALOG` y las ayudas, todo según [data-model.md](data-model.md) y [contracts/catalogo.md](contracts/catalogo.md). T003 en verde. _Requisitos: 2.1, 2.4, 2.6_
- [x] T005 Pruebas en rojo del envío, en `apps/api/tests/unit/test_email_send_template.py`, con `respx` para el transporte:
  - modo `log`: ninguna llamada HTTP; `email.suppressed` con `kind`, `template`, `to`, `subject` y `links` (solo las variables de enlace); devuelve `True`;
  - modo `resend`: el cuerpo lleva `template.id` = alias, variables escapadas (`<b>&</b>` → `&lt;b&gt;&amp;&lt;/b&gt;`), `from` según la ficha, `reply_to` = `support@auphere.com`, `subject` y la etiqueta `kind`, y **no** lleva `html` ni `text`; `email.sent` sin `links`;
  - un `EmailLines` no se escapa dos veces;
  - el inglés usa su alias, y un tipo sin alias `en` cae al `es`;
  - con una variable de menos o de más: `False`, ninguna llamada y `email.variables_mismatch`;
  - una cadena de 2 500 caracteres se recorta y el envío sale;
  - Resend con 422: `False` y `email.send_failed` con estado, tipo y alias;
  - `reply_to` explícito gana al de los ajustes.

  _Requisitos: 1.1, 1.2, 1.5, 2.3, 5.1, 6.2, 6.3, 7.2_
- [x] T006 Reescribir `apps/api/src/nexus_api/services/email.py`: `send_template` según el plan. Se borran `send_email`, `_smtp_send` y el repliegue SMTP. T005 en verde. _Requisitos: 1.1, 1.2, 1.5, 2.3, 6.2, 6.3, 7.2_
- [x] T007 [P] `email.delivery_mode` en el arranque de la API y del worker (en `warning` si es staging con `resend`); `docker-compose.yml` sin `mailhog` ni `NEXUS_SMTP_URL`. _Requisitos: 1.4_

## Fase 2 — Cada sitio que envía pasa al catálogo (Historias 2, 3 y 5)

Cada tarea adapta **primero** las pruebas existentes de ese sitio para que capturen `send_template` (tipo, asunto y variables) en vez de HTML, y las ve en rojo.

- [x] T008 [P] Alta: `services/signup.py` → `signup_link` / `signup_existing`, con la regla de idioma de la contraseña. Pruebas:
  - `tests/unit/test_signup_mail_sender.py`: sale de notificaciones, no de facturación, ni de «no-reply»; responde a soporte; los dos correos tienen el mismo remitente;
  - `tests/integration/test_signup_flow.py`, `test_admin_signups.py` y `test_signup_mail_failure.py`: 502 solo con `email_delivers`.

  _Requisitos: 4.1, 5.1, 5.2, 5.3, 6.4_
- [x] T009 [P] Contraseña: `services/password_reset.py` → `password_reset` / `password_changed`. Pruebas:
  - `tests/integration/test_password_reset.py` saca el token de `variables["RESET_URL"]`;
  - el aviso de cambio no lleva ninguna variable con `http`, y `SECURITY_CONTACT` es el contacto;
  - `tests/isolation/test_42_reset_scope.py` y `tests/integration/test_app_password_reset.py`.

  _Requisitos: 4.5, 6.1, 6.4_
- [x] T010 [P] Invitaciones: `api/console/team.py` y `scripts/seed_console_memberships.py` → `team_invite` (enlace absoluto, etiqueta de rol de la consola); `services/client_invitation_email.py` → `client_invite`. Pruebas nuevas:
  - `ACCEPT_URL` es absoluto y termina en `/invite/{token}`;
  - `ROLE_LABEL` es «Administrador» para `admin`;
  - la invitación de cliente no nombra al partner.

  También `tests/unit/test_endpoint_console.py:479`. _Requisitos: 2.6, 4.3, 4.5_
- [x] T011 [P] Recibo: `services/partner_receipt_email.py` construye asunto y variables (`LINES` con `lines_variable`), y lo usan `api/admin/receipts.py` y `apps/worker/src/nexus_worker/streams/partner_receipt_cron.py`. Prueba `tests/unit/test_partner_receipt.py`:
  - el asunto es `Tu recibo de junio de 2026 (Facelad SPA)`;
  - `LINES` contiene cada concepto;
  - `FX_NOTE` está vacía sin conversión;
  - `BILLING_URL` termina en `/billing`.

  _Requisitos: 4.1, 5.2, Caso límite «lista»_
- [x] T012 [P] Cobro: `services/partner_billing.py` → `charge_confirm`. Prueba en `tests/integration/test_partner_card_and_charges.py`. _Requisitos: 4.3, 5.2_
- [x] T013 [P] Saldo y consumo:
  - `services/wallet_alerts.py` → `client_out_of_quota`, `wallet_low` y `wallet_empty`, con el nombre del cliente;
  - `services/usage_alerts.py` → `usage_cap_threshold` y `usage_cap_reached`.

  Pruebas: `tests/integration/test_wallet_alerts.py` y `tests/unit/test_endpoint_console_home_usage.py`. El asunto no lleva «[Auphere]» y tutea. _Requisitos: 1.6, 4.1, 4.4_
- [x] T014 Pruebas en rojo de los textos de aviso, en `apps/api/tests/unit/test_email_notices.py`:
  - **barrido**: todo `NotificationKind` que puede salir por correo al partner o al cliente tiene fila, salvo una lista explícita de los que no salen;
  - cada `HEADING` cabe en 60 caracteres sin el nombre del cliente;
  - ningún texto contiene una cadena de [contracts/redaccion.md](contracts/redaccion.md);
  - `client.activated` elige la variante según `missing`;
  - un tipo desconocido da el texto genérico y `email.notice_without_copy`.

  _Requisitos: 2.5, 4.1, 4.4_
- [x] T015 `apps/api/src/nexus_api/services/email_notices.py` y `services/console_notifications.py`:
  - el partner recibe `partner_notice`, o `client_out_of_quota` para `client.out_of_quota`;
  - el cliente recibe `inbox_waiting`, `client_balance_low`, `client_balance_out` o `client_notice`.

  T014 en verde. Pruebas `tests/unit/test_inbox_lifecycle_mark_waiting.py` (`CONVERSATION_URL` con `/inbox?c=`) y `tests/unit/test_client_balance_alerts.py`. _Requisitos: 1.6, 2.5, 4.2_
- [x] T016 [P] Escalado: `apps/worker/src/nexus_worker/streams/operator_alerts.py` → `conversation_escalated`. Prueba `tests/integration/channels/test_escalation_recipients.py`: con resumen para el personal del cliente y sin él para el partner. _Requisitos: 4.1_
- [x] T017 [P] Internos → `internal_alert`:
  - `api/console/support.py`;
  - `services/account_deletion.py`, con `reply_to` = quien lo pide;
  - `worker/…/meta_reconciliation_cron.py`;
  - `worker/…/platform_watcher.py`, con `[Auphere]` en vez de `[Nexus]`.

  Pruebas: `tests/integration/test_phone_settings_routes.py`, `tests/integration/test_meta_reconciliation.py` y `apps/worker/tests/unit/test_platform_watcher.py`. _Requisitos: 5.1, 6.2_
- [x] T018 Barrido `apps/api/tests/unit/test_email_no_inline_html.py`. Falla si en `apps/api/src`, `apps/api/scripts` o `apps/worker/src`:
  - queda un `send_email`;
  - otro módulo que no sea `services/email.py` nombra `api.resend.com`;
  - una llamada a `send_template` no pasa un `EmailKind`.

  _Requisitos: 2.2 · CE-003_
- [x] T019 Barrido de aislamiento `apps/api/tests/isolation/test_55_email_owner_tagging.py`:
  - recorre con `ast` las mismas carpetas y falla si una llamada a `send_template` con un tipo de dueño `partner` no pasa `partner_id`, o con dueño `client` no pasa `client_ref`;
  - en ejecución, `email.suppressed` y `email.sent` llevan el negocio, y `owner="none"` cuando no hay.

  _Requisitos: 1.6 · Garantía 6_

## Fase 3 — Las plantillas en Resend (Historias 2 y 4)

- [x] T020 Generar el HTML de correo de las 39 plantillas: tema de marca (R10 de [research.md](research.md)), texto de [contracts/catalogo.md](contracts/catalogo.md) y variables de la ficha. Se guarda en `specs/051-correos-con-oficio/evidence/plantillas-iniciales/`. _Requisitos: 3.1–3.5, 4.1–4.5_
- [x] T021 Crear y publicar las 39 plantillas en Resend con su alias, asunto por defecto, remitente, `reply_to` y variables. Borrar el borrador «Untitled Template» **solo si el owner lo confirma**. _Requisitos: 2.1, 3.1–3.5, 5.1_
- [x] T022 `apps/api/scripts/check_email_templates.py` según R7 de [research.md](research.md), con una prueba unitaria (`apps/api/tests/unit/test_check_email_templates.py`) sobre respuestas de Resend simuladas:
  - todo en orden;
  - plantilla sin publicar;
  - variable de menos;
  - dos botones;
  - una muletilla de la lista;
  - un `href` http en `password_changed`.

  Ejecutarla contra la cuenta y guardar la salida en `evidence/comprobacion-plantillas.json`. _Requisitos: 7.1 · CE-002_
- [ ] T023 **Con el OK del owner**: un envío por plantilla a `delivered@resend.dev` con `<b>&</b>` en una variable de texto. Leer el HTML entregado y anotar en `evidence/escapado.md` si Resend escapa. Si escapa, el código deja de escapar y se ajusta T005. _Requisitos: 6.2_

## Fase 4 — Documentación y cierre

- [x] T024 [P] `docs/correos.md` (nuevo); `docs/recuperar-la-contrasena.md` §6; `docs/registro-de-partners.md` §5 ter y §5 quater; `docs/paso-a-produccion-031-041.md`. _Requisitos: 8.1_
- [x] T025 [P] KB: el enlace a esta spec en `research/2026-10-30-correos-con-oficio.md` y el banner del 2026-10-30 en `nexus-state.md`. _Requisitos: §IX_
- [x] T029 Staging envía solo los correos de acceso (segunda revisión del owner): `EmailSpec.access`, el modo `access` (por defecto en staging), la guardia de producción contra `access`, y las pruebas de `test_email_delivery_mode.py`, `test_email_send_template.py` y `test_email_catalog.py` primero en rojo. Docs: `docs/correos.md`. _Requisitos: 1.1, 1.3, 1.4_
- [x] T030 Las alertas de monitorización dejan de ir por correo (tercera revisión del owner): `platform_watcher._notify` y `meta_reconciliation_cron` solo registran, con nivel de error. Se retiran `operator_alert_email` y `NEXUS_OPERATOR_ALERT_EMAIL` en Terraform. Pruebas primero en rojo: `apps/worker/tests/unit/test_platform_watcher.py` y `apps/api/tests/integration/test_meta_reconciliation.py` comprueban que no sale correo y que el registro lo lleva. _Requisitos: 9.1, 9.2, 9.3_
- [x] T026 Pasada final (a petición del owner, sin suites completas; el pipeline las corre): `./scripts/verify.sh lint` en verde (ruff, format y `mypy --strict` de los cinco paquetes) y todos los archivos de prueba tocados: API 358 en verde (30 archivos), worker 22 en verde. Una pasada larga anterior, cortada a mitad, dio un fallo hacia el 16 % de la API. Cae en archivos que no tocan el correo, y sus 137 pruebas pasan aisladas: no se reprodujo. _Requisitos: CE-005_
- [ ] T027 Después del despliegue a staging, por el owner: recorrer [quickstart.md](quickstart.md) §4, comprobar en Resend que no hay envíos y guardar la consulta de Logs Insights en `evidence/`. _Requisitos: CE-001_
- [ ] T028 Lectura de cinco segundos de cada plantilla por una persona ajena al proyecto, anotada en `evidence/lectura.md`. _Requisitos: CE-004_

## Dependencias

- La Fase 1 bloquea la 2. Dentro de la 2, T014 va antes de T015, y T018 y T019 van al final, cuando ya no queda ningún `send_email`.
- La Fase 3 depende solo de T004, el catálogo con las variables definitivas, y puede ir en paralelo con la Fase 2.
- T026 va después de todo lo demás. T027 y T028 son del owner, tras el despliegue.
