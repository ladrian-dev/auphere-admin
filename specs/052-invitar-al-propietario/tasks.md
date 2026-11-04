# Tareas: Invitar al propietario

**Entrada**: [`spec.md`](spec.md), [`plan.md`](plan.md), [`research.md`](research.md), [`data-model.md`](data-model.md), [`contracts/admin-api.md`](contracts/admin-api.md).

**Reglas**: cada tarea cita sus requisitos. Prueba primero: el bloque de pruebas de cada fase se escribe y se ve en rojo antes que su implementación. Sin `skip`. Es el único plan de ejecución.

**Pruebas**: `apps/api/tests/integration/test_admin_owner_invitation.py` se llama aquí **API**, y `apps/api/tests/isolation/test_owner_invitation_scope.py`, **AISL**. Base y Redis propios: `NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_test_052 NEXUS_REDIS_URL=redis://localhost:6379/14`. Nunca dos pytest a la vez. En ninguna prueba sale correo: modo `log`, o `respx` delante de Resend.

## Fase 1: Preparación

- [X] T001 Dejar la spec como aprobada, con fecha, en `specs/052-invitar-al-propietario/spec.md`, y la rama `052-invitar-al-propietario-impl` sobre `origin/develop`, con `uv sync --frozen --extra dev` y `pnpm install --frozen-lockfile` en este worktree.
  _Requisitos: todos (puerta de la spec)_

## Fase 2: Cimientos (bloquean todas las historias)

- [X] T002 [P] Prueba en API, en rojo: la columna `partner_invitations.last_sent_at` existe, es `TIMESTAMPTZ` y admite nulos; `invitation_is_live_clause` deja fuera una `pending` vencida; las migraciones tienen una sola cabeza; las tres acciones están en `console_audit_vocabulary`.
  _Requisitos: 2.5, 3.9, 6.4_
- [X] T003 [P] Escribir AISL en rojo. **Barre** `app.routes`: toda ruta de escritura bajo `/admin/` cuya ruta nombre una invitación o cuyo manejador use el servicio de invitaciones o `PartnerInvitation*`. Una ruta nueva entra sola; un campo de cuerpo que el barrido no sepa rellenar lo pone en rojo. Para cada una: sin token, con credencial de consola, de clave de partner o de dispositivo → 401; sin operador, con uno inexistente o deshabilitado → 400; nada cambia. Para las que llevan `{invitation_id}`: la invitación de A por la ruta de B da el mismo código y los mismos bytes que una inexistente, y A queda igual, sin auditoría ni correo. Ninguna acepta `tenant_id` ni `partner_id` del llamante. Las sentencias SQL de cada acción no tocan ninguna tabla de tenant, entendida como tabla con RLS activa en el catálogo de Postgres, salvo las filas de plataforma de `audit_log` y `embed_audit_log`. El registro del correo, enviado o retenido, lleva `partner_id`. Aceptar sigue respetando que una cuenta es de un solo sitio.
  _Requisitos: 6.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_
- [X] T004 Migración `apps/api/alembic/versions/0217_owner_invitation_sent_at.py` sobre `0216_out_of_balance_notice_once`: `last_sent_at` (`TIMESTAMPTZ NULL`, sin relleno) y las tres frases, sin más escrituras. `last_sent_at` en `apps/api/src/nexus_api/db/models/partner_membership.py`.
  _Requisitos: 2.5, 3.11, 6.4_
- [X] T005 En `apps/api/src/nexus_api/repositories/partner_membership.py`: `invitation_is_live_clause(now: datetime)` con la condición `status == pending AND expires_at > now`, y `accept` toma la fila con `FOR UPDATE` antes de decidir. Sin cambiar la firma de `create`, `list_pending` ni `get_pending_by_token`.
  _Requisitos: 3.9, 5.3, 7.6_
- [X] T006 `require_enabled_operator` en `apps/api/src/nexus_api/api/admin/operator.py`: la misma negativa que `require_operator` para una cuenta deshabilitada.
  _Requisitos: 6.3, 7.3_
