# Bug Assessment: «¡Tu primer cliente activo!» llega con `can_serve: true` sin ningún canal

- **Slug**: activado-no-significa-que-atienda
- **Created**: 2026-09-23
- **Source**: auditoría de la consola, evidencia viva del 2026-09-22 (KB `nexus/INFORME-AUDITORIA-CONSOLA-2026-09-22.md`, fila «Notificación»); heredado de D8 en `PLAN-ACCION-E2E-2026-08-30.md`
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim)

> Llega `client.activated` con `{"can_serve": true}` mientras la salud dice «Falta
> WhatsApp» (D8 del 1-sep, sigue).

`console_notifications`: `kind=client.activated`, `payload={"first": true,
"can_serve": true, "external_client_ref": "panaderia-la-espiga"}`, severidad
`info`. Texto en la consola: «¡Tu primer cliente activo! Cliente
panaderia-la-espiga activado con agente publicado». La ficha del mismo cliente:
«Falta: WhatsApp conectado».

## Symptom

El primer aviso que recibe un partner celebra un cliente que no puede atender a
nadie: tiene agente y cuota, pero ningún canal. D8 ya corrigió el caso «sin cuota»
(`can_serve` mira `allow_channel_turn`), pero no el caso «sin canal».

## Reproduction

1. Crear un cliente con el wizard dejando marcado «Publicar la versión 1 y activar».
2. No conectar WhatsApp.
3. `/notifications`: aviso `info` «¡Tu primer cliente activo!…». En BD `can_serve: true`.

## Suspected Code Paths

- `apps/api/src/nexus_api/services/console_notifications.py:186-221` —
  `_client_can_serve` solo consulta `allow_channel_turn(tenant_id)` (cuota).
- `apps/api/src/nexus_api/api/console/deps.py:141-167` — la salud del cliente sí
  exige canal WhatsApp activo; las dos definiciones de «puede atender» divergen.
- `apps/console/src/components/notifications/render.ts:22-25` — el único copy de
  «no puede atender» habla de cuota.

## Root Cause Hypothesis

D8 definió «atiende» como «la puerta del libro está abierta» porque el incidente
del 31-ago fue de cuota. La otra condición necesaria —que exista un canal por el
que llegue el mensaje— quedó fuera.

## Proposed Remediation

`_client_can_serve` devuelve `(can_serve, missing)` con `missing ⊆ {"quota",
"whatsapp"}`: cuota por `allow_channel_turn`, canal por «existe un `Channel` activo
de clientes» (el del Playground no cuenta, `services/console_traffic`). El payload
lleva `missing` y la consola nombra lo que falta: «falta conectar WhatsApp», «sin
cuota», o las dos. Severidad `warning` en cualquiera de los dos casos, como ya
hacía D8.

## Files likely to change

- `apps/api/src/nexus_api/services/console_notifications.py`
- `apps/api/tests/unit/test_endpoint_console_onboarding.py`
- `apps/console/src/components/notifications/render.ts`, `__tests__/render.test.ts`
- `apps/console/src/i18n/lanes/onboarding.ts`

## Tests to add or update

- API: tres clientes activados (sin canal · con WhatsApp activo · solo canal de
  Playground) → `missing` contiene `whatsapp` en el primero y el tercero, no en el
  segundo; severidad `warning` en los tres porque ninguno tiene cuota.
- Consola: copy por `missing` (`whatsapp`, ambos, solo cuota) y compatibilidad
  con avisos antiguos sin `missing`.

## Risks & Considerations

- Solo afecta al texto y la severidad de un aviso; `partners.activated_at` y la
  métrica de tiempo al primer cliente activo no cambian.
- El canal se lee con una sesión con ámbito de tenant (RLS) abierta a propósito
  dentro de la función; si falla, `can_serve=False` y `missing` completo (lado seguro).

## Open Questions

- Ninguna.
