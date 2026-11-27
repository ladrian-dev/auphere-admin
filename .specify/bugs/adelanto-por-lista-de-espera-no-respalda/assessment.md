# Bug Assessment: un adelanto por lista de espera no respalda la respuesta

- **Slug**: adelanto-por-lista-de-espera-no-respalda
- **Created**: 2026-11-27
- **Source**: revisión de backend antes de producción, hallazgo BE-1 (nota de KB `research/2026-11-26-beta-jemma-p0-p1.md`, «Revisión antes de producción»)
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim)

> `_MADE_OR_MOVED` no incluye `waitlist_accepted`: un adelanto por lista de espera no
> respalda la respuesta (el freno salta sobre una respuesta cierta) y el informe no lo
> cuenta como movida. Reproducido.

## Symptom

Un cliente con una reserva viva acepta una oferta de la lista de espera y su cita se
adelanta. Si en ese ciclo el agente dice que la cita quedó adelantada, el freno de
reservas (spec 080) no encuentra nada que lo respalde y salta sobre una respuesta
cierta. El informe del piloto (spec 083) tampoco cuenta ese adelanto como movida.

## Reproduction

Una reserva del cliente de la conversación, creada hace diez días, con un evento
`waitlist_accepted` dentro del ciclo: `conversation_backed` devuelve `False`. Con
`moved` en lugar de `waitlist_accepted`, devuelve `True`. Lo reproducía la prueba de
la sesión coordinadora (`test_probe_brake.py`); queda como prueba del repo.

## Root Cause

Aceptar una oferta con reserva viva llama a
`move_booking(event="waitlist_accepted")` (`services/reservations/waitlist.py:625`):
el historial de esa reserva no lleva `moved`, sino `waitlist_accepted`.

- `apps/worker/src/nexus_worker/runtime/booking_brake.py:306`:
  `_MADE_OR_MOVED = ("created", "moved")` no lo incluye.
- `apps/api/src/nexus_api/services/client_report.py:70`: `AGENDA_KINDS` filtra la
  consulta y agrupa el recuento por tipo; `waitlist_accepted` ni se lee.

Sin reserva viva, aceptar la crea (`create_booking`, que deja `created`) y añade
`waitlist_accepted` en la **misma transacción**: los dos eventos llevan la misma hora
(`server_default now()`, la del inicio de la transacción). Ese caso ya es un alta.

## Proposed Remediation

- El freno: añadir `waitlist_accepted` a `_MADE_OR_MOVED`. Es una comprobación de
  existencia, así que el caso del alta no cambia nada.
- El informe: leer también `waitlist_accepted` y contarlo como movida, salvo que la
  misma reserva tenga un `created` a la misma hora (el alta desde la lista, ya contada
  como creada). No se toca `AGENDA_KINDS`, que da las claves del recuento.

## Isolation

El paso del freno sigue leyendo el `customer_id` de la fila de la conversación, en la
sesión del negocio (garantía 8). La prueba nueva comprueba también que desde otro
negocio no respalda.

## Out of scope

BE-2 (`contact_customer` sin buscar por `phone`) y el resto de hallazgos de la
revisión quedan en la nota de KB para otra tanda.
