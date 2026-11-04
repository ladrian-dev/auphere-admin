# Consumo y rebotes del correo (Origen de la spec 054)

Medido el 2026-11-03 hacia las 21:32 UTC, solo lectura: cuenta `793033583982`, `eu-south-2`, y la cuenta de Resend. Sin direcciones de correo a propósito: los registros de `email.sent` las llevan, y este documento no las necesita.

## La cuenta de Resend

| Dato | Valor |
|---|---|
| Hoy (se reinicia a las 00:00 UTC) | 45 de 100 |
| Ciclo (se reinicia el 2026-11-14 a las 15:19 UTC) | 899 de 3000 |
| Ritmo máximo | 10 peticiones por segundo, compartidas por toda la cuenta |
| Webhooks | 0 |
| Supresiones | 1, de origen `bounce`, creada el 2026-10-31 a las 19:06 UTC |
| Dominios | 1 de 3, `auphere.com`, verificado, en `eu-west-1`, con seguimiento de aperturas y clics apagado |
| Claves | 3: `Auphere Prod`, `Onboarding` y `amacrux-event`. Ninguna se llama como staging. No se ha comprobado cuál usa cada entorno |

Últimos 30 días según Resend: 1173 enviados, 1159 entregados, 14 rebotes (1 permanente, 13 transitorios), 0 quejas, 0 suprimidos, 0 fallidos, 67 retrasos. Tasa de rebote: 1,19 %. El máximo de un día fue 56, el 29 de octubre.

## Consumo por entorno y tipo, 30 días

Los registros cuentan **mensajes**. El contador de Resend cuenta **destinatarios**: un mensaje a tres personas gasta tres. Lo dice su documentación y se comprobó con el día de hoy.

```
filter event = "email.sent"
| stats count(*) as n, sum(ispresent(`to.1`)) as con2, sum(ispresent(`to.2`)) as con3 by subject, @log
| sort n desc
```

### Producción: 873 mensajes

| Tipo | Mensajes | Grupo | Después de fusionar |
|---|---:|---|---|
| Aviso de la DLQ | 720 | `scheduler` | Desaparece: la 051 lo pasa a una alarma |
| `client.out_of_quota` | 139, y 73 destinatarios más | `scheduler`, `runner` | Cae a uno por episodio, con la rama del aviso de saldo |
| Prompt cache degradado | 5 | `scheduler` | Desaparece: la 051 lo pasa a una alarma |
| Acceso a la consola e invitaciones | 5 | `api` | Se queda |
| Conversación que espera | 2 | `runner` | Se queda |
| Recibos | 2 | `scheduler` | Se queda |

Hay 864 de 873 que dejan de salir o bajan mucho, y **9 mensajes de negocio real en 30 días**. Producción aún corre el código de `main`, cuyos registros no llevan `kind`, así que se clasifica por asunto.

### Staging: 197 mensajes

| Tipo | Mensajes | Cuándo |
|---|---:|---|
| Automáticos anteriores a la 051: saldo agotado, `client.out_of_quota`, `wallet.empty`, avisos y cobro | 149 | hasta el 2026-10-30 |
| Alertas internas de servicio sin latido | 37 | hasta el 2026-10-30 |
| Correos de acceso | 11 | todo el periodo |

Desde el 2026-10-31, con la 051 desplegada, salieron **8 mensajes y todos son de acceso** (2 el 31 de octubre, 6 hoy). Además, 38 correos quedaron retenidos como `email.suppressed`.

### El contador de hoy, desglosado

| Qué | Destinatarios |
|---|---:|
| Aviso de la DLQ (22 mensajes, producción) | 22 |
| `client.out_of_quota` (9 mensajes, producción) | 16 |
| Acceso (7 mensajes, staging, uno de ellos por script) | 7 |
| **Total, igual al contador de Resend** | **45** |

El informe de 30 días de Resend (1173) y la suma de registros (1070) no cuadran del todo. La mayor parte de la diferencia cuadra con los mensajes a dos destinatarios de staging antes de la 051 (hasta +4 al día), y con envíos por script, cuyo grupo de registros no se consultó. No se concilió mensaje a mensaje.

## Previsión

Sin el aviso de la DLQ, con `client.out_of_quota` una vez por episodio y staging solo en acceso: **menos de 10 destinatarios al día** con el tráfico actual, contra un límite de 100. Es una previsión, y CE-009 la comprueba tras la fusión. El ciclo actual va camino de unos 1350 de 3000.

## Los 14 rebotes

```
filter event = "email.sent" and (`to.0` like /\.test$/ or `to.1` like /\.test$/)
| stats count(*) as n, min(@timestamp) as primero, max(@timestamp) as ultimo by subject
```

| Rebotes | Tipo | Origen | Qué es |
|---:|---|---|---|
| 12 | transitorios | staging, del 21 al 30 de octubre | Correos automáticos a una dirección de pruebas con dominio `.test`. La consulta dio 12 envíos en esas fechas, los mismos 12 rebotes transitorios de Resend. Los dos del 29 y 30 de octubre se vieron en el listado de Resend; el resto se deduce de que coinciden |
| 1 | permanente | staging, 31 de octubre, 19:06 UTC | Invitación de cliente a una dirección con una letra de menos. Se repitió a la dirección correcta a las 19:08. Es la única supresión de la cuenta |
| 1 | transitorio | **producción**, 31 de octubre, 23:42 UTC | El recibo de octubre de un partner. Nadie lo sabe hoy |

En producción, la misma consulta dio 0 envíos a `.test`.

## Nada lee los fallos

- `email.send_failed`, `email.send_error`, `email.variables_mismatch`, `email.not_configured`, `console_notifications.email_failed` y `console_notifications.client_email_failed`: **0 eventos en 60 días**, en los dos entornos, sobre 4,6 millones de registros. Staging solo guarda 30 días.
- `aws logs describe-metric-filters`: ningún filtro de métrica menciona `email`.
- `email.sent` aparece en `api`, `scheduler` y `runner`. `email.suppressed`, en `metering`, `scheduler` y `runner`. `email.delivery_mode`, en los cinco servicios, `egress` incluido.

## El canal de aviso

| | Producción | Staging |
|---|---|---|
| Suscripciones del topic | 1, por correo | 0 |
| Alarmas de la 051 | no aplicadas | existen con `ActionsEnabled = false`; `platform-alert-dlq-entries` está en ALARM |

## DNS de `auphere.com`, con `dig` contra `1.1.1.1`

| Registro | Valor |
|---|---|
| `_dmarc.auphere.com` | **NXDOMAIN** |
| `auphere.com` TXT | `v=spf1 include:spf.dondominio.com include:_spf.google.com ~all` |
| `send.auphere.com` TXT | `v=spf1 include:amazonses.com ~all` |
| `resend._domainkey.auphere.com` | presente |
| `google._domainkey.auphere.com` | presente |
| `auphere.com` MX | Google Workspace |
| Servidores de nombres | Cloudflare |

No se ha mirado la cabecera `Authentication-Results` de un correo real. Con estos registros, DKIM y SPF deberían alinear en modo relajado con `From: …@auphere.com`, y el `p=none` de la condición C1 no cambia nada mientras se comprueba.
