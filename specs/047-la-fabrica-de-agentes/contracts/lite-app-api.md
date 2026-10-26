# Contrato — consola lite y app Auphere Customers (`/console/lite/*`)

La consola lite web y la app son dos caras de las mismas rutas `/console/lite/*`
(ADR-042). `/app/*` sigue siendo solo lo del teléfono: sesión del dispositivo y
registro de push. Superficie `0`, con la misma puerta de hoy: `lite_scope` ata
cada petición a un solo cliente.

Reglas que no cambian:
- **Sin papeles** (owner): toda persona del cliente puede hacer todo lo de este
  contrato. La auditoría guarda su nombre y el origen (`lite_web` o `app`).
- **Fuera de su alcance**: crear, archivar o publicar agentes; instrucciones;
  calidad; conectar canales o integraciones; la bolsa. No hay ruta para eso
  (requisito 50.3).
- **Sin «Pedir saldo»** (specs 031 R4.4 y 044 R13.4).
- **Escrituras solo con conexión**: la app no encola nada (requisito 50.5).
- **Cada escritura** lleva `If-Match` (`412` con los cambios) e `Idempotency-Key`.

## 1. Agentes

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /console/lite/agents` | Agentes del cliente: nombre, `visible_state` (los mismos códigos, textos y tonos que la consola de partners), canales con su estado y `allowed` | 50.1 |
| `POST /console/lite/agents/{agent_id}/pause` · `/resume` | Pausar o reanudar; responde con las conversaciones en curso si las hay | 27.6, 50.2 |
| `POST /console/lite/channels/{channel_id}/pause` · `/resume` | Ídem, por número | 27.6 |

## 2. Negocio

Lo mismo que la consola de partners (`console-api.md` §3), restringido a:

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /console/lite/business` | Horario (con turnos y fechas especiales), servicios (precio y duración) y sedes, con su procedencia | 50.1 |
| `PUT /console/lite/business/hours?location_id=` | Horario; devuelve la frase «Así lo dirá el agente» | 10, 50.4 |
| `POST /console/lite/business/special-dates` · `PATCH /…/{id}` · `POST /…/{id}/archive` | Fechas especiales | 10.3 |
| `PATCH /console/lite/business/services/{id}` | Precio, duración, descripción y si es reservable | 11, 50.1 |
| `POST /console/lite/business/services` · `POST /…/services/{id}/archive` | Alta y archivo de servicios | 11 |
| `POST /console/lite/business/locations` · `PATCH /…/{id}` · `POST /…/{id}/archive` · `/restore` | Sedes | 9 |
| `POST /console/lite/business/history/{change_id}/undo` | Deshacer su último cambio | 13.3 |

Cada escritura avisa al partner (`client.business_changed`) y vuelve a pasar en
segundo plano las pruebas afectadas (requisito 13.7). El agente usa el dato nuevo
desde el siguiente mensaje (requisito 8.4).

## 3. Bandeja

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /console/lite/inbox` · `GET /console/lite/inbox/{conversation_id}` (existen) | Ganan `handled_by_agent` («La atiende {agente}») y `waiting_reason` (código de `events.md` §2) | 50.7, 53.2 |
| `POST /console/lite/inbox/{conversation_id}/messages/{message_id}/corrections` | `{text, scope: business \| agent}` → borrador de corrección: `kind` (dato o comportamiento), paráfrasis propuesta y `pii` (lo que hay que quitar) | 52.1, 52.2, 52.5 |
| `PATCH /console/lite/corrections/{id}` | Editar la lección o la paráfrasis | 52.4 |
| `POST /console/lite/corrections/{id}/send` | Un dato se aplica al momento (ficha o conocimiento); un comportamiento llega al partner como propuesta. Rechaza con `pii_present` si quedan datos de un cliente final en algo que va a la capa del negocio | 52.2, 52.5 |

## 4. Consumo

`GET /console/lite/usage` (existe) lee la bolsa del libro: la misma cifra que la
consola de partners (requisito 46.7). Gana:
- `bag_state` (`ok`, `low`, `not_enough`, `empty`);
- `days_left`;
- `partner_name`, para el texto «Pídeselo a {partner}».

## 5. Avisos y push

Los tipos de `events.md` §3.1. El registro de push no cambia (`/app/*`). Cada
aviso lleva su ruta interna de la app, por ejemplo `agents/{agent_id}` o
`inbox/{conversation_id}`.

## 6. Códigos de error

Los de `console-api.md` §9 que aplican (`revision_conflict`, `undo_window_closed`),
más:

| Código | HTTP | Cuándo |
|---|---|---|
| `pii_present` | 422 | Una corrección para la capa del negocio lleva datos de un cliente final |
| `client_archived` | 403 | El cliente está archivado: la consola lite y la app quedan cerradas (requisito 6.4) |
