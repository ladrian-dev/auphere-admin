# Plan: Invitar al propietario

**Rama**: `052-invitar-al-propietario-impl` · **Fecha**: 2026-11-03 · **Spec**: [spec.md](spec.md) · **Base**: `origin/develop` (`09d579ef`)

## Resumen

Crear un partner desde el panel pasa a ser, en una sola transacción, partner con la consola encendida + invitación de propietario + auditoría, y después, fuera de ella, el correo. El panel enseña el resultado en una vista que no se va sola, con el enlace absoluto, sin ponerlo en ninguna URL. La pestaña Equipo gana invitar, reenviar y revocar; la cabecera de la ficha dice cuándo un partner no tiene propietario activo.

Lo nuevo en datos es una columna, `partner_invitations.last_sent_at`, que distingue «el proveedor aceptó» de «no consta». Lo demás reutiliza lo que ya hay: `PartnerInvitationRepository`, `send_template`, la plantilla `team_invite` y `require_operator`.

## Contexto técnico

| | |
|---|---|
| **Lenguaje** | Python 3.11 (API); TypeScript strict, Next.js 16 (`apps/admin`) |
| **Dependencias** | Las que ya hay. **Ninguna nueva** |
| **Almacenamiento** | Una columna en una tabla de plataforma (`partner_invitations`) y tres filas en `console_audit_vocabulary`. Migración `0217_owner_invitation_sent_at` sobre `0215_inbox_clear_archive_vocab` |
| **Pruebas** | `pytest` + `respx` (API); `vitest` + Testing Library (panel). Sin Resend real: el modo `log` de tests y `respx` para el proveedor |
| **Restricciones** | CE-002: resultado en menos de 30 s con el proveedor sin responder. `send_template` tiene 20 s **por fase** de `httpx`, así que el servicio le pone un plazo total de 25 s. El panel declara `maxDuration = 60` en sus dos páginas: una función de Vercel que muriera antes dejaría a la operadora sin la vista |
| **Alcance** | 3 rutas de escritura y 1 de lectura nuevas en `/admin/partners`, 2 extendidas (crear y `members`), 1 servicio, 2 pantallas del panel y la cabecera de la ficha |

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | **Garantía 6**: `send_template(..., partner_id=...)`, cubierto por el barrido de `test_55_email_owner_tagging.py` y por `tests/isolation/test_owner_invitation_scope.py`. **Garantía 1, rozada**: ninguna acción lee ni escribe tabla de tenant; la prueba captura las sentencias SQL de cada acción. **Eje partner ↔ partner** (R7): la prueba barre las rutas de escritura de invitaciones del panel y compara byte a byte la respuesta de una invitación de otro partner con la de una inexistente |
| II | Superficie | ☑ | `0`. No se abre ninguna: la invitación, su enlace y su aceptación ya existen |
| III | Lo leído es dato | ☑ | El nombre del partner y la dirección llegan al correo escapados por `send_template`; en el panel, React los escapa. Ninguno decide a quién ni qué se envía más allá de lo que el operador pulsó |
| IV | Acción consecuente | ☑ | Todas las acciones las dispara una persona; revocar pide confirmación. La auditoría nombra al operador (`operator:<correo>`), también al crear, que hasta hoy escribía un prefijo del token. D3: nunca se envía al contacto sin pulsar |
| V | La pantalla no miente | ☑ | «Enviada» es «el proveedor la aceptó», y se aclara; sin `last_sent_at`, «no consta el envío». Una invitación vencida se pinta como caducada. Sin capacidad no hay botón apagado: se dice por qué y dónde resolverlo |
| VI | Por API | ☑ | El panel llama a la API. Ningún agente interviene |
| VII | Test primero | ☑ | Cada criterio nace como prueba en `tasks.md`; se ve en rojo antes de implementar. Sin `skip` |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | KB | ☑ | `research/2026-11-03-invitar-al-propietario`, enlazada desde el encabezado. Al cerrar, la nota de KB deja de decir «pendiente de aprobación» |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantías 6 y 1 (rozada), y partner ↔ partner | `T003` en `tests/isolation/test_owner_invitation_scope.py` |
| **Licencias** | Ninguna dependencia nueva | — |
| **Medidor** | Nada de modelo, reloj ni herramienta de pago. Un correo más en Resend, que no gasta saldo del partner | — |

## Diseño

Detalle de cada pieza: [`research.md`](research.md) (por qué), [`data-model.md`](data-model.md) (datos y estados), [`contracts/admin-api.md`](contracts/admin-api.md) (rutas y códigos), [`quickstart.md`](quickstart.md) (cómo se comprueba).

### API

**`services/owner_invitation.py` (nuevo)** es el único sitio con las reglas. Ninguna función confirma: la transacción es de quien llama (como `partner_access`), y el envío va aparte.

| Función | Hace | Requisitos |
|---|---|---|
| `issue_for_new_partner` | Comprueba la dirección y emite. La llama `create_partner`, en su transacción | 1.2, 1.5, 1.7, 1.10 |
| `invite` | Bloquea el partner, marca caducadas las vencidas, aplica las negativas y emite | 3.3–3.9 |
| `resend` | Bloquea partner e invitación; repite la comprobación de la dirección; deja la anterior `revoked` y emite otra con plazo completo | 4.2, 4.4, 4.5, 1.5 |
| `revoke` | Bloquea la invitación y la deja `revoked`; idempotente | 5.1, 5.3–5.6 |
| `deliver` | Fuera de la transacción: envía con plazo total y apunta `last_sent_at` si salió. **Nunca lanza** | 1.6, 1.8, 2.5, 7.4 |
| `read_state` | Lo que la pestaña y la cabecera pintan | 2.6, 3.1, 3.2, 3.9, 3.10, 3.12 |

