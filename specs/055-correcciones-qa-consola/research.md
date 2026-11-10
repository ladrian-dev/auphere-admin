# Investigación: Correcciones de QA de la consola

No quedaban marcas por aclarar. Esto recoge las decisiones técnicas que salen de leer el código el 2026-11-05.

## R1. Las marcas del índice

- **Decisión**: cada sección recibe `onStateChange` y lo llama con un efecto cuando cambia su estado. El índice guarda esos estados y los pinta antes que los de la carga inicial.
- **Por qué**: el estado ya vive en cada sección, y un efecto cubre todos los caminos a la vez: guardar, «Es correcto», aceptar algo sugerido y recargar tras un conflicto. Como el estado viene de la respuesta de la API, un fallo no lo mueve.
- **Descartado**: subir todo el estado al padre, que rehace cinco secciones. Refrescar la página entera, que perdería una edición abierta en otra sección.

## R2. Añadir un ejemplo

- **Decisión**: una función pura en `builder-model.ts` devuelve el texto nuevo, «ya está» o «no cabe».
- **Por qué**: las reglas se prueban sin montar la pantalla. «Ya está» se decide buscando el texto del ejemplo dentro de la descripción.
- **Descartado**: deshacer con un botón. QA pide añadir, y añadir no borra nada.

## R3. La moneda desconocida

- **Decisión**: `known_currency` devuelve la del perfil, la del mercado o `None`. `ServicesOut.currency` pasa a ser opcional. `business_currency` conserva su contrato para los ajustes de Reservas, que ganan `currency_set`.
- **Por qué**: los consumidores que solo pintan no cambian. El rechazo está en un único sitio, al escribir un importe: `price_currency_required`.
- **Elegirla en el modal**: el cuerpo del servicio acepta `price_currency`, y solo se usa si el negocio aún no tiene ninguna. Moneda e importe se guardan juntos.
- **Una fila sin precio** no necesita moneda, pero la columna no admite vacío. Sin moneda conocida guarda `XXX`, el código ISO 4217 de «sin moneda», que nunca se pinta.
- **Descartado**: exigir la moneda al crear el cliente, que añade fricción a todas las altas para un caso raro.

## R4. Cambiar la moneda de los precios

- **Decisión**: `update_basics` repreciará siempre que cambie la moneda, sea cual sea quien la cambie, y lo escribirá también como cambio de la sección de Servicios. La confirmación se pide en `PUT /basics`: sin `confirm_price_change`, y con servicios con importe, responde 409 `prices_would_change` con cuántos son.
- **El número**: `nuevo = viejo × 10^(decimales nuevos − decimales viejos)`, con los decimales de la moneda que tenía cada servicio. Al bajar decimales se redondea al entero más cercano, y el aviso lo dice.
- **Por qué**: subir la revisión de Servicios hace saltar el conflicto en un modal abierto. Deshacer el cambio de Datos básicos pasa por el mismo camino y devuelve la moneda.
- **Los servicios archivados** también se mueven, porque deshacer un archivado no debe traer una moneda vieja, pero no cuentan en el aviso.
- **Las reservas** no se tocan: guardan su moneda y su precio.
- **Datos ya mezclados**: al editar una fila se pasa a la moneda del negocio. No hay migración de datos, y C2 sigue siendo decisión del owner.

## R5. Los decimales de cada fila

- **Decisión**: `ServiceOut` gana `exponent`, calculado con la moneda de la fila.
- **Por qué**: la API ya tiene su tabla de decimales. Si lo calculara también la consola, serían dos tablas. Para la moneda que se elige en el modal, donde aún no hay fila, se usa `minorDigits`, y un test comprueba que coincide con la API en toda la lista.

## R6. Recuperar con una invitación viva

- **Decisión**: si no hay cuenta, se añade una tarea en segundo plano, **también cuando no hay invitación**. La tarea abre su propia sesión, busca la invitación viva más reciente de esa dirección y la reenvía.
- **Por qué**: la consulta y la escritura quedan fuera de la respuesta, así que el reloj no dice nada. Es el mismo razonamiento que ya tiene el envío de correo en esa ruta.
- **Tres tipos de invitación**:
  - Propietario, de Auphere (`invited_by` vacío): `owner_invitation.resend` y `deliver`.
  - Equipo: se revoca y se crea con el mismo rol e `invited_by`, y se envía con el texto de `team.py`, extraído a una función sin `principal`.
  - Cliente: `client_access.resend` y `send_client_invitation`.
- **Partner apagado**: si el partner está suspendido, con la consola apagada, o el acceso de cliente está cerrado, no sale nada. Esas funciones ya lo rechazan, y aquí se registra sin decirlo.
- **Actor**: `system:password_reset`.
- **Descartado**: enviar un enlace de restablecer a quien no tiene cuenta. No hay contraseña que restablecer.

## R7. La categoría

- **Decisión**: una columna `category`, de hasta 40 caracteres, en `reservation_services`. Sin tabla aparte.
- **Normalizar**: se recorta, se colapsan los espacios y, sin distinguir mayúsculas, se adopta la forma de un servicio vivo que ya la use. Se hace al escribir, en `services_catalog`, para todos los caminos.
- **Sugerencias**: un `<datalist>` con las categorías de los servicios vivos, leídas de la lista ya cargada. Sin componente ni dependencia nuevos.
- **Agente**: en `compilation.py` la categoría va como primera parte de la línea, por `_line`. El orden de las líneas no cambia, para que los agentes sin categoría compilen los mismos bytes.
- **Reservas de la lite**: `lite/reservas.py` escribe en la fila directamente, así que acepta `category` con la misma normalización.
- **Descartado**: una tabla de categorías, que exigiría pantallas para renombrar y borrar, que nadie ha pedido.

## R8. La etiqueta de «Señal»

- **Decisión**: cambiar `business.policies.deposit`, `builder.cb.policy.deposit`, `compilation.py` y `agent_draft.py`. La ayuda es una clave nueva. Solo cambia la etiqueta, no los valores.
- **Consecuencia**: cambia el texto compilado de los agentes con señal escrita. Es lo que pide la spec (6.2), y entra en su siguiente compilación.
