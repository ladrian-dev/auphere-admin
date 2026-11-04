# Especificación: Correo fiable

**Rama**: `054-correo-fiable` · **Creada**: 2026-11-03 · **Estado**: Borrador, pendiente de aprobación

**Entrada**: Luis autorizó el 2026-11-03 abrir esta spec: que un correo de la plataforma que falla o rebota no se pierda sin que nadie se entere. No lleva código de producto hasta que la apruebe.

La spec 051 arregló qué dice cada correo y a quién va. Esta mira si llega, y qué pasa cuando no.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la API y el panel de operador, que ya existen. Se añade una ruta pública para los eventos del proveedor, de la misma familia que las de Meta, TikTok y el cobro. No abre una superficie nueva, porque Resend ya es proveedor, pero es entrada externa no confiable: `/cso` es condición de salida (C7) |
| **Garantías de aislamiento tocadas** | **6**: cada envío y cada evento llevan el negocio al que pertenecen, y ese negocio sale del envío, nunca del evento. **1, rozada**: el registro de envíos es de plataforma, como los avisos de la consola, y el rol de tenant no lo lee. **8, rozada**: el nombre de un contacto final puede viajar en un correo en cola hasta que sale, y ni el panel ni los registros lo enseñan. Además, **una frontera que no está en esa lista, la de entorno**: con la cuenta compartida, el webhook de staging recibe eventos de producción y no puede guardarlos. Pruebas en el Requisito 9 |
| **Nota de KB que la justifica** | `[[research/2026-11-03-correo-fiable]]` · `[[research/2026-10-30-correos-con-oficio]]` |
| **Qué se mide** | Nada de modelo ni de reloj de máquina, y ningún correo gasta saldo de un partner. El plan de Resend, si se compra, es coste de plataforma. Lo que esta spec hace visible es el consumo de esa cuota (Requisito 8) |

## Origen

Medido el 2026-11-03 contra `develop` (`09d579ef`), la cuenta de Resend y CloudWatch. Las tablas completas y las consultas están en `evidence/consumo-y-rebotes.md`.

**Lo que hoy se pierde sin que nadie lo sepa:**

- **`send_template` hace un solo intento.** Un 429 o un 5xx de Resend, o un corte de red, y el correo no sale. Hasta ahora no ha pasado: 0 fallos en 60 días en los dos entornos. Pero ningún filtro de métrica mira `email.send_failed`, así que nadie se enteraría.
- **El aviso de consola y su correo no van juntos.** `emit` envía el correo dentro de la transacción del aviso. Si el correo falla, el aviso ya existe y su `dedupe_key` impide volver a emitirlo, así que ese correo no se reintenta nunca. Si la transacción se deshace, ha salido un correo de un aviso que no existe. Y un proveedor lento retiene una conexión y hasta 20 s de un turno del agente, que es por donde el `runner` emite.
- **Nada escucha lo que pasa después de que Resend acepta.** Hay 0 webhooks. `email.sent` significa «el proveedor lo aceptó», no «llegó».
- **Enviar a una dirección suprimida no se ve desde aquí.** Según su documentación, Resend salta ese destinatario y avisa con un evento que hoy nadie recibe. No documenta qué responde al envío, y se comprobará en staging. La lista de supresión vale para toda la cuenta, así que un rebote en staging también bloquea esa dirección en producción.

**Los 14 rebotes de 30 días** (de 1173 envíos, un 1,19 %):

| Rebotes | Tipo | Dónde | Qué es |
|---:|---|---|---|
| 12 | transitorios | staging, del 21 al 30 de octubre | Correos automáticos a una dirección de pruebas `.test`. Dejaron de salir con la 051 |
| 1 | permanente | staging, 31 de octubre | Invitación de cliente a una dirección con una letra de menos. Alguien lo vio a mano y repitió el envío dos minutos después. Es la única supresión de la cuenta |
| 1 | transitorio | **producción**, 31 de octubre | **El recibo de octubre de un partner. Nadie lo sabe hoy** |

**La cuota: 100 al día y 3000 al mes, compartidos por staging y producción.** A las 21:32 UTC el contador marcaba 45 y 899. Cuenta destinatarios, no mensajes: un mensaje a tres personas gasta tres.

| 30 días | Mensajes | Qué pasa con ellos |
|---|---:|---|
| Producción, aviso de la DLQ | 720 | Desaparecen al fusionar la 051 |
| Producción, `client.out_of_quota` | 139 | Caen a uno por episodio con la rama del aviso de saldo |
| Producción, prompt cache | 5 | Desaparecen al fusionar la 051 |
| **Producción, negocio real**: acceso 5, conversaciones 2, recibos 2 | **9** | Se quedan |
| Staging, antes de la 051 | 186 | Ya no salen |
| Staging, correos de acceso | 11 | Se quedan: 8 en los últimos 4 días, con un máximo de 6 en un día |

**Lo que eso quiere decir**: la cuota no está cerca de romperse, está llena de ruido. De los 45 de hoy, 22 son la DLQ y 16 `client.out_of_quota`. Con esas dos fusiones, el consumo baja a menos de 10 al día sin comprar nada. **Lo que obliga a decidir el plan no es el volumen: el plan gratis admite 1 solo webhook**, y hay dos entornos que quieren el suyo (D13).

**Cuantos menos correos, más fácil es incumplir la política de Resend.** Pide menos del 4 % de rebotes y menos del 0,08 % de quejas, y dice que puede cerrar la cuenta sin avisar. Con menos de 300 correos al mes, una sola queja ya supera ese 0,08 % (D11).

## Decisiones

**Decisiones de Luis que esta spec respeta**, del 2026-11-03:

- Nada en producción, ni Terraform, hasta fusionar `develop` en `main`.
- Staging sigue enviando solo los correos de acceso.
- El aviso de cliente sin saldo sale una sola vez, en una rama aparte.
- Fuera de alcance: marketing, y seguimiento de aperturas y clics.
- Staging no avisa a nadie: sus alarmas se miran en la consola de AWS. Es la R9.9 de la spec 051, y la rama `chore/observabilidad-sin-deriva` la recoge como decisión de Luis. La enmienda de la 051 que la contiene aún consta como pendiente de su OK, así que D11 lo señala.

**Todo lo que sigue es propuesta**: esta spec no le ha preguntado nada a Luis. Las preguntas que haría `/speckit-clarify` se resuelven aquí, y aprobar la spec es aprobarlas.

