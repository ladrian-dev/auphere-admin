# Envío directo por API: clientes de solo envío, códigos y membresía

**Spec**: `specs/077-otp-con-membresia/` · **KB**: `[[clients/tecfin]]`

Algunos clientes no tienen agente: su propio sistema llama a Auphere para mandar
plantillas de WhatsApp. New Air manda recordatorios; Tecfin manda **códigos de un
solo uso**. Este documento describe lo que existe para ellos.

## El alta, desde el panel

1. **Admin → Clientes → Nuevo cliente → «Solo envío por API».** El cliente nace
   con `tenants.send_only = true` y sin agente. «Con agente» sigue como siempre.
   - Partner opcional: con partner, va a su recibo; sin él, es cliente directo.
   - Membresía opcional (abajo).
2. **Su número.** En Canales, «Enviar enlace para conectar»: el enlace de la spec
   040 (siete días, un solo uso). El cliente entra con **su** cuenta de Meta, así
   que sus mensajes los paga él en su cuenta de WhatsApp Business.
3. **La plantilla de código.** Ficha del número → Plantillas → «Nueva plantilla»,
   categoría Autenticación. Meta fija el texto; solo se eligen el texto del
   botón de copiar código, la caducidad (1–90 min) y el aviso de seguridad.
4. **La clave.** Pestaña «Envío por API» → «Crear clave». Se ve completa una sola
   vez. Rotar y revocar piden confirmación y quedan en Auditoría. La consola de
   partners no las lista ni las toca: solo el operador las gestiona, para que
   ningún miembro de un partner pueda sacar el secreto de una clave de envío.

El Resumen del cliente enseña la **puesta en marcha** con esos pasos y su estado
real (`GET /admin/tenants/{id}/send-readiness`).

## Lo que cambia la marca «solo envío»

- El panel oculta Agente, Habilidades, Playground y Canal del dueño, y enseña
  «Envío por API».
- **Todo número de WhatsApp del cliente es de solo envío.** Al conectarse, por
  cualquier camino (`nexus_channels/whatsapp_meta/signup.py::_upsert_channel`),
  queda con `agent_enabled=false` y, si no tenía papel, `role=notifications`. Y la
  puerta del entrante (`runtime/dispatcher.py`) lo trata como solo envío aunque
  alguien lo cambie: una respuesta a un código se guarda y no espera a nadie.
- Marcar un cliente existente (`PATCH /admin/tenants/{id}/send-only`) aplica lo
  mismo a sus números. Un cliente sin la marca (New Air hasta que alguien la
  ponga) se ve y se comporta como antes.

## La API que usa el cliente

`POST https://api.auphere.com/v1/messages/template` con
`Authorization: Bearer ak_live_…` (una clave ligada al cliente, permiso
`messages_send`).

```json
{ "to": "+56912345678", "template_name": "tecfin_codigo", "language": "es",
  "code": "482913", "idempotency_key": "login-7f3a" }
```

- **`code`** solo vale con una plantilla `AUTHENTICATION`, y es lo único que esa
  plantilla admite: 1–15 caracteres ASCII imprimibles, sin espacios ni enlaces.
  El código va en el cuerpo (`{{1}}`) y en el botón de copiar código (Meta lo
  exige dos veces).
- Con una plantilla de variables con nombre (`variables`), todo es como antes.
- `/v1` está congelada (`tests/unit/v1_contract.json`). `code` entró en el
  contrato a propósito: es opcional, así que ninguna integración de hoy cambia.
- Respuestas: `202` en cola; `402 membership_inactive`; `422 code_required`,
  `code_not_allowed`, `invalid_code`, `variables_not_allowed`; `409 opted_out` si
  la persona se dio de baja de todo (una baja solo de marketing no frena un código).
- `GET /v1/messages/{id}` da el estado de entrega.

**El código no se guarda ni se registra.** Ningún log lo lleva, y el despachador
lo borra de la fila en cuanto el envío termina, enviado o fallido
(`tests/isolation/test_78_otp_code_never_logged.py`). Un código que lleva más de
**10 minutos** en cola (tras una caída del worker, por ejemplo) no sale: se marca
fallido con `code_expired` y se borra. También en un cliente pausado o suspendido, al que el
despachador no visita: su barrido de cada 30 segundos los busca y los borra.

Las difusiones no admiten plantillas de autenticación.