- [X] T007 Esquemas en `apps/api/src/nexus_api/schemas/partner.py`: `PartnerCreateIn` con `owner_email` obligatorio y sin `contact_email`, `OwnerInviteIn`, `OwnerInvitationResultOut`, `PartnerCreatedOut`, `OwnerInvitationRevokedOut`, `OwnerStateOut`, `PartnerAuditLineOut`; `PartnerInvitationOut` con `last_sent_at` y `from_auphere`. La dirección se recorta, va a minúsculas y se valida por forma, con `max_length=255`.
  _Requisitos: 1.3, 1.11, 2.5_

## Fase 3: Historia 1 — Crear el partner hace llegar el correo (P1)

**Prueba independiente**: crear un partner por la ruta, con el correo retenido: nace encendido, con invitación; ese enlace se acepta y la persona entra como propietaria.

- [X] T008 [US1] Pruebas en API, en rojo: nace con consola encendida y vistas por defecto; invitación de propietario y auditoría en la misma transacción; dirección vacía o sin forma → 422 sin filas; un fallo de la transacción no deja nada y no envía; identificador usado → `slug_taken`, sin correo; dirección de otro partner o de un cliente, activa o no → `address_has_own_console`, sin nada; el envío ocurre con la transacción ya confirmada, y un fallo no la deshace; rol siempre propietario, sin poder pedir otro; variables de la plantilla con `INVITER = Auphere`; idioma de la cuenta o español; enlace absoluto desde `console_base_url`; `contact_email` deja de aceptarse y el contacto queda con la dirección, auditado; aceptar lleva a la consola como propietaria (Historia 1, escenario 4; CE-006).
  _Requisitos: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 6.1, 6.2, 6.3_
- [X] T009 [P] [US1] Pruebas de `apps/admin/src/app/(dashboard)/partners/new/__tests__/new-partner-form.test.tsx`, en rojo: «Correo del propietario» obligatorio, con error en el campo; la explicación de lo que hará crear está antes de enviar; no se pide contacto; el error de dirección ocupada sale en su campo; el aviso no manda a crear una clave; no se navega a una URL con el resultado; una respuesta perdida dice que puede haberse creado y que se compruebe antes de repetir.
  _Requisitos: 1.1, 1.3, 1.5, 1.11, 2.10, 6.6_
- [X] T010 [US1] `apps/api/src/nexus_api/services/owner_invitation.py`: errores con nombre, `is_from_auphere`, comprobación de la dirección por cuenta y por copia, emisión con la regla del contacto y su auditoría, `issue_for_new_partner`, y `deliver` (fuera de la transacción, plantilla `team_invite`, `last_sent_at` si salió).
  _Requisitos: 1.2, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 2.5, 6.1, 6.5, 7.4_
- [X] T011 [US1] `create_partner` en `apps/api/src/nexus_api/api/admin/partners.py`: operador obligatorio, consola encendida, `partner.create` con la persona, `slug_taken`, y `deliver` tras confirmar.
  _Requisitos: 1.2, 1.3, 1.4, 1.6, 6.1, 6.2, 6.3_
- [X] T012 [US1] Actualizar las pruebas que crean partners sin el correo: `apps/api/tests/integration/test_partner_auto_provisioning.py`, `apps/api/tests/integration/test_new_partner_reaches_the_model.py` y `apps/api/tests/integration/test_console_v2_for_all.py`. Barrer con grep cualquier otra llamada, en `apps/api`, `apps/worker`, `scripts/` y `apps/admin`.
  _Requisitos: 1.3, 6.3_
- [X] T013 [US1] `apps/admin/src/lib/backend.ts` (tipos y `createPartner` con operador) y `createPartnerAction` en `apps/admin/src/app/(dashboard)/partners/actions.ts`, que conserva el código de la negativa y distingue la respuesta perdida.
  _Requisitos: 1.3, 1.5, 6.3_
- [X] T014 [US1] `apps/admin/src/app/(dashboard)/partners/new/new-partner-form.tsx` y `new/page.tsx` (`maxDuration = 60`): el campo, la explicación, los errores en su campo, y al terminar la vista de resultado en la misma URL.
  _Requisitos: 1.1, 1.3, 1.5, 1.11, 2.1, 2.10, 6.6_

## Fase 4: Historia 2 — Si el correo no sale, el operador lo sabe y puede resolverlo (P1)

**Prueba independiente**: con el proveedor rechazando, crear: se ve el fallo y un enlace que funciona; la ficha sigue diciendo que no consta; reintentar con el proveedor sano lo deja enviado.

