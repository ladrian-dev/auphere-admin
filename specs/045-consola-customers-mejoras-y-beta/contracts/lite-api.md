# Contrato 045: cambios en `/console/lite/*`

**Estado: congelado el 2026-10-22.** Lo consumen la consola web (esta spec) y la
app Auphere Customers (spec 044). Un cambio después de esta fecha se escribe
aquí, con fecha, y se avisa a la sesión de la app.

Todo lo de [`specs/030-consola-lite-del-cliente/contracts/lite-api.md`](../../030-consola-lite-del-cliente/contracts/lite-api.md)
sigue en pie. Aquí solo va lo que **cambia o se añade**. Autenticación, códigos
(401/403/404 opacos) y la regla «ninguna ruta acepta `ref`, `tenant_id`,
`partner_id` ni `customer_id`» no cambian. Los campos nuevos son **aditivos**: un
cliente que no los lea no se rompe.

Tipos: fechas-hora en ISO 8601 con zona (`2026-10-22T14:05:00Z`); fechas locales
del negocio en `YYYY-MM-DD`; horas locales en `HH:MM`.

---

## 1. Regla de la Bandeja (comportamiento, sin cambio de forma)

Aplica a **todas** las rutas `/console/lite/inbox/*`, a `/console/lite/home`
(`waiting`) y a la insignia del push.

- Una conversación **existe para la Bandeja** si tiene al menos un mensaje del
  contacto que el agente pudo atender: un entrante que la puerta de números
  permitidos (spec 024) no silenció, en un número con agente. Si no, la lista no
  la trae, los contadores no la cuentan y
  `GET /inbox/conversations/{id}` (y toda ruta con su id) responde **404**, igual
  que para una conversación de otro cliente.
- El hilo (`/messages`) empieza en el primer mensaje atendido y **no incluye**
  entrantes silenciados.
- `unread` compara la lectura de la persona con el último entrante atendido.
- `last_message` de la fila es el último mensaje que el hilo enseña.

## 2. Bandeja: motivo y espera

### `GET /console/lite/inbox/conversations` — cada `items[]` gana `waiting`

```json
{
  "id": "…",
  "state": "waiting",
  "waiting": {
    "reason": "Pide que le devuelvan la seña del pedido #4821. Los reembolsos los aprueba tu equipo.",
    "since": "2026-10-22T13:51:10Z"
  },
  "…": "el resto, igual que en la 030"
}
```

- `waiting` es `null` salvo con `state = "waiting"`.
- `reason` es el motivo del último escalado del agente; `null` si el escalado no
  dejó motivo. Puede ser largo: la pantalla decide cuántas líneas enseña.
- `since` es el momento del último escalado.

### `GET /console/lite/inbox/conversations/{id}` — gana `waiting_since`

```json
{ "state": "waiting", "waiting_reason": "…", "waiting_since": "2026-10-22T13:51:10Z", "…": "…" }
```

`waiting_since` es `null` salvo con `state = "waiting"`.

### Filtros (sin cambio)

`filter = all | unread | waiting | resolved`. `all` excluye las resueltas, como
hasta ahora. No hay filtro por canal.

## 3. Saldo: «te alcanza hasta»

El objeto `balance` de `GET /console/lite/home` y de
`GET /console/lite/usage/summary` gana dos campos:

```json
{
  "assigned": true,
  "remaining_cents": 3013,
  "cap_cents": 5000,
  "days_left": 11.4,
  "month_days_left": 10,
  "runs_out_on": "2026-11-02"
}
```

| Campo | Significado |
|---|---|
| `month_days_left` | Días del mes que quedan, **hoy incluido**, en la zona horaria del negocio. Nunca `null` |
| `runs_out_on` | Fecha local en que se acaba el saldo al ritmo de los últimos 7 días: hoy + `floor(days_left)`. `null` si `days_left` es `null` (sin gasto) o `assigned` es `false`. Con el saldo agotado, hoy |

Frases que la pantalla compone (no las da la API): «Cubre {min(days_left,
month_days_left)} de {month_days_left} días del mes», «Te alcanza hasta el
{runs_out_on}».

## 4. El negocio: horario y zona

### `GET /console/lite/me` — gana `business`

```json
{
  "user": {"email": "…", "name": "…"},
  "client": {"name": "…", "modules": ["panel", "inbox", "usage"]},
  "nav": ["panel", "inbox", "usage"],
  "business": {
    "timezone": "America/Santiago",
    "hours": {
      "monday": [{"from": "09:00", "to": "19:00"}],
      "tuesday": [{"from": "09:00", "to": "19:00"}],
      "wednesday": [{"from": "09:00", "to": "19:00"}],
      "thursday": [{"from": "09:00", "to": "19:00"}],
      "friday": [{"from": "09:00", "to": "19:00"}],
      "saturday": [{"from": "09:00", "to": "14:00"}],
      "sunday": []
    },
    "hours_label": "Lunes a viernes 09:00–19:00, sábados 09:00–14:00"
  },
  "…": "balance_contact, agents, channels: igual que en la 030"
}
```

- `hours`: forma canónica (siete días, lista de tramos, lista vacía = cerrado), o
  `null` si el negocio no tiene horario.
- `hours_label`: la frase ya compuesta en el idioma de la persona, o `null`.
- Se edita en la web (spec 043, Ajustes de Reservas). La app solo lo lee.

## 5. Avisos del teléfono: silencio fuera de horario

### `GET|PUT /console/lite/phones/current/notices` (solo teléfono)

```json
{ "kinds": ["inbox.waiting", "inbox.message_for_you", "client.balance"], "quiet_outside_hours": true }
```

- `PUT` acepta `quiet_outside_hours` opcional; si no viene, no cambia.
- Por defecto `true` en todo teléfono, también en los que ya existen.
- Con `true`, fuera del horario del negocio **no sale el push** de los avisos no
  urgentes. **Urgente** = `inbox.waiting`. Sin horario configurado no se
  silencia nada.
- La entrega silenciada queda `skipped` con motivo `quiet_hours` (no se reintenta
  al abrir el horario: es un aviso, no una cola).

Los tipos de Reservas se añaden en la spec 043 (ver su contrato).

## 6. Lo que NO cambia (para que nadie lo busque)

- No hay `channel` en los filtros ni pestañas por canal.
- No hay compra de saldo ni alertas de consumo en `/console/lite/*`.
- No hay papel de la persona en `/me`.
