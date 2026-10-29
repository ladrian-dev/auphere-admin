# Especificación: Instagram y Messenger como canales de Auphere

**Rama**: `049-meta-instagram-messenger` · **Creada**: 2026-10-29 · **Estado**: Aprobada para plan

**Entrada**: owner, 2026-10-29 — «Adapter de canales Meta: Instagram (Unified Login) y Messenger en Auphere. Un parser compartido para `object=instagram` y `object=page` en `/webhook/meta`, adapters con ChannelAdapter, respuesta del agente por DM, comentarios a DM, takeover humano con Human Agent, y preparar el material de App Review de Meta (llamadas de prueba y screencasts por permiso)». Configuración de Instagram (Unified Login, Config ID `1157578836735566`) y webhooks de Instagram y Page ya creados y verificados en la app de Meta el 2026-10-29.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API y webhook de la plataforma. No se abre navegador, máquina ni escritorio: es un canal de mensajería más, como WhatsApp, sobre la superficie ya abierta |
| **Garantías de aislamiento tocadas** | **1** (RLS: el cliente del mensaje se resuelve desde el canal, nunca desde el payload) · **4** (el hilo del agente incluye el canal: la misma persona por Instagram y por WhatsApp son hilos distintos) · **6** (logs y trazas etiquetados con tenant y canal) · **8** (dos clientes finales del mismo negocio no se mezclan: la identidad es la de la plataforma —IGSID/PSID—, nunca un argumento del modelo). Pruebas en `tests/isolation/` |
| **Nota de KB que la justifica** | `[[whatsapp-connector/decisions/ADR-030-instagram-connector]]` · `[[whatsapp-connector/11-instagram-build-plan]]` · `[[whatsapp-connector/13-meta-canales-investigacion-2026-10]]` · `[[decisions/ADR-029-tiktok-business-messaging-channel]]` · `[[decisions/ADR-049-messenger-channel]]` (aceptado 2026-10-29) · enmienda 1 de ADR-030 (aceptada) |
| **Qué se mide** | Modelo: cada respuesta del agente por Instagram o Messenger entra en el medidor del partner igual que por WhatsApp. Sin herramienta de pago nueva |

## Origen

Medido el 2026-10-29 en la app de Meta y en el código:

- La app tiene los casos de uso de Instagram y Messenger, la configuración de inicio de sesión unificado de Instagram y los dos webhooks suscritos (Instagram: 8 campos; Page: 7). **Ningún permiso de Instagram ni de Messenger está aprobado** para cuentas de terceros: la App Review de ambos no se puede saltar.
- El backend solo procesa eventos de WhatsApp. Un evento de Instagram o de Page que llegue hoy se registra como campo no tratado y se descarta.
- Los perfiles de capacidades de ambos canales ya existen; falta todo lo demás (identidad, envío, conexión de cuentas, ventana de mensajería, traspaso a humano).
- Meta exige, por permiso, una llamada real en los últimos 30 días y un screencast de la función en uso. Sin canal funcionando no hay nada que grabar: por eso el material de revisión es parte de esta spec y no un paso aparte.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Un cliente final escribe por Instagram y el agente responde (Prioridad: P1)

El operador conecta la cuenta profesional de Instagram de un cliente de Auphere. Una persona escribe un mensaje directo a esa cuenta y el agente del cliente le contesta en la misma conversación.

**Por qué esta prioridad**: es el valor central del canal y lo que Meta pide demostrar para `instagram_manage_messages`. Todo lo demás se apoya en esto.

**Prueba independiente**: con una cuenta profesional de prueba conectada, enviar un DM desde otra cuenta y ver la respuesta del agente en menos de un minuto, con la conversación visible en la consola.

**Escenarios de aceptación**:

1. **Dado** una cuenta de Instagram conectada a un cliente con un agente activo, **cuando** una persona le escribe un DM, **entonces** el agente responde en el mismo hilo y la conversación aparece en la consola del cliente con el canal «Instagram».
2. **Dado** la misma persona que ya escribió antes por WhatsApp, **cuando** escribe por Instagram, **entonces** es una conversación distinta, con su propio historial.
3. **Dado** dos personas que escriben a la vez a la misma cuenta, **cuando** el agente responde, **entonces** cada una recibe solo su respuesta.
4. **Dado** un mensaje que no escribió una persona (el eco de lo que envía la propia cuenta), **cuando** llega, **entonces** no dispara al agente.

---

### Historia 2 — Lo mismo por Messenger (Prioridad: P1)

El operador conecta la Página de Facebook de un cliente. Una persona escribe a la Página por Messenger y el agente le contesta.

**Por qué esta prioridad**: Meta revisa Messenger aparte (`pages_messaging` y compañía); comparte con Instagram casi toda la mecánica y se entrega en la misma ronda.

**Prueba independiente**: con una Página de prueba conectada, escribirle desde una cuenta con rol de evaluador y recibir la respuesta del agente.

**Escenarios de aceptación**:

1. **Dado** una Página conectada a un cliente, **cuando** una persona le escribe, **entonces** el agente responde y la conversación aparece con el canal «Messenger».
2. **Dado** una Página y una cuenta de Instagram del mismo negocio, **cuando** llegan mensajes por ambas, **entonces** cada conversación queda en su canal.

---

### Historia 3 — Del comentario al mensaje directo (Prioridad: P2)

Una persona comenta una publicación del negocio. El agente responde al comentario y, cuando procede, abre la conversación por mensaje directo.

**Por qué esta prioridad**: es el embudo de captación de Instagram y lo que Meta pide demostrar para `instagram_manage_comments`. Va después porque depende de la Historia 1.

**Prueba independiente**: comentar una publicación de la cuenta de prueba y ver la respuesta pública y el DM.

**Escenarios de aceptación**:

1. **Dado** una publicación de la cuenta conectada, **cuando** alguien la comenta, **entonces** el agente puede responder al comentario en público.
2. **Dado** un comentario que pide información, **cuando** el agente decide continuar en privado, **entonces** envía un DM a esa persona referido a su comentario.
3. **Dado** un comentario del propio negocio, **cuando** llega, **entonces** no dispara al agente.

---

### Historia 4 — Una persona del equipo toma el control (Prioridad: P2)

Una persona del negocio toma la conversación desde la consola, y puede seguir respondiendo pasadas las 24 horas de la ventana normal, hasta 7 días.

**Por qué esta prioridad**: es el permiso especial **Human Agent** de Meta, que exige demostrar una persona real al otro lado. Sin ella la ventana de respuesta es de 24 horas.

**Prueba independiente**: tomar una conversación con más de 24 horas de silencio y responder con éxito.

**Escenarios de aceptación**:

1. **Dado** una conversación que supera las 24 horas, **cuando** el agente intenta responder solo, **entonces** el envío se rechaza con un motivo claro y no se reintenta.
2. **Dado** la misma conversación con una persona del equipo que la ha tomado, **cuando** responde dentro de los 7 días, **entonces** el mensaje se envía.
3. **Dado** una conversación a la que ninguna persona ha tomado, **cuando** pasa la ventana, **entonces** nunca se usa la etiqueta de agente humano.

---

### Historia 5 — Material para la revisión de Meta (Prioridad: P1)

El equipo puede demostrar, permiso por permiso, que Auphere usa lo que pide, y enviar la solicitud de revisión con todo en regla.

**Por qué esta prioridad**: sin aprobación, solo cuentas con rol en la app pueden usar los canales; el resto de la spec no llega a clientes reales.

**Prueba independiente**: seguir el kit paso a paso con la cuenta y la Página de prueba y obtener un vídeo por permiso y un registro de al menos una llamada exitosa por permiso.

**Escenarios de aceptación**:

1. **Dado** el kit de revisión, **cuando** se sigue el guion de un permiso, **entonces** el vídeo muestra el recorrido completo (conceder → usar → resultado visible) en 1 a 3 minutos y sin información personal real.
2. **Dado** la lista de permisos pedidos, **cuando** se compara con lo que el código usa, **entonces** no sobra ninguno ni falta ninguno.
3. **Dado** un permiso sin llamada exitosa en los últimos 30 días, **cuando** se prepara el envío, **entonces** la lista de comprobación lo marca como pendiente.

---

### Casos límite

- ¿Qué pasa si la persona no ha escrito primero? Meta no permite iniciar la conversación: el envío se rechaza con un motivo claro.
- ¿Qué pasa si el cliente tiene apagada la opción «Herramientas conectadas» en Instagram? Las llamadas fallan en silencio: la conexión lo detecta y se lo dice al operador, con el paso exacto para encenderla.
- ¿Qué pasa si llega el mismo evento dos veces (Meta reintenta)? Se procesa una sola vez.
- ¿Qué pasa con un evento con firma inválida o de una cuenta no conectada? Se rechaza o se ignora sin tocar datos de ningún cliente.
- ¿Qué pasa si la cuenta o la Página se desconecta o pierde el permiso? El canal pasa a «requiere atención», el agente deja de intentar enviar y el operador lo ve.
- ¿Qué pasa con adjuntos (imagen, audio, vídeo, documento)? Se reciben y se pasan al agente; los que Instagram o Messenger no admiten al enviar se degradan a texto con aviso.
- ¿Qué pasa con las reacciones, las lecturas y los mensajes editados? Se registran sin disparar al agente.
- ¿Qué ve el partner o el cliente cuando Instagram o Messenger **no está disponible** para su cuenta? Nada: ni botón apagado ni explicación (constitución §V). Solo el panel de operador muestra el estado.

## Requisitos *(obligatorio)*

### Requisito 1 — Recibir eventos de Instagram y Messenger

**Historia de usuario:** Como plataforma, quiero recibir y atribuir a su cliente los eventos de Instagram y de las Páginas, para que el agente correcto los atienda.

#### Criterios de aceptación

1. WHEN llega a la dirección de webhook compartida un evento de Instagram o de Página con firma válida THEN el sistema DEBE atribuirlo al cliente dueño de esa cuenta o Página a partir del canal registrado, y NO DEBE leer el cliente del contenido del evento.
2. IF la firma es inválida THEN el sistema DEBE rechazar el evento y NO DEBE procesar nada de él.
3. IF el evento es de una cuenta o Página que ningún cliente tiene conectada THEN el sistema DEBE ignorarlo y dejar constancia sin datos personales.
4. WHEN llega un evento ya procesado THEN el sistema DEBE tratarlo una sola vez.
5. WHEN llega un campo que el sistema no trata THEN el sistema DEBE responder éxito a Meta, registrarlo y no fallar.
6. El sistema DEBE seguir procesando los eventos de WhatsApp exactamente igual que antes.

### Requisito 2 — Conversar con el agente por mensaje directo

**Historia de usuario:** Como cliente final, quiero escribir por Instagram o Messenger y recibir respuesta del agente del negocio, para resolver mi duda donde ya estoy.

#### Criterios de aceptación

1. WHEN una persona escribe a una cuenta o Página conectada THEN el sistema DEBE entregar el mensaje al agente del cliente y enviar su respuesta por el mismo canal.
2. El sistema DEBE identificar a cada persona por el identificador que da la plataforma de origen, y NO DEBE aceptar ese identificador como argumento del modelo.
3. WHERE la misma persona escribe por canales distintos EL sistema DEBE mantener conversaciones separadas.
4. WHEN el agente responde con botones o respuestas rápidas THEN el sistema DEBE mostrarlos con las capacidades de cada canal y degradar a texto lo que el canal no admita, con el texto de reserva obligatorio.
5. IF el mensaje es un eco de la propia cuenta THEN el sistema NO DEBE enviarlo al agente.
6. WHEN el agente responde THEN el consumo DEBE entrar en el medidor del partner con el canal indicado.