| # | Pregunta | Decisión propuesta | Por qué |
|---|---|---|---|
| D1 | ¿Cuántos reintentos en línea? | **3 intentos y 30 s en total**, contando las esperas, y respetando `retry-after`. Se reintenta ante un 429 de ritmo, un 5xx, un error de red o un plazo vencido. No se reintenta en línea ante otro 4xx ni ante un 429 de cuota | A veces hay una persona esperando. Hoy ya espera hasta 20 s en un solo intento. Un 429 de cuota no se arregla en 30 s |
| D2 | ¿Dónde viven los correos automáticos? | **En una cola durable.** Se guardan antes de llamar al proveedor y, si nacen dentro de una transacción, con ella. Quien los pide no espera al proveedor | Es lo único que arregla a la vez el aviso sin correo, el correo sin aviso, el turno del agente esperando a Resend y lo que se pierde al reiniciar un proceso |
| D3 | ¿Y los de acceso? | **En línea y sin guardar variables.** `team_invite`, `client_invite`, `signup_link` y `password_reset` llevan un enlace de un solo uso, y `signup_existing` tiene que comportarse igual que `signup_link`. `password_changed` sí va a la cola: no lleva enlace, nadie espera y nadie puede pedirlo otra vez | Guardar en claro el enlace de un solo uso lo convertiría en un secreto en reposo, cuando hoy solo existe su hash. Quien lo pidió puede pedir otro |
| D4 | ¿Qué pasa al agotar? | **Se deja de intentar, se borra lo guardado salvo los metadatos, queda como `fallido`, y salta la alarma y sale en el panel.** En un automático, 7 pasadas en 22 h 20 min, con tope a las 23 h. `inbox_waiting` y `conversation_escalated`, a las 4 h, porque más tarde mienten. No se reenvía solo | Un día después, un aviso ya es otra cosa. El aviso sigue en la consola, y un recibo se reenvía con la acción que ya tiene el panel |
| D5 | ¿Cómo se evita duplicar? | **Una clave de idempotencia por correo**, la misma en todos sus intentos, también tras un reinicio | Resend la guarda 24 h. Por eso el tope son 23 h: pasado el plazo, reintentar podría duplicar |
| D6 | ¿Qué eventos se escuchan? | Los dos pedidos (`email.bounced`, `email.complained`) y **tres más**: `email.suppressed`, `email.failed` y `email.delivered`. No `email.delivery_delayed`, `email.opened` ni `email.clicked` | Sin `suppressed`, enviar a la dirección suprimida de hoy se perdería en silencio. Sin `delivered`, un webhook muerto no se distingue de uno tranquilo. Los 67 retrasos de 30 días eran ruido, y aperturas y clics están fuera de alcance |
| D7 | ¿De quién es un evento? | **Del envío al que corresponde en el registro de este entorno.** Partner, cliente, tipo y entorno nunca se leen del evento | Es la regla del `tenant_id`, aplicada aquí. Una firma válida dice que lo manda Resend, no de quién es |
| D8 | ¿Y los eventos de otro entorno? | **No se guardan**, ni dirección ni asunto. Queda un contador sin datos | Con la cuenta compartida, el endpoint de staging recibe los rebotes de producción. Guardarlos sería copiar direcciones reales a staging |
| D9 | ¿Qué se guarda? | **Metadatos**: tipo, destinatarios, negocio, estado, fechas y motivo del rebote. No el asunto ni las variables, que solo viven en la cola hasta que el correo termina. **90 días**, como los registros de producción | El asunto puede llevar el nombre de un contacto final. Para saber qué falló no hace falta |
| D10 | ¿Dónde lo ve el operador? | **Panel → Estado, sección «Correo»**, de solo lectura. El partner no lo ve en esta spec | Estado ya es donde se mira lo que hay que mirar. Hay 1 rebote permanente en 30 días y el operador puede avisar al partner. Enseñárselo al partner es otra spec, junto a la pestaña Equipo de la 052 |
| D11 | ¿Qué alarmas? | **Tres, una más de las pedidas**: fallo de envío, cuota alta, y rebote permanente, queja o supresión. Solo en staging y **sin aviso** hasta fusionar, por R9.9. En producción avisan por el topic que ya existe, que no pasa por Resend | Un panel que nadie abre es el mismo silencio. La tercera apenas suena (1 rebote permanente y 0 quejas en 30 días) y una queja ya incumple la política de Resend. **Hasta fusionar, estas alarmas no le llegan a nadie**: si Luis quiere aviso antes, es un topic propio y una excepción escrita a R9.9, sin el ruido de `worker_dead` |
| D12 | ¿Cómo se protege un correo de acceso? | **Una reserva de 30 de los 100 diarios.** Con el contador en 70, los automáticos esperan al día siguiente y los de acceso siguen. En el mes, los automáticos paran en 2850 | Máximo de acceso medido: 6 al día, así que 30 sobran. Esperar a las 00:00 UTC no pierde nada, porque ya están en cola |
| D13 | ¿Hay que comprar? | **No por volumen. Al fusionar, sí hay que elegir (C5)**: Pro a 20 USD al mes, con 5 webhooks y sin límite diario, o mover el único webhook a producción y dejar staging sin eventos. Recomendación: comprar. **Si Luis compra antes de `/speckit-plan`, los criterios 8.3 a 8.5 se retiran** | Es una compra de Luis, así que la spec funciona sin ella. 20 USD al mes son menos que un correo de acceso perdido con un cliente delante |
| D14 | ¿Se separa por entorno? | **La clave, sí** (C3). **La cuenta y el dominio, no** | La clave cuesta cero y permite revocar sin tocar el otro entorno, pero no separa la cuota, que es por equipo. Otra cuenta obligaría a mantener dos veces 39 alias, y dos copias divergen; con menos de 10 correos al día no resuelve un problema que exista hoy |
| D15 | ¿Y las direcciones que no existen? | **No se llama al proveedor si el dominio es reservado** (`.test`, `.example`, `.invalid`, `.localhost`, `example.com`, `example.net` y `example.org`) | 12 de los 14 rebotes vinieron de ahí, y cuentan contra la tasa de toda la cuenta |
| D16 | ¿Qué DMARC? | **`p=none` con informes**, y endurecer solo con ellos a la vista (C1) | `p=none` no cambia ninguna entrega. La guía de Resend va de `none` a `quarantine` y a `reject` |

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Un tropiezo del proveedor no se nota y no duplica (Prioridad: P1)

Una persona pide restablecer su contraseña justo cuando Resend devuelve un 503. La plataforma lo reintenta unos segundos después, con la misma clave, y el correo llega una sola vez. Si la primera respuesta se perdió por un corte de red, el segundo intento recibe la misma respuesta y no sale un segundo correo.

