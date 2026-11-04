# Bug Fix: reinvitar tras una invitación vencida da 409

- **Slug**: reinvitar-tras-vencer-da-409
- **Fixed**: 2026-11-03
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

«Viva» pasa a tener una sola definición, `invitation_is_live_clause(now)`, y ninguna lectura depende ya de que la fila esté marcada. `create` retira la fila vencida de esa dirección y ese partner antes de insertar, y el índice único sigue decidiendo quién gana si hay dos peticiones a la vez. Sin cron.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/repositories/partner_membership.py` | modified | La regla; `create` retira la fila vencida; `list_pending` filtra; comentario corregido sobre la marca que se deshace |
| `apps/api/src/nexus_api/api/console/onboarding.py` | modified | El paso «team» cuenta aceptadas y vivas |
| `apps/api/src/nexus_api/api/console/home.py` | modified | Usa la regla en vez de su copia, sin cambio de comportamiento |
| `apps/api/src/nexus_api/api/admin/partners.py` | modified | La pestaña Equipo del panel solo lista vivas |
| `apps/api/src/nexus_api/api/console/team.py` | modified | Docstring |
| `apps/api/src/nexus_api/db/models/partner_membership.py` | modified | Comentario del índice |
| `docs/console.md`, `docs/admin.md` | modified | Spec viva |

## Diff Highlights

```python
def invitation_is_live_clause(now: datetime) -> ColumnElement[bool]:
    return sa.and_(
        PartnerInvitation.status == InvitationStatus.PENDING.value,
        PartnerInvitation.expires_at > now,
    )
```

En `create`, antes de insertar: `UPDATE … SET status = 'expired' WHERE partner_id, email, status = 'pending' AND NOT invitation_is_live_clause(now)`.

## Tests Added or Updated

- `tests/unit/test_repo_partner_membership.py::test_live_clause_is_pending_and_within_its_term`: la regla contra todos los estados y el instante exacto del vencimiento.
- `…::test_list_pending_leaves_out_an_overdue_invitation`: la lista.
- `…::test_reinviting_retires_only_the_overdue_row_of_that_address`: no toca otra dirección ni otro partner.
- `…::test_simultaneous_reinvitations_leave_one_live_row`: la segunda espera el bloqueo de verdad (comprobado en `pg_stat_activity`), recibe `IntegrityError` y queda una viva.
- `…::test_reinvitation_goes_through_if_the_one_ahead_rolls_back`: si la primera se deshace, la segunda pasa.
- `tests/unit/test_endpoint_console.py::test_reinvite_after_expiry_works_and_the_list_tells_the_truth`: de punta a punta, con el enlace viejo muerto, el nuevo vivo y una invitación viva que sigue bloqueando.
- `…::test_reinvite_works_whether_or_not_someone_opened_the_dead_link`: fija que nada depende de la marca.
- `…::test_two_simultaneous_reinvites_one_wins_the_other_gets_409`: `asyncio.gather` real, `[201, 409]`.
- `tests/unit/test_endpoint_console_onboarding.py::test_team_step_does_not_count_an_invitation_past_its_term`.
- `tests/integration/test_admin_panel_overview.py::test_members_does_not_show_an_invitation_past_its_term_as_pending`.

## Local Verification

- En rojo antes del arreglo: 10 fallos, cada uno por la causa esperada (`[409, 409]`, `assert 409 == 201`, `UniqueViolationError`, lista con la vencida).
- En verde después: ver `./test.md`.

## Deviations from Assessment

Ninguna.

## Follow-ups

- La spec 052 se implementa a la vez y usa `invitation_is_live_clause`. Puede chocar al fusionar en `list_partner_members` (`admin/partners.py`), que esa spec reescribe para enseñar la caducada: gana su versión.
- `seed_console_memberships.py` no usa la regla, a propósito (ver el assessment).
