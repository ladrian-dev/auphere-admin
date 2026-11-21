# Research: Lo que te necesita (API y worker)

Notas del 2026-11-21 sobre lo que el contrato no dice y el código obligó a decidir.

## R1 · Dónde vive la regla

`services/attention.py` sigue siendo puro (hechos → motivos, gravedad, arreglos, orden). La lectura con base va en `services/attention_live.py`: `client_overview` importa la regla, y la lectura importa `client_overview`. Una sola función de lectura, `live_attention()`, sirve al Panel, a `GET /console/attention` y a `resolve_cleared`.

## R2 · Qué es «la cuenta» en dinero

La misma cifra que «Saldo disponible» del Panel: lo asignable (`bags.assignable`: lo comprado más lo que queda de la línea de crédito, nunca el pool incluido). «Lo cargado en el mes» se calcula como las bolsas (D27): lo disponible más lo que salió de la cuenta este mes (débitos, asignaciones a bolsas y caducidades, menos lo devuelto). El ritmo es lo que salió en los últimos 7 días completos; con menos de 3 días con salida no se estima, como las bolsas.

## R3 · La cuenta, superconjunto del aviso

`wallet_alerts.evaluate_partner_wallet_alerts` (cada 15 minutos) avisa con una clave por umbral y mes, y su único freno es esa clave. Si la regla dijera «ya no está baja» mientras el emisor dice que sí, soltar la clave haría volver el aviso en el siguiente tick, sin fin. Sus bases difieren (el emisor mira lo comprado sin la línea de crédito y solo los débitos de turno; la regla, lo asignable y todas las salidas), así que la regla incluye también **el porcentaje del emisor, calculado con sus mismas funciones** (`read_wallet`, `purchased_spent_since`, `_percent_used`): al 80 % es baja, al 100 % vacía. Consecuencia: un partner postpago que ha gastado lo comprado y vive de la línea sale como «sin saldo», igual que ya le dice hoy `wallet.empty`.

## R4 · «Bajo» cubierto por «agotado»

La regla dice una sola vez lo peor (una bolsa vacía no es además «baja»). Pero `wallet.low` lo crea el emisor también cuando la cuenta está vacía, y `client.wallet.low`/`build.budget.warning` dicen algo que sigue siendo cierto al agotarse. Un aviso de `account_low`, `low_balance` o `build_cap_warning` no se resuelve mientras su hermano `account_empty`, `no_balance` o `build_cap_exhausted` siga en la lista.

## R5 · «Cobro fallido»

El aviso `billing.payment_failed` sale cuando la suscripción (`partner_subscriptions.state`) pasa a `payment_failed` (`billing/ladder.py`). La fila `billing_payment_failed` está en la lista mientras el estado sea `payment_failed` o `unpaid`: el segundo escalón es el mismo cobro sin pagar, y quitar la fila ahí diría que se arregló. Al volver a `current` se resuelve y la clave `billing:<partner>:payment_failed` se suelta, así que un fallo posterior vuelve a avisar.

## R6 · Solo la consola nueva

La campana de la consola de antes no tiene «Ahora». Si `unread-count` dejara de contar allí los avisos de condición, el partner los perdería de vista. `condition`, `unread-count`, `read-all` y `resolve_cleared` aplican a los partners con `console_v2_enabled_at`; los demás siguen como hoy. `GET /console/attention` responde a cualquiera (para los de antes no hay partida de construcción).

## R7 · La campana del cliente

`announce` deja también una copia `audience = client` de los avisos de bolsa, tope y canal. La consola lite no tiene «Ahora» y su comportamiento no cambia: `resolve_cleared` solo toca `audience = partner` y la lite sigue contando y marcando como hoy. Queda para otra spec que la lite lea la lista.

## R8 · `integration_reauth` también por el conector

La regla contaba solo `tenant_credentials.needs_reauth`, pero el aviso `integration.reauth_required` sale cuando Composio dice `EXPIRED` y solo cambia `tenant_connectors.status`. Con la regla así, el repaso resolvería el aviso con la integración caducada. Ahora cuenta las integraciones distintas con la credencial marcada **o** el conector en `needs_reauth`.

## R9 · Módulos y permisos

El contrato pide respetar los módulos sin enumerarlos. Lectura: las filas de cliente con `clients:read` y el módulo `clients` (como el Panel); la partida con `usage:read` y el módulo `usage` (su «Pedir ampliación» es `usage:read`); la cuenta con `usage:read` y el módulo `usage` o `billing` (es la cifra del Panel); el cobro con `billing:read` y el módulo `billing`. Sin el módulo del arreglo no hay fila (§V: la ausencia se diseña).

## R10 · Errores del Panel

`GET /console/attention` dice `errors: ["partner" | "clients"]`. En el Panel, que ya tenía `"attention"` para «no se pudo leer», `"attention"` sigue significando que la parte de clientes falló entera (la lista sale `null`, como hoy); una parte que falló sin tumbar la lista se dice como `"attention.partner"` o `"attention.clients"`. `all_serving` es lista vacía y sin errores.

## R11 · Lo que no se resuelve en el acto

- `alerts.rearm` es una función pura sin llamantes; el rearme real está en `bags._rearm`, dentro de `assign` y `move`, y se resuelve en sus endpoints tras confirmar.
- Comprar saldo para la cuenta, el escalón de cobro y los arreglos de canal que no vienen de un evento de cuenta (el cron de salud, el envío) los recoge el repaso de cada hora.
- Un canal con problemas de un cliente sin agentes no cuenta en la regla (sus canales cuelgan del agente principal, que no hay); ese cliente sale como `no_agents`. Es de antes de esta spec y no se cambia aquí.

## R12 · Leer antes de escribir

La primera versión de `resolve_cleared_detached` abría su transacción, miraba si el partner tenía la consola nueva y, con esa transacción abierta, leía la lista en otras sesiones. Un `TRUNCATE` del limpiado de los tests se coló en medio y las tres sesiones quedaron esperándose sin que Postgres lo viera como interbloqueo (la espera entre sesiones era del propio proceso). En producción pasaría igual con cualquier `LOCK` de una migración. Ahora todas las lecturas van en sesiones cortas **antes** de abrir la transacción que escribe, y `resolve_cleared(session, …)` pide que `session` no haya leído nada aún.