**Por qué esta prioridad**: es el fallo más barato de evitar y el que afecta a quien está esperando.

**Prueba independiente**: con un proveedor simulado que falla dos veces y acepta a la tercera, el correo sale una vez y el registro cuenta los intentos. Con uno que acepta pero corta la conexión antes de responder, la clave es la misma en los dos intentos.

**Escenarios de aceptación**:

1. **Dado** un 503, **cuando** el reintento lo acepta, **entonces** queda un solo envío y `email.attempt_failed` del primer intento, y quien llamó recibe que salió.
2. **Dado** un 429 de ritmo con `retry-after: 2`, **cuando** se reintenta, **entonces** espera al menos 2 s.
3. **Dado** un 422 de validación, **cuando** responde, **entonces** no reintenta en línea, y queda `email.send_failed` con el estado y el nombre del error.
4. **Dado** un 429 de cuota, **cuando** responde, **entonces** no reintenta en línea.
5. **Dado** un proveedor que nunca responde, **cuando** pasan 30 s, **entonces** el envío termina y quien llamó recibe que no salió.

---

### Historia 2 — Un correo automático espera en vez de perderse (Prioridad: P1)

Resend cae de madrugada. La plataforma sigue generando avisos: un cliente sin saldo, un recibo, una conversación que espera. Esos correos quedan en cola, el agente sigue contestando sin esperar a nadie, y cuando Resend vuelve salen todos, en orden y sin duplicar, aunque algún proceso se haya reiniciado entremedias. Si Resend no vuelve en 23 horas, se dejan de intentar y alguien se entera de cuáles fueron.

**Por qué esta prioridad**: es el caso real de hoy. Un aviso creado cuyo correo falla no se vuelve a emitir.

**Prueba independiente**: con el proveedor simulado caído, emitir un aviso de consola, reiniciar el proceso y levantar el proveedor. El correo sale una sola vez. Repetir sin levantarlo: a las 23 horas simuladas queda como `fallido`, sin variables, y con `email.send_failed`.

**Escenarios de aceptación**:

1. **Dado** un aviso de consola con correo, **cuando** su transacción se confirma, **entonces** el correo queda en cola, y **cuando** se deshace, **entonces** no queda ni aviso ni correo.
2. **Dado** un proveedor que tarda 20 s, **cuando** el `runner` emite un aviso, **entonces** el turno no espera al proveedor.
3. **Dado** un correo en cola que falla, **cuando** toca su siguiente pasada, **entonces** se reintenta con la misma clave.
4. **Dado** que se agota la vigencia, **cuando** ocurre, **entonces** deja de intentarse, se borran sus variables y salta la alarma.
5. **Dado** un 401 o un 403 del proveedor, porque hay una clave o un dominio mal, **cuando** responde, **entonces** el correo sigue en cola hasta su vigencia y salta la alarma en la primera vez: arreglar la clave rescata lo pendiente.
6. **Dado** el panel, **cuando** un operador envía a mano un recibo que queda en cola, **entonces** se le dice que está en cola y saldrá en un minuto, no que se ha enviado.

---

### Historia 3 — Un rebote llega a quien puede resolverlo (Prioridad: P1)

El recibo de un partner rebota. Minutos después, en Panel → Estado, una operadora ve que el recibo de ese partner no llegó, a qué dirección iba, cuándo y qué dijo el servidor de destino. Lo mismo con una queja o con un envío que Resend descartó porque la dirección está suprimida. Si un día deja de llegar cualquier evento, la pantalla lo dice en vez de enseñar «sin problemas».

**Por qué esta prioridad**: el recibo de octubre de un partner rebotó el 31 de octubre y nadie lo sabe.

**Prueba independiente**: en staging, invitar a `bounced@resend.dev`, `complained@resend.dev` y `suppressed@resend.dev`. Cada caso aparece en el panel con su negocio. Una petición sin firma se rechaza y no deja nada. Un evento firmado de un correo que este entorno no envió no deja ninguna dirección.

**Escenarios de aceptación**:

1. **Dado** un rebote de un correo enviado por este entorno, **cuando** llega el evento, **entonces** queda asociado a ese envío, con su tipo y su negocio.
2. **Dado** un evento firmado cuyas etiquetas nombran a otro partner, **cuando** llega, **entonces** el negocio sigue siendo el del envío.
3. **Dado** un evento firmado que no corresponde a ningún envío de este entorno, **cuando** llega, **entonces** responde 200 y no guarda dirección ni asunto.
4. **Dado** una firma ausente, falsa o fuera de plazo, **cuando** llega la petición, **entonces** se rechaza sin leer el cuerpo.
5. **Dado** un evento repetido, **cuando** llega otra vez, **entonces** responde 200 y no cambia nada.
6. **Dado** un entorno sin secreto del webhook, **cuando** se abre el panel, **entonces** dice que los eventos no están conectados, y no «ningún problema».
7. **Dado** correos aceptados en las últimas 24 horas y ningún evento en ese tiempo, **cuando** se abre el panel, **entonces** dice desde cuándo no llegan eventos.

---

### Historia 4 — Alguien se entera sin tener que mirar (Prioridad: P1)

Un correo falla de forma definitiva, la cuota se acerca al límite, o llega una queja. Salta una alarma, una sola por avería. Hasta fusionar `develop` en `main` eso solo existe en staging y se mira en la consola de AWS. Al fusionar se aplica en producción, y ahí el aviso llega a un buzón por un canal que no depende de Resend.

**Por qué esta prioridad**: hoy nadie se enteraría de ninguno de los tres. Y el canal de aviso no puede ser el que está fallando.

**Prueba independiente**: en staging, provocar un fallo definitivo de envío y un rebote: las alarmas pasan a ALARM en menos de 15 minutos y sin notificar. En producción, al fusionar, forzar el estado de cada alarma y comprobar que el aviso llega al buzón.

**Escenarios de aceptación**:

1. **Dado** un fallo definitivo en cualquier servicio que puede enviar, **cuando** se registra, **entonces** la alarma de fallo de envío pasa a ALARM.
2. **Dado** un fallo que se repite durante horas, **cuando** sigue, **entonces** la alarma no vuelve a avisar hasta 3 horas después del último.
3. **Dado** staging, **cuando** salta cualquiera de las tres, **entonces** no se notifica a nadie.
4. **Dado** un rebote de un correo de otro entorno, **cuando** llega al webhook, **entonces** ninguna alarma de este entorno se mueve.

---

### Historia 5 — Un correo de acceso no se queda sin cuota por culpa de otra cosa (Prioridad: P2)