- [X] T015 [US2] Pruebas en API, en rojo, con `respx`: rechazo, sin respuesta, sin proveedor y error interno dan `email_sent = false`, con partner, invitación y enlace válido; el plazo total se respeta aunque el proveedor no responda; sin aceptación no hay `last_sent_at`; el registro de un envío real y de un fallo no lleva el enlace, aunque el proveedor lo devuelva en su error.
  _Requisitos: 1.6, 2.3, 2.5, 6.5_
- [X] T016 [P] [US2] Pruebas de `apps/admin/src/app/(dashboard)/partners/_invitation/__tests__/invitation-result.test.tsx`, en rojo: enviada (dirección, fecha, enlace de recurso, aclaración del proveedor); no salió (partner e invitación existen, no se volverá a mostrar, copiar y reintentar); no se va sola; reintentar sustituye el enlace y dice que el anterior ya no sirve; se anuncia, recibe el foco y funciona con teclado; no dice «entregado» ni «recibido».
  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.7, 2.9_
- [X] T017 [US2] `deliver` en `apps/api/src/nexus_api/services/owner_invitation.py`: plazo total de 25 s y captura de cualquier excepción, sin texto de la excepción en el registro. `apps/api/src/nexus_api/services/email.py`: quita los enlaces de acción del cuerpo de error que registra.
  _Requisitos: 2.3, 6.5_
- [X] T018 [US2] `apps/admin/src/app/(dashboard)/partners/_invitation/invitation-result.tsx`, `_invitation/messages.ts` y `resendOwnerInvitationAction` en `actions.ts`, y usarlos en el alta.
  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.7, 2.9, 6.6_

## Fase 5: Historia 5 — Todo queda dicho y nada cruza de un partner a otro (P1)

**Prueba independiente**: AISL en verde, y la auditoría de un alta completa leída en el panel y en la consola.

- [X] T019 [US5] Pruebas en API, en rojo: `GET /admin/partners/{id}/audit-log` da la frase completa con el correo del operador, solo de ese partner y sin `before_json` ni `after_json`; `/console/audit` da la misma acción con el actor «Auphere»; ninguna fila de auditoría de ninguna acción contiene el token ni el enlace. Y en `apps/api/tests/unit/test_console_audit_words.py`, las tres acciones se leen sin «?».
  _Requisitos: 6.1, 6.4, 6.5_
- [X] T020 [US5] Ruta `GET /{partner_id}/audit-log` en `apps/api/src/nexus_api/api/admin/partners.py` y `actor_label` opcional en `summarise` de `apps/api/src/nexus_api/api/console/audit.py`.
  _Requisitos: 6.4_
- [X] T021 [US5] Tarjeta en `apps/admin/src/app/(dashboard)/partners/[id]/audit/page.tsx` y `listPartnerAuditLog` en `apps/admin/src/lib/backend.ts`, con sus estados: vacío, y error parcial que no tumba la actividad del embed.
  _Requisitos: 6.4_

## Fase 6: Historia 4 — Los partners que ya existen sin propietario (P2)

**Prueba independiente**: sobre un partner existente sin personas, invitar desde Equipo: sale y se acepta. El despliegue no envió nada a nadie.

- [X] T022 [US4] Pruebas en API, en rojo: invitar con la dirección dada aplica 1.5 a 1.10; negativas `has_active_owner`, `invitation_pending` (también con dos peticiones simultáneas), `console_off`, `partner_suspended`, `already_in_team`, `address_already_invited`, `partner_not_found`; una vencida no cuenta como viva, no impide reinvitar a esa dirección, y `members` la saca de las pendientes; `owner` da `can_invite`, `block`, `suggested_email` (la caducada por encima del contacto) y `expired_*`; ninguna invitación sale sola: migrar y leer no llaman al envío.
  _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 2.6_
- [X] T023 [P] [US4] Pruebas de `apps/admin/src/app/(dashboard)/partners/[id]/team/__tests__/owner-invitation-panel.test.tsx` y de `[id]/__tests__/owner-notice.test.tsx`, en rojo: el formulario con la sugerencia editable, y nada enviado sin pulsar; consola apagada, con enlace a Módulos, sin formulario; suspendido; con propietario activo, nada; caducada con su fecha; la línea de la cabecera en cada estado, y sin afirmar nada si la lectura falla.
  _Requisitos: 2.6, 2.7, 2.8, 3.1, 3.2, 3.4, 3.6, 3.7, 3.10, 3.12_