Una invitación **es de Auphere** si es de rol `owner` y `invited_by IS NULL` (`is_from_auphere`). `invitation_is_live_clause(now)` vive en `repositories/partner_membership.py`, idéntica a la de la rama `fix/invitaciones-vencidas-y-enlace`.

**Rutas** (`api/admin/partner_invitations.py`, nuevo, y `api/admin/partners.py`): ver el contrato. Todas las de escritura exigen el token del panel y un operador habilitado (`require_enabled_operator`, nuevo en `api/admin/operator.py`).

**Crear** (`POST /admin/partners`): `PartnerCreateIn` cambia `contact_email` por `owner_email`, obligatorio. El partner nace con `console_enabled=True`. La respuesta es `PartnerCreatedOut`, un `PartnerOut` con `invitation` dentro.

**Vocabulario**: tres acciones nuevas, en la misma migración. **Lectura en el panel**: la pestaña Auditoría solo lee el *embed audit*, así que una acción de operador no se vería; se añade `GET /admin/partners/{id}/audit-log`, con la misma frase que la consola pero nombrando al operador (R6.4, ver `research.md` R7).

**`repo.accept`**: toma la fila con `FOR UPDATE` antes de decidir, para que revocar y aceptar a la vez no acaben en «revocada para el operador, dentro para la persona» (R5.3).

**`send_template`**: limpia los enlaces de acción del cuerpo de error del proveedor antes de registrarlo (CE-005).

### Panel (`apps/admin`)

Dirección estética: la declarada por el repo, ops sobria sobre tokens de `@nexus/ui`. Sin componentes nuevos en el paquete: `Section`, `Callout`, `StatusBadge`, `ConfirmDialog`, `Form`.

| Pieza | Qué es |
|---|---|
| `partners/_invitation/invitation-result.tsx` | **La vista de resultado** (R2): compartida por el alta y Equipo. Enviado o no salió, enlace completo y copiable, reintentar. Se anuncia y recibe el foco |
| `partners/_invitation/messages.ts` | Cada código de negativa de la API, en palabras |
| `partners/new/new-partner-form.tsx` | «Correo del propietario» obligatorio, la explicación antes de enviar y, al terminar, la vista de resultado **en la misma URL** (R6.6) |
| `partners/[id]/team/owner-invitation-panel.tsx` | Invitar, reenviar, revocar y lo que impide cada cosa. Mientras hay un enlace en pantalla no refresca nada (research R10) |
| `partners/[id]/team/page.tsx` | Lee `read_state` y pinta personas, con los textos honestos de R2.8 |
| `partners/[id]/owner-notice.tsx` | La línea de la cabecera, en todas las pestañas (R3.12) |
| `partners/[id]/audit/page.tsx` | La nueva tarjeta con las frases de auditoría |

### Documentos

`docs/registro-de-partners.md` (R8.1), `docs/pendientes-tras-el-go-live.md` §1 (R8.2), la ayuda de `seed_console_memberships.py` (R8.3), `docs/admin.md` y `docs/correos.md`.

## Estructura

```text
apps/api/
├── alembic/versions/0217_owner_invitation_sent_at.py        # nuevo
├── src/nexus_api/
│   ├── api/admin/{partner_invitations.py,partners.py,operator.py,__init__.py}
│   ├── api/console/audit.py                                 # etiqueta de actor opcional
│   ├── db/models/partner_membership.py                      # last_sent_at
│   ├── repositories/partner_membership.py                   # clause y bloqueo en accept
│   ├── schemas/partner.py
│   └── services/{owner_invitation.py,email.py}
├── scripts/seed_console_memberships.py                      # ayuda
└── tests/
    ├── integration/test_admin_owner_invitation.py           # nuevo
    └── isolation/test_owner_invitation_scope.py             # nuevo

apps/admin/src/
├── lib/backend.ts
└── app/(dashboard)/partners/
    ├── actions.ts
    ├── _invitation/{invitation-result.tsx,messages.ts,__tests__/}
    ├── new/{new-partner-form.tsx,page.tsx,__tests__/}
    └── [id]/{layout.tsx,owner-notice.tsx,audit/page.tsx,team/}
```

## Complejidad

| Añadido que la spec no nombra | Por qué | Alternativa descartada |
|---|---|---|
| `GET /admin/partners/{id}/audit-log` y su tarjeta | R6.4 y la Historia 5 piden leer la auditoría en el panel, y la pestaña Auditoría de hoy no lee `audit_log` | Escribir también en el *embed audit*: duplicaría filas y seguiría sin ser una frase |
| `require_enabled_operator` | R6.3 pide un operador **válido**; `require_operator` acepta una cuenta deshabilitada | Cambiar `require_operator` para todos: toca rutas de otras specs sin prueba propia. Queda anotado en el informe |
| Bloqueo en `repo.accept` | Sin él, revocar y aceptar a la vez pueden terminar en un estado que contradice lo que vio el operador | Dejar la carrera: es un enlace de dueño |
| Limpieza de enlaces en `email.send_failed` | CE-005: ningún registro de producción contiene un enlace, y el proveedor puede devolver el cuerpo enviado | Confiar en que Resend nunca lo devuelva: no está garantizado |
| `safe_path` en el registro de acceso, el contexto de `structlog` y el span | CE-005: la ruta de aceptar lleva el token, y salía de la máquina en los tres (research R10) | Mover el token fuera de la ruta: cambia el contrato de la consola y el enlace de los correos ya enviados |
| Plazo total de 25 s en `deliver` | CE-002: el `timeout` de `httpx` es por fase | Bajar el `timeout` global: afectaría a todos los correos |