Un día de muchos avisos el contador llega a 70. Los automáticos paran y esperan a que el contador se reinicie a las 00:00 UTC. Un cliente real pide restablecer su contraseña a las 22:00 y el correo sale, porque aún quedan 30 reservados para esto.

**Por qué esta prioridad**: el riesgo es real pero no inminente. El máximo medido es 56 en un día, con el ruido incluido. Si Luis compra el plan antes de planificar, esta historia se retira (D13).

**Prueba independiente**: con un proveedor simulado que devuelve el contador en 70, un automático queda en cola y un `password_reset` sale. A las 00:00 UTC simuladas, el automático sale.

**Escenarios de aceptación**:

1. **Dado** un contador en 70 o más, **cuando** toca un automático, **entonces** espera a las 00:05 UTC.
2. **Dado** un contador en 70 o más, **cuando** se pide un correo de acceso, **entonces** sale.
3. **Dado** un plan sin límite diario, porque no llega ese contador, **cuando** se envía, **entonces** nada espera por este motivo.
4. **Dado** un 429 de cuota en un correo de acceso, **cuando** responde, **entonces** falla como cualquier fallo definitivo, y salta la alarma de cuota y la de fallo.

---

### Historia 6 — Lo que no es código queda dicho (Prioridad: P2)

Luis tiene una lista con el valor exacto de cada cosa que solo él puede configurar o comprar, y sabe cuáles bloquean qué. Ver §Condiciones de salida.

**Por qué esta prioridad**: sin DMARC y sin un `support@` que alguien lea, parte de lo anterior queda a medias. Pero nada de esta lista bloquea escribir el código.

**Prueba independiente**: cada condición dice cómo se comprueba.

---

### Casos límite

- **Un correo a varias personas y solo una rebota.** El evento nombra a los afectados. El panel enseña a esa persona, y el envío no se pinta como rebotado entero.
- **Un `delivered` que llega después de un `bounced`.** Un evento sano no borra un problema: los eventos pueden llegar desordenados.
- **El evento llega antes de que el envío guarde su identificador.** No se pierde: el envío existe antes de llamar al proveedor y se puede correlacionar por una referencia propia (9.2).
- **Staging está aparcado, de 03:00 a 09:00, hora de Madrid.** La ruta no responde y Resend reintenta: al momento, a los 5 s, 5 min, 30 min, 2 h, 5 h, 10 h y 10 h. Un evento de madrugada llega al despertar. Si el endpoint falla demasiado, Resend lo desactiva y avisa al equipo por correo, y el panel lo enseña como «sin eventos desde…».
- **El `scheduler` caído.** La cola no se vacía y su alarma no suena, porque la emite él mismo. Es el punto ciego que ya existe en la 051. Los correos esperan y salen al volver, dentro de su vigencia.
- **La cola atascada con el `scheduler` vivo.** Un `platform_alert` propio la delata (2.11).
- **Una persona deja de ser destinataria mientras su correo espera.** Los destinatarios se fijan al encolar. Se acepta: son 23 horas como mucho, solo con el proveedor caído, y no lleva nada de un solo uso.
- **Un aviso de saldo agotado que sale 20 horas tarde, con el saldo ya repuesto.** Se acepta: solo ocurre con el proveedor caído casi un día, y el correo ya invita a mirar la consola. Los dos que mienten antes tienen 4 horas de vigencia (D4).
- **Un automático que nace con la reserva ya gastada en la primera hora UTC.** Las 00:05 del día siguiente quedan fuera de sus 23 horas y caduca como `fallido`. Se acepta: exigiría gastar 70 destinatarios en una hora, y el máximo medido es 56 en un día.
- **Se reintenta un correo cuyas variables cambiaron.** No puede pasar: la cola guarda lo compuesto. Si ocurriera, el proveedor responde `invalid_idempotent_request` y queda como fallo definitivo con un error visible.
- **Los enlaces de restablecer no llegan y no hay pantalla que lo diga.** Como hoy: la respuesta no cambia, para no abrir un oráculo de cuentas (spec 011). El operador lo ve en el panel, y la persona puede pedirlo otra vez.
- **Una dirección suprimida por un error de staging.** Se levanta a mano en el panel de Resend. Esta spec no lo automatiza.
- **El contador leído tiene horas.** El proveedor solo lo dice al responder a un envío, y no documenta una forma de consultarlo. En staging, con pocos envíos, el panel y la alarma de cuota pueden ir por detrás de lo que consume producción. Por eso el panel dice cuándo se leyó.
- **Sin capacidad disponible (§V).** El panel no enseña un número de cuota que no se ha leído nunca, ni un «0 rebotes» sin eventos conectados.

## Requisitos *(obligatorio)*

### Requisito 1 — Reintentar sin duplicar

**Historia de usuario:** Como persona que espera un correo, quiero que un fallo pasajero del proveedor no me cueste ese correo, y como su destinataria, no recibirlo dos veces.

#### Criterios de aceptación

1. WHEN el proveedor responde un 429 de ritmo (`rate_limit_exceeded`) o un 5xx, o no responde por un error de red o un plazo vencido, THEN el sistema DEBE reintentar con espera creciente y aleatoria, hasta 3 intentos y 30 s en total, contando las esperas.
2. WHEN la respuesta trae `retry-after` THEN el sistema DEBE esperar al menos ese tiempo, e IF no cabe en lo que queda de los 30 s THEN DEBE terminar sin ese intento.
3. IF el proveedor responde un 429 de cuota (`daily_quota_exceeded` o `monthly_quota_exceeded`) THEN el sistema NO DEBE reintentar en línea.
4. IF el proveedor responde cualquier otro 4xx THEN el sistema NO DEBE reintentar en línea.
5. El sistema DEBE enviar cada correo con una clave de idempotencia que lo identifique a él y solo a él, por grupo de idioma, y DEBE usar la misma en todos sus intentos, también tras un reinicio del proceso.
6. IF el proveedor responde `concurrent_idempotent_requests` THEN el sistema DEBE tratarlo como reintentable, e IF responde `invalid_idempotent_request` THEN DEBE tratarlo como fallo definitivo.
7. WHEN falla un intento y quedan más THEN el sistema DEBE registrar `email.attempt_failed` a nivel de aviso, con tipo, plantilla, número de intento, estado y nombre del error. NO DEBE llevar variables ni enlaces.
8. El sistema DEBE reservar `email.send_failed` para cuando un correo no va a salir, o cuando el proveedor rechaza la configuración (2.6), con tipo, plantilla, estado, nombre del error y negocio.
9. El envío NO DEBE lanzar excepciones hacia quien lo pide, igual que hoy, y NO DEBE mantener abierta una transacción de base de datos mientras espera al proveedor.

