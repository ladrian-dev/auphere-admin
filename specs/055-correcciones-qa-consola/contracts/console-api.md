# Contratos: API de la consola

Solo lo que cambia. Todo es aditivo: la app móvil instalada lee `ServicesOut.currency` como texto, así que sigue siéndolo.

## `PUT /console/clients/{ref}/business/basics`

Entrada nueva: `confirm_price_change: bool` (por defecto `false`).

| Caso | Respuesta |
|---|---|
| Cambia `price_currency`, hay servicios vivos con importe, sin confirmar | `409`, código `prices_would_change`, con `count` y `rounds` (si alguno se redondea). No escribe nada |
| Igual, con confirmación | `200`. Moneda y servicios cambian juntos |
| Sin servicios con importe | `200`, sin pedir confirmación |

Un cambio confirmado deja en la auditoría `business.price_currency_changed`, con `from`, `to` y `services`.

## `GET /console/clients/{ref}/business/services`

```text
ServicesOut.currency: string            # sin moneda elegida, XXX
ServicesOut.currency_set: boolean       # nuevo; falso si no hay moneda elegida
ServicesOut.exponent: int                # 2 si no hay moneda
ServiceOut.exponent: int                 # los decimales de la moneda de esa fila
ServiceOut.category: string | null
```

## `POST` y `PATCH /console/clients/{ref}/business/services[/{id}]`

Entrada nueva:

```text
category: string | null        # hasta 40; ausente en PATCH = no se toca
price_currency: string | null  # ^[A-Z]{3}$; solo se usa si el negocio no tiene moneda
```

| Caso | Respuesta |
|---|---|
| Importe, negocio sin moneda y sin `price_currency` | `422`, código `price_currency_required`, campo `price` |
| Importe y moneda conocida | La fila toma la moneda del negocio |
| `category` más larga de 40 | `422` |

## Lite: `/console/lite/reservas/services`

`ServiceIn` y `ServicePatchIn` ganan `category` y `price_currency`, con las mismas reglas. `ServiceOut` gana `category`. Los ajustes ganan `currency_set: bool`. `currency` sigue siendo texto.

## `POST /console/password-reset` y su equivalente de la app

**El contrato no cambia**: siempre `202` y el mismo cuerpo. Solo cambia qué pasa después:

| Dirección | Efecto |
|---|---|
| Con cuenta | Correo de restablecer |
| Sin cuenta, con invitación viva | La invitación, con un enlace nuevo. El anterior muere |
| Sin cuenta y sin invitación viva | Nada |
| Pasado el tope | Nada |

## Ficha portable (`ClientSpec`)

`Service` gana `category`, opcional. Una ficha sin ese campo sigue siendo válida.

## Lo que lee el agente

La línea de un servicio con categoría empieza por ella: `Corte · Básico · 30 min · 15,00 EUR · se reserva`. Sin categoría, la línea es la de hoy, byte a byte.
