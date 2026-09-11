# Idea Intake: membresías, consumo y cobro

- **Slug**: membresias-y-consumo-stripe
- **Created**: 2026-09-11
- **Source**: conversación con Luis al cerrar la evaluación de empaquetado ·
  punteros al repositorio: `db/models/partner_wallet.py`, `db/models/billing.py`,
  `metering/wallet.py`, `metering/quota.py`, `api/console/companion.py`,
  `api/console/teammates.py`, `apps/console/src/app/(console)/usage`,
  `apps/desktop/src/app/routes/account.tsx` · KB:
  [[teammates/08-coste-y-precio]], [[teammates/10-decisiones]] (decisión 14),
  [[nexus/PLAN-CONSOLE-V1]], [[nexus/PLAN-PENDIENTE-CORTE-2026-09-08]] (K1/K2/K3),
  [[nexus/decisions/ADR-022-stripe-integration-v1]]
- **Type**: new-capability (con mitad ya construida)
- **Superficie de confianza (§II)**: `0` — API de la consola. No se abre ninguna
  nueva; se cierra una puerta que hoy está abierta (`add_purchased` sin cobro).

## Idea (as captured)

> Una evaluación del flujo completo de facturación, membresías y consumo.
> Teammates es membresía + consumo; los clientes finales son solo consumo de los
> créditos del partner. La membresía más básica arranca en 20 USD/mes y trae un
> pool de consumo **semanal** que se reinicia solo; si se agota, se sigue
> consumiendo de los créditos comprados. Las membresías limitan el uso de la app.
> Consola, panel de admin y aplicación leen lo mismo. La landing no cuenta.

## Restated

El repositorio sabe **medir** y sabe **cortar**, y no sabe **cobrar**. El libro
del partner existe, es transaccional, es idempotente y está probado; la puerta
que lo recarga (`POST /console/wallet/purchased`) devuelve **404 opaco en
producción a propósito**, porque acreditarse saldo sin pago de por medio es
regalar producto. Todo el aparato está esperando a que alguien conecte el cobro.

Lo que la evaluación decide no es «si Stripe». Es cuatro cosas que arrastran:

1. **Qué es la membresía** y qué limita, frente a qué es consumo.
2. **Qué unidad mide el pool**, y cómo no se convierte en un segundo contador.
3. **Quién manda sobre el tope**: la plataforma o Stripe.
4. **Qué pasa cuando no se paga**, sin que nada desaparezca de la pantalla.

## Decisiones de producto que entran como dato, no como pregunta

| # | Decisión |
|---|---|
| P1 | **Dos cosas que conviven.** Teammates (app de escritorio) = membresía + consumo, máximo **3 membresías** por ahora. Clientes (agentes que el partner opera) = **solo consumo** de los créditos del partner, sin membresía |
| P2 | La membresía más básica y sencilla arranca en **20 USD/mes** |
| P3 | Cada membresía trae un **pool de consumo semanal** que se reinicia solo. Agotado, se sigue consumiendo de los **créditos** que el partner tenga |
| P4 | Las membresías limitan el uso de la app: número de teammates, número de personas colaborando, y lo que la investigación proponga |
| P5 | Consola, panel de admin y aplicación de escritorio **leen lo mismo** |
| P6 | **La landing no se tiene en cuenta.** Lo que se construya aquí es la fuente de la verdad; si la landing dice otra cosa, se corrige la landing |

P1 resuelve por decisión de producto la deuda **D5** de
[[nexus/PLAN-PENDIENTE-CORTE-2026-09-08]] («separar el bolsillo del Companion del
de los clientes»), que lleva abierta desde el 8 de septiembre. Conviene decirlo:
esto no añade trabajo, cierra el que ya estaba pendiente.

P3 reabre la decisión **5 del 2026-08-27** de [[teammates/10-decisiones]]
(«Precio: fuera de alcance. Esto es construcción»). Se reabre a propósito y con
la construcción hecha detrás, que es el orden correcto.

## Lo que hay hoy, verificado en el repositorio el 2026-09-11

| Pieza | Estado |
|---|---|
| `partner_wallets` (`included` + `purchased`) | **Construido y probado.** RLS FORCE por `partner_id` (0094). `included` caduca; `purchased` no |
| `usage_ledger` | **Construido.** Asiento por débito, `idempotency_key` UNIQUE, bucket `included`/`purchased` |
| `partner_allocations` | **Construido.** Tope por cliente dentro del wallet, con `OverAllocation` |
| `metering/quota.py` → `quota_tokens()` | **Construido.** La unidad única (C3): `uncached + 0,1 × cache_read + output` |
| Renovación del `included` | **Construida** (`wallet_renewal_cron`), y es **mensual**, con el cap sacado de `partners.companion_monthly_token_cap` |
| Columnas `stripe_*` | **Ausentes a propósito**, y lo sigue siendo hoy: el docstring de `billing.py` es cierto. Cero código de Stripe en todo el repositorio |
| `POST /console/wallet/purchased` | Construido y **cerrado en producción** (404 opaco). Abierto en staging. Su propio docstring dice que lo sustituye el webhook de K2 |
| `invoices` / `invoice_lines` / `billing_plans` | Construidos. El recibo mensual (`partner_receipt.py`) emite comisión / suscripción / inactivo. **Sin línea de membresía y sin línea de tokens** |
| Recibo por correo | **Construido** (`partner_receipt_email.py`), con nota de cambio CLP→USD |
| Avisos | **Construidos**: `usage_alerts` (avisa, no corta) y `wallet_alerts` (el saldo sí corta), con dedupe por umbral y mes |
| `model_profiles` | Construido. Anthropic con tarifa; **Sol, Terra y Luna a NULL** — y Sol es el modelo por defecto del Companion |
| `partner_model_allowlist` | **Construido** (0098). Lista de modelos por partner, con RLS. Es el mecanismo de «qué cerebro da cada plan», ya hecho |
| `partners.max_clients` | Construido (por defecto 5). **No existe tope de teammates ni de personas** |
| Consola `/usage` y `/billing` | Construidas. `/usage` pinta wallet, asignaciones y series; `/billing` pinta recibos |
| Admin `partners/[id]/{wallet,usage,limits,models,receipts}` | Construidas |
| Cuenta en la app | Construida. Pinta `budget` y el reparto por teammate, con la línea «gastado en otro sitio» |

## Preguntas que abre

1. El pool es **semanal** y el cobro **mensual**. ¿Cuándo empieza la semana de
   cada partner, y qué pasa con lo que no se gasta?
2. ¿Manda Stripe sobre el tope, o el tope sigue siendo de la plataforma y Stripe
   solo cobra?
3. ¿Sigue habiendo **un solo medidor** cuando el pool sea semanal? (Hoy ya hay
   dos cifras del mismo gasto que pueden discrepar: §1.3 de
   [`research.md`](./research.md).)
4. Impagos y degradación: ¿qué pasa con los teammates y con las tareas en marcha
   cuando una membresía caduca?
5. Prorrateo al subir o bajar de plan, y qué pasa con los créditos comprados.
6. ¿Qué ve el cliente final? (La respuesta esperada es «nada», y hay que
   probarlo, no afirmarlo.)
7. Impuestos: ADR-022 dejó Stripe Tax apagado para un canal de dos agencias.
   ¿Sigue valiendo eso para una membresía de 20 USD vendida a cualquiera?
8. ADR-022 está **aprobado** y describe un modelo (tier por número de clientes,
   un `Subscription Item` por cliente final, sin metered) que no es el de P1–P3.
   ¿Se enmienda, se supersede, o conviven?