### Requisito 2 — Los correos automáticos esperan en una cola

**Historia de usuario:** Como equipo de Auphere, quiero que un correo que nadie está esperando sobreviva a una caída del proveedor y a un reinicio, y saber cuáles no salieron al final.

#### Criterios de aceptación

1. El catálogo DEBE declarar por tipo si puede esperar en cola. NO DEBEN poder `team_invite`, `client_invite`, `signup_link`, `password_reset` ni `signup_existing`. DEBEN poder todos los demás, `password_changed` incluido.
2. WHEN se envía un tipo que puede esperar, en un modo que lo envía, THEN el sistema DEBE guardarlo en la cola con lo ya compuesto y DEBE volver sin esperar al proveedor.
3. WHEN ese correo nace dentro de una transacción THEN su entrada DEBE confirmarse o deshacerse con ella.
4. Un proceso de la plataforma DEBE revisar la cola al menos una vez por minuto y DEBE enviar por orden de antigüedad, a no más de 5 por segundo, porque el ritmo del proveedor lo comparte toda la cuenta.
5. WHEN falla una pasada, aplicado ya el Requisito 1, THEN el sistema DEBE programar la siguiente a los 5 min, 15 min, 1 h, 3 h, 6 h y 12 h.
6. IF el proveedor responde un 401 o un 403 THEN el sistema DEBE dejar el correo en cola según 2.5 y DEBE registrar `email.send_failed`, porque arreglar la clave o el dominio rescata lo pendiente.
7. IF el proveedor responde cualquier otro 4xx, salvo los de cuota, THEN el sistema DEBE dar el correo por `fallido`.
8. WHEN un correo llega a su vigencia sin salir THEN el sistema DEBE dejar de intentarlo, DEBE marcarlo `fallido` y DEBE registrar `email.send_failed` con el motivo. La vigencia es de 23 h desde su creación, y de 4 h para `inbox_waiting` y `conversation_escalated`.
9. WHEN un correo termina, salga o no, THEN el sistema DEBE borrar sus variables y conservar solo los metadatos del Requisito 5.
10. WHERE quien pide el envío informa a una persona del resultado, el sistema NO DEBE presentar «en cola» como «enviado».
11. WHEN la entrada más antigua lleva más de 30 min con su pasada vencida y sin intentarse THEN el sistema DEBE registrar un `platform_alert` de tipo `email_queue_stuck`, con su alarma propia según la spec 051, R9.7.
12. WHILE el modo retiene ese tipo THEN el sistema NO DEBE encolarlo: queda como hoy en `email.suppressed`.

### Requisito 3 — Los correos de acceso agotan en línea

**Historia de usuario:** Como equipo de Auphere, quiero que un enlace de un solo uso no acabe guardado en claro, y que quien lo pidió sepa qué hacer si no sale.

#### Criterios de aceptación

1. El sistema NO DEBE guardar las variables de un correo que no puede esperar en cola, ni antes ni después del intento.
2. WHEN uno de estos correos agota los intentos THEN el sistema DEBE devolver que no salió, DEBE dejarlo como `fallido` en el registro de envíos y DEBE registrar `email.send_failed`.
3. Lo que cada sitio hace con ese resultado NO DEBE cambiar: el alta sigue respondiendo 502, la invitación sigue diciendo que no salió, y el restablecimiento sigue fuera de la respuesta, sin oráculo.
4. El presupuesto de 30 s DEBE ser el mismo exista o no la cuenta, de modo que la duración de un alta no delate si una dirección ya tiene cuenta.

### Requisito 4 — Recibir los eventos del proveedor

**Historia de usuario:** Como equipo de Auphere, quiero saber qué pasó con un correo después de que el proveedor lo aceptara, sin abrir una puerta a quien quiera escribir en el registro.

#### Criterios de aceptación

1. El sistema DEBE ofrecer una sola ruta pública para los eventos del proveedor, y DEBE verificar la firma sobre los bytes tal como llegaron ANTES de interpretar nada: HMAC-SHA256 de `id.timestamp.cuerpo` con el secreto del endpoint, comparado en tiempo constante.
2. IF la firma falta o no coincide, o el `timestamp` se aleja más de 5 minutos del reloj, o el cuerpo supera los 64 KB, THEN el sistema DEBE rechazar con 400, NO DEBE leer el cuerpo ni guardar nada, y DEBE registrar `email.webhook_rejected` solo con el motivo.
3. IF el entorno no tiene secreto del webhook THEN la ruta DEBE rechazar todo, DEBE registrar `email.webhook_closed` y la API DEBE arrancar igualmente, como hace ya el cobro.
4. WHEN llega un `id` de evento ya procesado THEN el sistema DEBE responder 200 sin ningún otro efecto. DEBE recordarlo al menos 72 h, porque los reintentos del proveedor duran unas 28 h.
5. El sistema DEBE procesar `email.delivered`, `email.bounced`, `email.complained`, `email.suppressed` y `email.failed`. WHEN llega cualquier otro THEN DEBE responder 200 sin guardarlo.
6. WHEN un evento verificado corresponde a un envío de este entorno THEN el sistema DEBE asociarlo a ese envío, y DEBE tomar de él el negocio, el tipo y la plantilla.
7. IF un evento verificado no corresponde a ningún envío de este entorno THEN el sistema DEBE responder 200, NO DEBE guardar ni registrar dirección ni asunto, y DEBE registrar `email.webhook_foreign` solo con el tipo de evento.
8. IF un `email.delivered` llega después de un rebote, una queja o una supresión THEN el sistema NO DEBE borrar el problema.
9. El sistema DEBE responder en menos de 5 s, y NO DEBE enviar correo, llamar al proveedor ni ejecutar nada a partir de un evento.
10. IF la base de datos no está disponible THEN el sistema DEBE responder 5xx, para que el proveedor reintente.
11. El texto que traiga un evento DEBE tratarse como dato (constitución §III): DEBE guardarse recortado a 500 caracteres, DEBE enseñarse como texto y NO DEBE llegar a ningún agente, prompt ni herramienta.

### Requisito 5 — Qué se guarda

**Historia de usuario:** Como responsable de los datos, quiero guardar lo justo para saber qué falló, y durante un tiempo con razón.

#### Criterios de aceptación