## La membresía

Opcional por cliente (`service_memberships`, FORCE RLS por `tenant_id`). Si un
cliente la tiene y **no está activa, no sale nada**:

- la API responde `402 membership_inactive` a sus envíos directos y a sus
  difusiones, sin encolar;
- el despachador marca **fallidas** (`failure_code = membership_inactive`) las
  plantillas que estuvieran en cola: no se retienen, para que un código viejo no
  salga al reactivarla;
- las respuestas de un agente no pasan por aquí.

La puerta (`services/membership_gate.py`) solo lee lo guardado: no llama a
Stripe ni importa `nexus_api.billing`.

Quién la paga:

| | El cliente, con tarjeta | Del saldo del partner |
|---|---|---|
| Cómo se cobra | Suscripción mensual de Stripe, con un cliente de Stripe propio del tenant | Un **cargo fijo mensual** en el libro del partner (`kind = fixed_fee`) |
| Cómo empieza | Enlace de pago desde Facturación (caduca a las 24 h; crear otro caduca el anterior, y si el anterior ya se pagó sin aviso, se aplica ese pago y no se abre otro) | Se cobra al activarla |
| Cuándo corta | Al primer cobro fallido (Stripe la pasa a `past_due`) o al cancelarse | Si al renovar el saldo, con la línea de crédito, no alcanza |
| Cómo vuelve | Pagando su factura pendiente (el enlace del panel es esa factura: nunca se abre una segunda suscripción) o, si se canceló, por un enlace nuevo | Sola, en cuanto hay saldo (el cron reintenta cada 5 min), o «Cobrar ahora» |

- **Stripe:** el estado sale siempre de la suscripción leída en Stripe, no del
  tipo de aviso. Un aviso solo cambia la membresía cuyo cliente de Stripe es el
  del tenant. Los avisos de membresía no traen `partner_id`, así que el camino de
  los partners no cambia. Como el webhook no reintenta, «Actualizar» en el panel
  y `service-memberships-cron` releen Stripe (como mucho una vez por hora).
- **Saldo del partner:** se intenta renovar una hora antes de vencer; si no hay
  saldo, sigue activa hasta el fin del periodo pagado. El periodo que toca se
  guarda antes de cobrar, con la fila bloqueada (dos cobros a la vez comparten la
  clave). La clave
  del cargo (`fee:membership:{tenant}:{inicio}`) es única, así que nunca se cobra
  dos veces aunque el proceso se repita. Ver `docs/billing.md`.
- Cancelar corta en el acto. Quitar la membresía la **archiva** (nunca la borra),
  y solo si no está activa.
- Un enlace de pago abierto se caduca en Stripe **antes** de cambiar el importe
  o quién paga, de archivar o de cancelar. Si Stripe no responde, no se guarda
  nada (503): un enlace viejo nunca queda pagable.

## Los cobros y los últimos envíos

- Facturación → Membresía → Cobros: las facturas de Stripe (con su enlace) o los
  cargos al saldo del partner.
- «Envío por API» → Últimos envíos: las 50 últimas plantillas, con el
  destinatario enmascarado y nunca el código.

## El script de alta a mano

`apps/api/scripts/seed_tenant_direct.py` ya no es el camino de alta: lo es el
panel. El script crea un número de relleno que, al conectar el real, deja dos
números activos.

## De qué partner cuelgan las claves

Las claves de un cliente cuelgan de su partner y, si no tiene, del partner
contenedor `auphere-direct`, el mismo de New Air. Si el cliente cambia de
partner, su clave pasa al nuevo la próxima vez que se rote desde su ficha.
Todos los clientes directos comparten, por tanto, el límite de la superficie de
envío de `auphere-direct` (600 llamadas por minuto por partner), y suspender ese
partner corta a todos. Si un cliente directo necesita su propio límite, se le
da un partner propio.

## Lo que hay que comprobar en producción

- La cuenta de Stripe es la que ya usa la consola. Su webhook de producción debe
  recibir `checkout.session.completed`, `customer.subscription.updated`,
  `customer.subscription.deleted`, `invoice.paid` e `invoice.payment_failed`.
- Una plantilla de autenticación real en staging: la forma en que Meta la
  devuelve (cuerpo con `{{1}}` o sin texto, botón `OTP` o `URL`) está cubierta por
  pruebas, pero solo un envío real la confirma.