- [X] T024 [US4] `invite` y `read_state` en `apps/api/src/nexus_api/services/owner_invitation.py`; `POST /{partner_id}/invitations` en `apps/api/src/nexus_api/api/admin/partner_invitations.py`, montada en `api/admin/__init__.py`; `GET /{partner_id}/members` con `owner`, y solo vivas.
  _Requisitos: 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_
- [X] T025 [US4] `inviteOwnerAction` en `actions.ts`, `apps/admin/src/app/(dashboard)/partners/[id]/team/owner-invitation-panel.tsx`, `team/page.tsx` (`maxDuration = 60`, textos de R2.8 y estado vacío honesto), y `[id]/owner-notice.tsx` en `[id]/layout.tsx`.
  _Requisitos: 2.6, 2.7, 2.8, 3.1, 3.2, 3.3, 3.4, 3.6, 3.7, 3.10, 3.12_

## Fase 7: Historia 3 — Reenviar, revocar y corregir la dirección (P2)

**Prueba independiente**: reenviar: el enlace viejo da «no encontrado» y el nuevo abre. Revocar: ninguno abre. Invitar a otra dirección: el contacto cambia con ella.

- [X] T026 [US3] Pruebas en API, en rojo: reenviar da otro enlace para la misma dirección y rol, con plazo completo, y el viejo da 404; negativas con el enlace intacto: `has_active_owner`, `partner_suspended`, `console_off`, y `address_has_own_console` si la dirección pasó a vivir en otro sitio; negativas que dicen qué pasó: `invitation_accepted`, `invitation_revoked`, `invitation_expired`; revocar deja el enlace igual que uno inexistente, sea cual sea el estado del partner; revocar otra vez, o una fila antigua tras un reenvío: éxito con `changed = false`, sin cambio ni auditoría, y el enlace vivo sigue vivo; aceptada: `invitation_accepted`, sin retirar el acceso; no sale correo; invitar a otra dirección tras revocar cambia el contacto si era la anterior; revocar y aceptar a la vez terminan en un solo resultado.
  _Requisitos: 1.10, 4.1, 4.2, 4.4, 4.5, 5.1, 5.3, 5.4, 5.5, 5.6_
- [X] T027 [P] [US3] Ampliar `owner-invitation-panel.test.tsx`, en rojo: reenviar enseña el resultado y dice que el anterior no sirve; el botón se bloquea durante la petición; revocar pide confirmación nombrando dirección y enlace; si la persona ya aceptó se dice y no queda un enlace muerto en pantalla; con consola apagada, suspendido o propietario activo no hay reenviar y sí revocar, y se dice por qué, avisando de que quien acepte verá que no tiene acceso; un `changed = false` no dice que el enlace haya muerto.
  _Requisitos: 4.1, 4.3, 4.4, 4.5, 5.1, 5.2, 5.5_
- [X] T028 [US3] `resend` y `revoke` en `apps/api/src/nexus_api/services/owner_invitation.py` y sus dos rutas en `apps/api/src/nexus_api/api/admin/partner_invitations.py`, con `404` de cuerpo único.
  _Requisitos: 4.2, 4.4, 4.5, 5.1, 5.3, 5.4, 5.5, 5.6, 7.1, 7.2_
- [X] T029 [US3] `revokeOwnerInvitationAction` en `actions.ts`, y los controles de reenviar y revocar en `owner-invitation-panel.tsx`.
  _Requisitos: 2.4, 4.1, 4.3, 4.5, 5.1, 5.2, 5.5_

## Fase 8: Documentación viva, revisiones y cierre

- [X] T030 [P] `docs/registro-de-partners.md`: el alta desde el panel y en qué se diferencia de la autónoma. `docs/pendientes-tras-el-go-live.md` §1: el script deja de ser la vía del operador. Ayuda de `apps/api/scripts/seed_console_memberships.py`. `docs/admin.md` y `docs/correos.md`: lo que cambia. `apps/api/tests/isolation/README.md`: la prueba nueva.
  _Requisitos: 8.1, 8.2, 8.3_
