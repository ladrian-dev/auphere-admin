# Bug Assessment: reinvitar tras una invitación vencida da 409

- **Slug**: reinvitar-tras-vencer-da-409
- **Created**: 2026-11-03
- **Source**: encargo de Luis, «soluciones estables y no parches en el alta de partners»; leído en el código y reproducido con pruebas contra `develop` (`09d579ef`)
- **Verdict**: valid
- **Severity**: medium. Bloquea reinvitar a una persona hasta que alguien revoque una invitación que la lista enseña como viva. No hay datos en riesgo ni cruce entre partners: un enlace vencido nunca ha abierto

## Report

> `apps/api/src/nexus_api/api/console/team.py` (`invite`) devuelve «already pending». `PartnerInvitationRepository.create` choca con el índice parcial `uq_partner_invitations_pending_email`, porque la fila sigue `pending`: `get_pending_by_token` solo la marca `expired` al abrir el enlace, y `list_pending` la enseña como pendiente en `GET /console/team`.

## Symptom

Pasados los 21 días, invitar otra vez a la misma dirección responde 409 «an invitation for this e-mail is already pending», y `GET /console/team` sigue listando la vencida como pendiente. Lo esperado: la invitación vencida deja de contar y reinvitar funciona.

## Reproduction

Con pruebas nuevas, todas en rojo contra el código sin arreglar:

1. Invitar, adelantar `expires_at` y pedir `GET /console/team`: la lista la devuelve (`assert [{...}] == []`).
2. Invitar otra vez a esa dirección: `IntegrityError` en `uq_partner_invitations_pending_email` y 409.
3. **Abrir el enlace vencido y luego reinvitar: sigue dando 409** (`assert 409 == 201`). Ver la causa.
4. Dos reinvitaciones a la vez: `[409, 409]`. Ninguna llega a colarse, pero ninguna funciona.
5. `GET /console/onboarding`: el paso «team» sigue hecho con una invitación vencida (`assert True is False`).
6. `GET /admin/partners/{id}/members`: la vencida sale bajo «invitaciones pendientes».

## Suspected Code Paths

- `apps/api/src/nexus_api/repositories/partner_membership.py`: `create` no mira lo que ya hay; `list_pending` filtra solo por estado.
- `apps/api/src/nexus_api/db/models/partner_membership.py`: el índice parcial mira solo `status = 'pending'`. No puede mirar la fecha: `now()` no es inmutable y Postgres no lo admite en el predicado de un índice.
- `apps/api/src/nexus_api/api/console/onboarding.py`: cuenta `pending` sin mirar la fecha.
- `apps/api/src/nexus_api/api/admin/partners.py`: `list_partner_members`, igual, con su propia consulta.
- `apps/api/src/nexus_api/api/console/home.py`: ya mira la fecha, con una copia de la regla.
- `apps/api/src/nexus_api/api/console/invitations.py`: ver abajo.

## Root Cause

Confianza alta, demostrada por los pasos 1 a 6.

**No hay una definición de «viva»**: la fecha solo se mira donde alguien se acordó (`home.py`, `get_pending_by_token`, `accept`), y el índice único, que es quien decide si se puede invitar, solo mira el estado. Una fila vencida sigue ocupando su sitio porque nada la retira al crear.