1. WHEN se envía un correo en un modo que lo envía, THEN el sistema DEBE crear una entrada ANTES de llamar al proveedor, con tipo, plantilla, destinatarios, negocio, idioma, estado, fechas, número de intentos y el último error.
2. La entrada NO DEBE guardar el asunto. Las variables SOLO DEBEN existir mientras el correo está en cola.
3. WHEN llega un problema (rebote, queja, supresión o fallo) THEN el sistema DEBE guardar el tipo, el subtipo, el destinatario afectado, el motivo recortado y la fecha.
4. WHEN llega un `email.delivered` THEN el sistema DEBE guardar solo la fecha.
5. El sistema DEBE borrar entradas y eventos a los 90 días.
6. WHEN se borra un partner o un cliente THEN el sistema DEBE borrar sus entradas y sus eventos.
7. Los registros nuevos NO DEBEN llevar variables ni enlaces, y DEBEN llevar el negocio igual que los de la spec 051, R1.6.

### Requisito 6 — Lo que ve el operador

**Historia de usuario:** Como operador de Auphere, quiero ver en un solo sitio qué correos no han llegado, y poder fiarme de que un «sin problemas» es cierto.

#### Criterios de aceptación

1. La página Estado del panel DEBE tener una sección «Correo», con el mismo acceso de operador que el resto del panel.
2. La sección DEBE enseñar, en el periodo que ya elige esa página, cuántos correos se aceptaron, entregaron, rebotaron, recibieron queja, se suprimieron y fallaron, y la tasa de rebote y de quejas junto a los umbrales de Resend, 4 % y 0,08 %.
3. La sección DEBE listar cada problema con el tipo de correo en lenguaje llano, el destinatario, el partner y el cliente, la fecha, el motivo y qué hacer.
4. La sección DEBE enseñar cuántos correos hay en cola y desde cuándo espera el más antiguo.
5. WHERE se ha leído el contador del proveedor, la sección DEBE enseñar el consumo del día y del ciclo, sobre su límite, con cuándo se leyó y una línea que diga que la cuenta se comparte entre entornos.
6. La sección DEBE decir cuándo llegó el último evento.
7. IF el entorno no tiene secreto del webhook THEN la sección DEBE decir que los eventos no están conectados, y NO DEBE enseñar cifras de rebotes ni decir que no hay problemas.
8. IF hay correos aceptados en las últimas 24 horas y ningún evento en ese tiempo THEN la sección DEBE decir desde cuándo no llegan.
9. La sección DEBE decir «aceptado» hasta que un evento confirme otra cosa, y «entregado» solo con un `email.delivered`.
10. La sección DEBE ser de solo lectura. DEBE explicar cómo levantar una supresión en el panel de Resend y por dónde reenviar lo que ya tiene acción propia.
11. La sección DEBE tener estado de carga con la forma final, vacío, error y parcial. El vacío SOLO DEBE decir «ningún problema» con los eventos conectados y al día.
12. La sección DEBE cumplir WCAG 2.2 AA, DEBE usar los tokens de `@nexus/ui` y una dirección larga DEBE partirse sin desbordar a 360 px.

### Requisito 7 — Las alarmas

**Historia de usuario:** Como equipo de Auphere, quiero que me avisen de lo que no llega, sin que un fallo repetido llene el buzón y sin depender del proveedor que falla.

#### Criterios de aceptación

1. WHEN se registra `email.send_failed`, `email.variables_mismatch` o `email.not_configured` en cualquier servicio que pueda enviar (`api`, `scheduler`, `runner`, `metering`, `egress`) THEN la alarma `nexus-<entorno>-email-send-failed` DEBE pasar a ALARM en menos de 15 minutos.
2. WHEN el contador leído llega al 70 % del límite diario o del mensual, o el proveedor responde un 429 de cuota, THEN la alarma `nexus-<entorno>-email-quota-high` DEBE pasar a ALARM en menos de 15 minutos.
3. WHEN llega un rebote permanente, una queja o una supresión de un correo de este entorno THEN la alarma `nexus-<entorno>-email-delivery-problem` DEBE pasar a ALARM en menos de 15 minutos.
4. Las tres DEBEN comportarse como las de la spec 051, R9.5: un aviso al empezar, y otro solo si vuelve tras 3 horas sin registrarse.
5. La métrica y el aviso NO DEBEN llevar `tenant_id` ni datos de un negocio. La descripción DEBE decir qué consulta hacer y dónde está el detalle.
6. MIENTRAS `develop` no esté fusionada en `main`, las alarmas SOLO DEBEN existir en staging, y DEBEN hacerlo sin avisar a nadie (spec 051, R9.9). NO DEBE aplicarse nada en producción.
7. WHEN se fusione `develop` en `main` THEN las alarmas DEBEN aplicarse en producción y DEBEN avisar por el topic `nexus-prod-alerts`, que no pasa por Resend.
8. Una prueba de contrato DEBE fallar si un evento de un filtro no lo registra el código, o si un servicio que puede enviar no tiene su filtro.

### Requisito 8 — La cuota y la reputación

**Historia de usuario:** Como equipo de Auphere, quiero ver cuánto queda y que lo primero en quedarse sin correo nunca sea un acceso.

#### Criterios de aceptación

1. WHEN el proveedor responde a un envío THEN el sistema DEBE leer `x-resend-daily-quota` y `x-resend-monthly-quota`, si vienen, DEBE dejarlos en el registro del envío, y DEBE guardar el último valor con su hora en un sitio que vean todos los procesos del entorno.
2. Los límites DEBEN ser configuración por entorno, 100 y 3000 por defecto, de modo que cambiar de plan no exija cambiar código.
3. WHILE el contador diario leído hoy sea 70 o más, o el mensual 2850 o más, los correos que pueden esperar DEBEN seguir en cola, y los que no pueden DEBEN seguir saliendo.
4. WHEN un 429 de cuota diaria devuelve un correo en cola THEN el sistema DEBE programar su siguiente pasada para las 00:05 UTC.
5. IF el proveedor no devuelve contador diario THEN el sistema NO DEBE retener nada por el límite diario.
6. IF algún destinatario tiene un dominio reservado (D15) THEN el sistema NO DEBE enviarle nada. Fuera de producción DEBE registrar `email.suppressed` con el motivo y los enlaces, y en producción DEBE registrar `email.send_failed` sin enlaces, porque una dirección así en producción es un dato mal.

### Requisito 9 — Aislamiento

**Historia de usuario:** Como negocio cliente, quiero que lo que le pasa a un correo mío no lo vea otro, ni pueda escribirlo un tercero.

Cada criterio nace como prueba en `tests/isolation/`, se ve en rojo antes de implementar, y una prueba con `skip` no cubre nada. Las de barrido recorren el código, no una lista de sitios conocidos (constitución §I).

#### Criterios de aceptación