### Requisito 3 — Respetar las reglas de mensajería de Meta

**Historia de usuario:** Como operador, quiero que Auphere nunca rompa las reglas de Meta, para no poner en riesgo el acceso de todos los clientes.

#### Criterios de aceptación

1. IF la persona no ha escrito primero o la ventana de 24 horas ha vencido THEN el sistema DEBE rechazar el envío automático con un motivo claro y NO DEBE reintentarlo.
2. WHERE una persona del equipo ha tomado la conversación EL sistema DEBE permitirle responder hasta 7 días después del último mensaje de la persona, con la etiqueta de agente humano.
3. IF no hay una persona real en la conversación THEN el sistema NO DEBE usar nunca la etiqueta de agente humano, ni de forma automática ni desde el agente.
4. El sistema DEBE dejar en la auditoría quién tomó cada conversación y cuándo.

### Requisito 4 — Comentarios y paso al mensaje directo

**Historia de usuario:** Como negocio, quiero responder a los comentarios de mis publicaciones y continuar en privado, para convertir comentarios en conversaciones.

#### Criterios de aceptación

1. WHEN una persona comenta una publicación de una cuenta conectada THEN el sistema DEBE ofrecer el comentario al agente como entrada distinta de un DM.
2. WHEN el agente responde un comentario THEN el sistema DEBE publicarlo como respuesta a ese comentario.
3. WHEN el agente pasa a mensaje directo THEN el sistema DEBE enviarlo referido al comentario de origen, una sola vez por comentario.
4. IF el comentario es del propio negocio THEN el sistema NO DEBE enviarlo al agente.

### Requisito 5 — Conectar y desconectar cuentas

**Historia de usuario:** Como operador, quiero conectar la cuenta de Instagram o la Página de un cliente desde el panel, para que empiece a atender.

#### Criterios de aceptación

1. WHEN el operador conecta una cuenta o Página de un cliente THEN el sistema DEBE guardar su acceso cifrado, registrar el canal y suscribir los eventos, y el canal DEBE aparecer en la lista de Canales del cliente con su estado.
2. IF falta algo que impide funcionar (cuenta personal, mensajes desactivados, «Herramientas conectadas» apagado, permiso no concedido) THEN el sistema DEBE decir cuál y cómo corregirlo, y NO DEBE dejar el canal como activo.
3. WHEN el operador desconecta el canal THEN el sistema DEBE dejar de recibir y de enviar por él, y conservar el historial.
4. El sistema DEBE pedir en la conexión solo los permisos que usa, y NO DEBE pedir publicar contenido ni gestionar anuncios.
5. WHERE el canal no está disponible para un partner o cliente EL sistema NO DEBE mostrarlo en la consola de partners ni en la lite.

### Requisito 6 — Material de revisión de Meta

**Historia de usuario:** Como responsable de la integración, quiero un kit reproducible de pruebas y vídeos, para que Meta apruebe cada permiso a la primera.

#### Criterios de aceptación

1. El sistema DEBE tener una cuenta profesional de prueba, una Página de prueba y una persona evaluadora con todo preparado, y un procedimiento para reproducirlas.
2. WHEN se sigue el guion de un permiso THEN DEBE producirse al menos una llamada exitosa con ese permiso en la app y un vídeo de 1 a 3 minutos, sin audio, en inglés, en alta definición y con una descripción de uso propia, no copiada de otro permiso.
3. El kit DEBE cubrir `instagram_business_manage_messages` o `instagram_manage_messages` según la vía de acceso, `instagram_manage_comments`, `instagram_basic`, `pages_messaging`, `pages_manage_metadata`, `pages_show_list`, `pages_read_engagement`, `business_management` y la función Human Agent.
4. El kit DEBE incluir la comprobación previa de las direcciones de privacidad, condiciones y eliminación de datos, y de las instrucciones de prueba de la app.
5. IF alguna llamada de prueba sale con credenciales o secretos visibles THEN el vídeo NO DEBE publicarse.

### Entidades clave