**La lectura del encargo se queda corta en un punto.** `get_pending_by_token` sí marca la fila como `expired`, pero **ese cambio nunca se guarda**: las dos rutas de `console/invitations.py` lanzan el 404 dentro de `async with session.begin()`, y la excepción deshace la transacción con la marca dentro. Lo mismo pasa con la marca de `accept`. El comentario del repositorio («the partner's list shows it as expired and the e-mail can be re-invited») describe algo que en la práctica no ocurre: abrir el enlace tampoco desbloquea nada. Lo demuestra el paso 3. Por eso la solución no puede apoyarse en esa marca.

## Proposed Remediation

**Preferred**: una sola regla, en el repositorio, y que nadie dependa de que la marca ya esté escrita.

1. `invitation_is_live_clause(now)`, función de módulo en `repositories/partner_membership.py`: `status = 'pending' AND expires_at > now`. Es lo que usará también la spec 052 (criterio 3.9).
2. `create` retira en la misma transacción la fila vencida de esa dirección y ese partner, con un `UPDATE` condicionado, antes de insertar. El índice único sigue siendo el árbitro: con dos peticiones a la vez, la segunda espera el bloqueo de la fila, vuelve a evaluar la condición al confirmarse la primera (ya no coincide), inserta y choca con la fila nueva. Eso es el mismo `IntegrityError` que hoy y el mismo 409, y solo queda una viva.
3. `list_pending`, `onboarding.py`, `home.py` y `admin/partners.py` usan la regla.

**¿Hace falta un cron como `expire-signups-cron`? No.** Basta con marcar al crear y filtrar al leer. Razones:

- **Corrección.** Con lo anterior, ninguna lectura ni escritura depende de que la fila esté marcada: leen la fecha, y quien necesita el sitio en el índice lo libera. Un cron no arreglaría nada que quede roto.
- **Y no bastaría sin el resto.** Un cron diario deja hasta 24 horas de 409 y de lista falsa. Habría que hacer igualmente lo de arriba, así que solo añadiría.
- **El de altas responde a otro problema.** Una solicitud de alta es anónima y su volumen no tiene techo: cualquiera puede crearlas y lo normal es que se abandonen, de modo que el índice parcial crece con basura. Una invitación la crea una persona autenticada con `team:manage`, a ritmo humano, y el propio índice limita a una pendiente por dirección y partner. Lo que se acumula es poco y se va con `ON DELETE CASCADE` del partner.
- **Su coste es real.** Cada cron va en dos sitios (`bootstrap.SCHEDULER_TASK_NAMES` y el contrato de `test_bootstrap_split.py`), y olvidar el segundo ha abortado dos despliegues. Además escribiría cambios de estado sin nadie que los pida, para que los lea nadie.
- **Qué lo haría necesario.** Que alguien empiece a consultar `status = 'expired'` en informes, o que aparezca un flujo que cree invitaciones sin persona detrás a volumen. Hoy ninguno existe. Las filas con `status = 'pending'` vencidas siguen ahí hasta la siguiente invitación a esa dirección, y eso es deliberado: no son «vivas» para nadie.

**Alternatives**:

- Quitar el índice parcial y comprobar en código: pierde al único árbitro que aguanta la concurrencia. Descartado.
- Reutilizar la fila vencida (renovar su token y su fecha): pierde el histórico de qué enlace se emitió y cuándo, y mezcla dos emisiones en una auditoría. Descartado.
- Marcar la caducidad fuera de la transacción de las rutas de `invitations.py` para que se guarde: arregla un síntoma y sigue dependiendo de que alguien abra el enlace, cuando el caso normal es que nadie lo abra. Descartado.

**Files likely to change**:

- `apps/api/src/nexus_api/repositories/partner_membership.py`
- `apps/api/src/nexus_api/db/models/partner_membership.py` (comentario)
- `apps/api/src/nexus_api/api/console/team.py` (docstring), `onboarding.py`, `home.py`
- `apps/api/src/nexus_api/api/admin/partners.py`
- `docs/console.md`, `docs/admin.md`

**Tests to add or update**:

- `tests/unit/test_repo_partner_membership.py`: la regla, la lista, la retirada acotada a esa dirección y ese partner, y las dos carreras (gana una y la otra da `IntegrityError`; si la primera se deshace, la segunda pasa).
- `tests/unit/test_endpoint_console.py`: reinvitar de punta a punta, tras abrir o no el enlace, y dos peticiones simultáneas `[201, 409]`.
- `tests/unit/test_endpoint_console_onboarding.py` y `tests/integration/test_admin_panel_overview.py`.

## Risks & Considerations

- **Aislamiento**: garantía no debilitada. `partner_invitations` es de plataforma, sin RLS; el `UPDATE` va acotado por `partner_id`, que sale del principal. Hay prueba de que no toca la fila de otro partner con la misma dirección. La ruta no recibe `tenant_id` ni `partner_id` del llamante.
- **`invite` no audita la retirada**: es la consecuencia de una fecha, no una decisión de nadie. La invitación nueva sí queda auditada.
- **El paso «team» del onboarding puede volver atrás** cuando una invitación vence sin aceptarse. Es lo correcto: el partner no tiene equipo, y es lo que ya pasaba con una fila marcada `expired`.
- **`seed_console_memberships.py` queda como está**: con una fila vencida dice que ya hay una pendiente, enseña su fecha y pide `--reissue`, que funciona. Es una herramienta de desarrollo y emergencias que la spec 052 también toca.
- **Coordinación**: la spec 052 se implementa a la vez sobre este repositorio. La regla se llama `invitation_is_live_clause(now: datetime)` por acuerdo, y no cambian las firmas de `create`, `list_pending` ni `get_pending_by_token`.

## Open Questions

Ninguna.