1. **Garantía 6, barrido.** Todo evento de registro nuevo de esta spec DEBE llevar el negocio cuando lo tiene y un valor explícito cuando no, y NINGUNO DEBE llevar variables, enlaces ni el texto de un evento.
2. **Garantía 6, el dueño sale del envío.** Un evento firmado cuyas etiquetas, destinatario o asunto nombran a otro partner NO DEBE cambiar el negocio de su envío, y si no corresponde a ningún envío NO DEBE crear nada. El sistema PUEDE usar una referencia propia enviada como etiqueta para encontrar el envío, pero solo para eso.
3. **Frontera de entorno.** Un evento de un correo de otro entorno NO DEBE dejar en este ninguna dirección, asunto ni mover ninguna alarma.
4. **Garantía 1, rozada.** El rol de tenant NO DEBE poder leer ni escribir el registro de envíos ni la cola. Si guardan `tenant_id`, `test_21_rls_covers_every_tenant_table.py` DEBE tener su justificación escrita.
5. **Eje de partner, barrido.** Ningún módulo de la consola, de la consola lite, de la app ni de las herramientas de un agente DEBE poder leer el registro de envíos, y la ruta del panel DEBE rechazar las credenciales de una consola, de una clave de partner y de un dispositivo.
6. **Barrido del catálogo.** Ningún tipo con un enlace de un solo uso DEBE poder esperar en cola, y la ficha de un tipo nuevo DEBE obligar a declararlo. Tras terminar cualquier correo, su entrada NO DEBE conservar variables.
7. **Garantía 8, rozada.** El panel y los registros NO DEBEN enseñar el nombre de un contacto final que viaje en las variables de un correo en cola.
8. **§III.** El texto de un evento NO DEBE llegar a ningún prompt ni herramienta de un agente.
9. **Lo que se borra.** `test_22_tenant_delete_leaves_nothing.py` DEBE cubrir el registro de envíos y sus eventos.

### Requisito 10 — Documentación y puertas

#### Criterios de aceptación

1. `docs/correos.md` DEBE describir, en el mismo commit que el código, los reintentos, la cola, el webhook, la sección del panel, las alarmas y la cuota. `.env.example` y la guía de paso a producción DEBEN nombrar el secreto nuevo.
2. Antes de dar la spec por terminada, `/cso` DEBE ejecutarse sobre el cambio, porque abre una entrada externa no confiable, y NO DEBE quedar ningún hallazgo HIGH o CRITICAL sin mitigar o aceptar por escrito. También `tenant-security-audit`, porque toca webhooks y aislamiento.
3. El cambio DEBE pasar `./scripts/verify.sh lint` y las pruebas de lo tocado, incluida la del contrato de nombres de crons del worker si se añade uno. Eso ha roto la tubería dos veces.
4. La verificación de la firma NO DEBE añadir dependencias: es HMAC de la biblioteca estándar, como en el webhook de Composio. Si el plan propone otra cosa, DEBE citar su licencia (constitución §VIII).

### Entidades clave

- **Registro de envío**: un correo que la plataforma intentó enviar, por grupo de idioma. Lleva el tipo, los destinatarios, el negocio, el estado (`en cola`, `aceptado`, `entregado`, `fallido`), los intentos y la clave de idempotencia. **Es de plataforma, como los avisos de la consola: no lo alcanza la RLS de ningún tenant, y el rol de tenant no lo lee.** El negocio lo pone el servidor al enviar. Vive 90 días.
- **Correo en cola**: un registro de envío que aún guarda lo compuesto (asunto, variables, respuesta). Solo existe para los tipos que pueden esperar, y como mucho 23 horas.
- **Evento de entrega**: lo que dijo el proveedor sobre un envío. Solo se guarda el problema o la fecha de entrega, con el motivo como dato, nunca como instrucción. Pertenece al negocio de su envío.
- **Contador de cuota**: el último consumo del día y del ciclo que dijo el proveedor, con su hora. Es de toda la cuenta de Resend, no del entorno que lo lee.

## Criterios de éxito *(obligatorio)*

- **CE-001**: con un proveedor que falla de forma intermitente, 100 correos dan **100 envíos y ningún duplicado**.
- **CE-002**: con el proveedor caído 6 horas y un reinicio en medio, el **100 %** de los correos automáticos sale al volver, una vez cada uno. Ninguno lleva un enlace de un solo uso guardado.
- **CE-003**: durante esa caída, un turno del agente no tarda ni un segundo más por el correo.
- **CE-004**: en staging, una invitación a cada dirección de prueba de Resend (rebote, queja, supresión) aparece en el panel en **menos de 5 minutos**, con su tipo y su negocio.
- **CE-005**: una semana con el webhook de staging recibiendo eventos de producción deja **0 direcciones de producción** en staging. Se comprueba con una consulta al registro de envíos y a los registros.
- **CE-006**: cada alarma pasa a ALARM en **menos de 15 minutos** tras su causa, y un fallo que se repite 2 horas da **una sola** transición.
- **CE-007**: con el contador en 70, un correo de acceso sale y un automático espera y sale al día siguiente.
- **CE-008**: la suite de `tests/isolation/` en verde, con las pruebas del Requisito 9 vistas antes en rojo. `/cso`, sin hallazgos HIGH o CRITICAL abiertos.
- **CE-009**: siete días después de fusionar la 051 y la rama del aviso de saldo, el consumo diario de la cuenta no pasa de **15 destinatarios** ningún día. Si pasa, se revisa la previsión de D13.
- **CE-010**: las siete condiciones de salida están cumplidas o, si no aplican todavía, con su fecha. Ningún rebote de producción se queda sin aparecer en el panel desde que esté conectado.

## Condiciones de salida *(lo que no es código)*

Ningún agente ha creado, comprado ni enviado nada. Estos son pasos de Luis, salvo que él diga otra cosa.