- [X] T038 Lo que encontró la revisión independiente, con prueba primero: el token fuera del registro de acceso, del `path` de `structlog` y del span, con barrido de rutas en `apps/api/tests/isolation/test_tokens_stay_out_of_request_logs.py`; sin revalidar mientras hay un enlace en pantalla; un reintento perdido retira el enlace; el panel no firma como Auphere a una persona del partner; el filtro «Auphere» de la consola encuentra al operador.
  _Requisitos: 2.1, 2.3, 4.3, 6.4, 6.5_
- [X] T031 Revisión `ui-states-checklist` sobre el alta, la vista de resultado y Equipo; arreglar lo que salga.
  _Requisitos: 2.1, 2.9_
- [X] T032 Revisión `a11y-audit`: foco visible, objetivos de 24 px, anuncio del resultado, teclado; arreglar lo que salga.
  _Requisitos: 2.9_
- [X] T033 Revisión `responsive-audit` con texto largo a 360 px; arreglar lo que salga.
  _Requisitos: 2.9_
- [X] T034 Revisión `design-tokens`: sin colores ni valores fuera de la escala; arreglar lo que salga.
  _Requisitos: 1.1_
- [X] T035 `/cso` sobre el diff, porque toca autorización y entrada de un correo. Decir cualquier hallazgo rojo que quede.
  _Requisitos: 6.3, 6.5, 7.1, 7.2, 7.3_
- [X] T036 Verificación de cierre: los archivos tocados y `tests/isolation/test_console_scope.py`; `./scripts/verify.sh lint`; `pnpm typecheck`, `pnpm lint`, `pnpm test` y `pnpm build` en `apps/admin`.
  _Requisitos: 7.7_
- [X] T037 Puente con la KB: `research/2026-11-03-invitar-al-propietario` deja de decir «pendiente de aprobación» y enlaza la implementación.
  _Requisitos: 8.1_

## Dependencias

```text
Fase 2 ─► Historia 1 ─► Historia 2 ─► Historia 5
                │
                └────► Historia 4 ─► Historia 3 ─► Fase 8
```

La Historia 3 usa `read_state` y el panel de la Historia 4. La Historia 2 reintenta con la ruta de reenviar, que nace en T028: `T016` lo prueba contra una acción simulada, y hasta T028 el botón responde 404.

**En paralelo**, por ser archivos distintos: T002/T003; cada prueba de panel con la de API de su fase; T030 con cualquier otra. Las pruebas de API comparten archivo y base: en serie.

**Fuera de cualquier tarea, por decisión**: CE-001 de punta a punta en staging lo comprueba Luis tras fusionar (`quickstart.md`).

## Cobertura de criterios

| Requisito | Tareas | Prueba |
|---|---|---|
| 1.1, 1.11 (formulario) | T009, T014 | `new-partner-form.test.tsx` |
| 1.2–1.10, 1.11 (API) | T008, T010, T011 | API |
| 2.1–2.4, 2.7, 2.9 | T016, T018 | `invitation-result.test.tsx` |
| 2.5 | T002, T004, T010, T015 | API |
| 2.6, 2.8 | T022–T025 | API, `owner-invitation-panel.test.tsx` |
| 2.10 | T009, T014 | `new-partner-form.test.tsx` |
| 3.1–3.11 | T022, T024 | API |
| 3.1, 3.2, 3.4, 3.6, 3.7, 3.10 (pantalla) | T023, T025 | `owner-invitation-panel.test.tsx` |
| 3.12 | T023, T025 | `owner-notice.test.tsx` |
| 4.1–4.5 | T026–T029 | API, `owner-invitation-panel.test.tsx` |
| 5.1–5.6 | T026–T029 | API, `owner-invitation-panel.test.tsx` |
| 6.1–6.3 | T008, T011 | API, AISL |
| 6.4 | T002, T019–T021 | API, `test_console_audit_words.py` |
| 6.5 | T015, T017, T019 | API |
| 6.6 | T009, T018 | `new-partner-form.test.tsx`, `invitation-result.test.tsx` |
| 7.1–7.7 | T003 | AISL |
| 8.1–8.3 | T030 | Revisión del documento; 8.3 con `--help` |