- **Canal de Instagram / de Messenger**: una cuenta profesional o una Página conectada a **un** cliente. Pertenece al tenant del cliente (columna de tenant, RLS). Guarda su estado, su acceso cifrado y la última comprobación.
- **Persona (cliente final) por canal**: identificada por el identificador de la plataforma de origen, dentro del canal; sin teléfono.
- **Conversación**: una por persona y canal. Guarda quién la atiende (agente o persona del equipo) y la fecha del último mensaje de la persona, de la que se deduce la ventana.
- **Comentario atendido**: referencia al comentario y a la publicación, y si ya se envió el mensaje directo.
- **Registro de prueba de permiso**: permiso, fecha de la última llamada exitosa y vídeo asociado.

## Criterios de éxito *(obligatorio)*

- **CE-001**: una persona escribe por Instagram y recibe respuesta del agente en menos de un minuto, en el 95 % de los intentos de la prueba.
- **CE-002**: lo mismo por Messenger.
- **CE-003**: cero mensajes de un cliente visibles en otro, en la batería de pruebas de aislamiento con dos clientes y dos personas por cliente.
- **CE-004**: cero envíos con la etiqueta de agente humano sin una persona real en la conversación.
- **CE-005**: el kit produce un vídeo y una llamada exitosa para cada permiso pedido, sin ninguno de más, antes de enviar la solicitud.
- **CE-006**: la solicitud de revisión se envía una sola vez con todos los permisos de Instagram y Messenger; los permisos de WhatsApp ya aprobados no se modifican.
- **CE-007**: WhatsApp no cambia: los mismos mensajes se procesan igual antes y después.

## Fuera de alcance

- **Publicar contenido en Instagram y gestionar anuncios o estadísticas** — la configuración de Meta los incluye por defecto, pero el producto no los usa; se quitan de lo que se pide.
- **Threads, Telegram, X** — canales distintos, una spec por canal.
- **Mensajes de marketing de pago y plantillas de Messenger** — no hay caso de uso.
- **Iniciar conversaciones en frío** — Meta no lo permite en estos canales; solo se contempla comentario a mensaje directo y anuncios con destino al DM, y estos últimos no se construyen aquí.
- **Cuentas personales de Instagram** — solo profesionales.
- **Facebook Login para el cliente final** — el acceso lo da el negocio, no su cliente.
- **Mostrar el canal en la consola de partners o lite** — hasta que Meta apruebe; hasta entonces es solo del panel de operador.

## Supuestos

- Se usa el **inicio de sesión unificado** de Instagram (decisión del owner, 2026-10-29), que sustituye a la elección de ADR-030 (Instagram Login). El ADR se enmienda o se sustituye antes del plan.
- Messenger tiene su ADR (**ADR-049, aceptado el 2026-10-29**) y ADR-030 está enmendado (enmienda 1, aceptada el mismo día). El owner confirmó: Messenger en la misma ronda que Instagram, primera conexión por el operador, revisión de Meta aparte de la de catálogo y publicar contenido fuera de alcance.
- El acceso de cada cuenta es un token de usuario del sistema que no caduca, así que no hace falta el trabajo programado de renovación a 60 días que preveía ADR-030. Si Meta cambia eso en la revisión, se reabre.
- El webhook de Instagram y el de Página ya están verificados y suscritos con los campos de mensajes, comentarios, menciones, traspasos y ecos.
- La primera conexión de cuentas es **del operador desde el panel** (como el WhatsApp «propio»); el registro integrado para el partner viene después, cuando Meta apruebe.
- El agente y su prompt son los de siempre: el canal solo cambia lo que renderiza (capacidades ya definidas para ambos).
- La cuenta de Facelad (verificada) es la dueña de la app; las cuentas de prueba usan roles de la app, que no requieren aprobación.
- La solicitud actual de revisión (catálogo y gestión de negocio) sigue sin enviarse; esta spec decide si los permisos de Instagram y Messenger van en el mismo envío o en uno posterior, sin tocar los aprobados de WhatsApp.