| # | Qué | Valor exacto | Cuándo | Cómo se comprueba |
|---|---|---|---|---|
| **C1** | **DMARC.** TXT en Cloudflare, donde están los servidores de nombres | Nombre: `_dmarc.auphere.com` · Valor: `v=DMARC1; p=none; rua=mailto:dmarc@auphere.com` · Y crear `dmarc@auphere.com` como alias en Google Workspace | **Ya**, no depende del código | `dig +short TXT _dmarc.auphere.com @1.1.1.1` devuelve ese valor, y llega el primer informe |
| **C2** | **`support@auphere.com`** existe y alguien lo lee. Es la dirección de respuesta de casi todos los correos | Confirmar el buzón o grupo en Google Workspace y **nombrar a la persona** que lo lee. Si no existe, crearlo | **Ya**. La 051 lo dio por supuesto | Escribir desde fuera de la organización: llega, y esa persona lo ve |
| **C3** | **Una clave por entorno** en Resend | Crear `auphere-staging`, con permiso `Sending access`, y ponerla en el secreto de staging como `NEXUS_RESEND_API_KEY`. Producción se queda con `Auphere Prod`. Revisar `Onboarding` y `amacrux-event`, y revocarlas si no se usan | Antes de probar en staging | Un correo de acceso de staging sale, y `check_email_templates.py` sigue pasando con la clave que use. No se ha comprobado que una clave `Sending access` envíe por plantilla: si no puede, se usa `Full access` y se deja escrito |
| **C4** | **Webhook de staging** | URL: `https://api.staging.auphere.com/webhook/resend` · Eventos: `email.delivered`, `email.bounced`, `email.complained`, `email.suppressed`, `email.failed` · Secreto: `NEXUS_RESEND_WEBHOOK_SECRET` en el secreto de staging | Antes de probar en staging | La Historia 3 pasa con las direcciones de prueba de Resend |
| **C5** | **El plan, al fusionar. Es una compra de Luis** | **Opción A, recomendada**: Pro, **20 USD al mes** (50 000 correos, sin límite diario, 5 webhooks, 10 dominios; [precios leídos el 2026-11-03](https://resend.com/pricing)), más otro webhook a `https://webhooks.auphere.com/webhook/resend` con los mismos eventos, su secreto en producción y los límites de la configuración al día (8.2). **Opción B, sin coste**: mover el único webhook del plan gratis a producción. Staging queda como «sin conectar» | Antes de fusionar `develop` en `main` | La Historia 3 pasa en producción con un correo de prueba |
| **C6** | **Alarmas en producción** | Aplicar los recursos de esta spec con `-target` y su `prod.tfvars`. Sin `-target`, el plan toca más cosas (ver `evidence/alarma-calibracion.md` de la 051) | Al fusionar, no antes | Forzar cada alarma con `set-alarm-state`: el aviso llega al buzón de la suscripción del topic |
| **C7** | **`/cso`** sobre la implementación | Sin hallazgos HIGH o CRITICAL abiertos | Antes de darla por terminada | Su informe, citado en el PR |

**Endurecer DMARC**, siempre con `rua` puesto:

| Paso | Cuándo | Valor |
|---|---|---|
| 1 | Hoy | `v=DMARC1; p=none; rua=mailto:dmarc@auphere.com` |
| 2 | Con 30 días de informes en los que Resend y Google Workspace pasan al 100 %, y `spf.dondominio.com` explicado o retirado del SPF | `v=DMARC1; p=quarantine; rua=mailto:dmarc@auphere.com` |
| 3 | Con 30 días más sin fallos legítimos | `v=DMARC1; p=reject; rua=mailto:dmarc@auphere.com` |

Antes del paso 2, abrir un correo real de cada remitente y comprobar `dmarc=pass` en sus cabeceras. Esta spec no lo ha mirado. Si leer XML resulta incómodo, Cloudflare ofrece DMARC Management para quien tiene su DNS allí; su documentación no aclara si cambia el `rua`, así que hay que verlo al activarlo.

## Fuera de alcance

- Marketing, y seguimiento de aperturas y clics: decisión de Luis.
- **Que el partner vea sus rebotes**: otra spec, junto a la pestaña Equipo de la 052 (D10). Hasta entonces, la 052 sigue sin decir «entregado».
- **Reenviar desde el panel o levantar una supresión**: la sección es de solo lectura, y los recibos ya tienen su acción de reenvío.
- **El aviso de cliente sin saldo que se repite**: va en su rama.
- **Separar la cuenta de Resend o crear un dominio de staging** (D14).
- **Vaciar la DLQ de producción**: no es de esta spec. Esta solo mide que su aviso dejó de gastar cuota.
- **Datadog**: si se aprueba, será otra spec.
- **Respaldar con otro proveedor de correo**: no hay datos que lo justifiquen. 0 fallos en 60 días.

## Supuestos

- Lo que se dice de Resend viene de su documentación, leída el 2026-11-03 (§Fuentes). Las cifras de cuota, webhooks y precios pueden cambiar. Lo que no se ha visto en la práctica, y se comprueba al probar en staging: la forma real de un evento, y que un rebote transitorio llegue como `email.bounced`, aunque su documentación lo describe como permanente y sus métricas cuentan los dos.
- La previsión de menos de 10 al día depende de las dos fusiones pendientes y del tráfico de hoy. Puede cambiar con más clientes: un `inbox_waiting` sale por conversación.
- Gmail y Google Workspace no informan de quejas, según Resend. Las cifras de quejas son un mínimo.
- El `scheduler` sigue siendo un solo proceso y ya envía casi todos los correos (1365 de 1379 en 60 días). La cola no añade una dependencia nueva, pero sí su punto ciego (§Casos límite).
- `infra/terraform/30-observability/` está cambiando en la rama `chore/observabilidad-sin-deriva`. Las alarmas de esta spec se escriben encima de esa rama. Su prueba `test_alarms_notify_only_in_production` y la R9.9 siguen valiendo sin excepción.
- Esta spec depende de la 051, ya en `develop`. La 052 no depende de esta ni al revés, pero las dos tocan el resultado de enviar una invitación: quien llegue segundo adapta su lado.
- `contacto@ladrian.dev` sigue siendo la única suscripción del topic de producción, y alguien la lee (spec 051).
- Los datos de este documento no llevan direcciones: el repositorio no es el sitio.

## Fuentes

Leídas el 2026-11-03: [precios](https://resend.com/pricing) · [cuotas y límites](https://resend.com/docs/knowledge-base/account-quotas-and-limits) · [límite de peticiones y cabeceras](https://resend.com/docs/api-reference/rate-limit) · [errores](https://resend.com/docs/api-reference/errors) · [idempotencia](https://resend.com/docs/dashboard/emails/idempotency-keys) · [eventos](https://resend.com/docs/dashboard/webhooks/event-types) · [verificar webhooks](https://resend.com/docs/webhooks/verify-webhooks-requests) · [reintentos de webhooks](https://resend.com/docs/webhooks/retries-and-replays) · [supresiones](https://resend.com/docs/dashboard/emails/email-suppressions) · [política de uso](https://resend.com/legal/acceptable-use) · [direcciones de prueba](https://resend.com/docs/dashboard/emails/send-test-emails) · [DMARC](https://resend.com/docs/dashboard/domains/dmarc) · [verificación manual de Svix](https://docs.svix.com/receiving/verifying-payloads/how-manual).
