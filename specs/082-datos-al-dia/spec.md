# Especificación: datos al día en la consola

**Rama**: `082-datos-al-dia` · **Creada**: 2026-11-26 · **Estado**: Borrador, decidido sin Luis (lo revisa al final)

**Entrada**: Luis, 2026-11-26, sobre la beta de Jemma's Hair (partner Autprod): «empieza a trabajar en los P0 y P1 hasta tenerlos listos y probados», respetando el design system de Auphere. Esta spec es la 082 del lote: que lo que la persona ve en la consola esté al día sin recargar. Luis decidió usar React Query (TanStack Query) en la consola, solo en las pantallas con datos vivos.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` API de la consola (rutas lite y de partner que ya existen) y la consola web en el navegador de la persona. **No abre ninguna superficie**: el aviso nuevo viaja por la línea en vivo de la Bandeja, que ya existe (spec 030, D17), y la consola sigue leyendo por sus Server Actions. La consola no guarda ninguna credencial del backend. |
| **Garantías de aislamiento tocadas** | **Garantía 1 (separación entre negocios), en la línea en vivo.** El aviso nuevo `reservations.changed` sale por el canal del negocio (`inbox:{tenant}`) y la línea se abre con el negocio de la sesión, nunca con uno que mande quien llama. La línea pasa a admitir a una persona con Reservas y sin Bandeja: ve solo los avisos de sus módulos. Lleva su prueba en `tests/isolation/`. **La garantía 8 no se toca**: el aviso no lleva datos del cliente final, solo «algo cambió». |
| **Nota de KB que la justifica** | `[[research/2026-11-26-beta-jemma-p0-p1]]` (sección 082) en `/Users/lmatos/Work/Auphere/nexus/`. |
| **Qué se mide** | **Nada.** No llama al modelo (el resumen del agente se oculta, no se regenera), no gasta reloj de máquina ni herramientas de pago. El sonido se genera en el navegador, sin fichero. |

## Por qué

En la beta, la consola enseña datos viejos en cinco sitios:

1. **Reservas.** Luis canceló una reserva y no vio el cambio hasta recargar. Las reservas que hace el agente solo aparecen con el sondeo de 45 s: la app del teléfono escucha el aviso `reservations.changed`, pero nadie lo emite.
2. **Agente › Conocimiento.** Al subir un documento o añadir una web, ni la lista ni el resumen «Qué sabe» se actualizan. Una fuente que se está leyendo se queda en «Leyendo» hasta recargar.
3. **Bandeja.** No suena al llegar un mensaje. Fuera de la Bandeja, el contador de no leídos tarda hasta 60 s y se esconde con la barra plegada. Al volver la conexión no se relee nada, y la pestaña del navegador no dice cuántos hay sin leer.
4. **Resumen del agente.** El panel del contacto enseña el resumen del último escalado aunque la conversación ya se resolvió y volvió a empezar.
5. **Avatar.** WhatsApp no da foto, así que todos los contactos se ven iguales. Un contacto sin nombre sale como «·». El nombre de usuario de WhatsApp se guarda pero no se pinta, y el nombre no cambia cuando el contacto cambia su perfil.

## Clarificaciones

### Sesión 2026-11-26 (decidido sin Luis, para su revisión)

Luis no aprueba pasos intermedios en este lote: lo que se decidió sin él está aquí.

- P: ¿El resumen del agente se regenera o se oculta? → R: Se oculta tras Resolver o pasado el corte `context_from`, sin llamar al modelo (lo decidió Luis en la nota de KB).
- P: ¿Cuándo suena? → R: Con cada mensaje entrante, en cualquier pantalla de la consola, salvo si esa conversación está abierta y a la vista. Como mucho una vez cada 3 s.
- P: ¿Dónde se apaga el sonido? → R: En el diálogo de ajustes de la Bandeja, guardado en el navegador. Encendido por defecto.
- P: ¿Qué se ve en un contacto sin nombre? → R: El icono de persona, en lugar de unas cifras sin sentido.
- P: ¿Cuándo se actualiza el nombre del contacto? → R: Cuando WhatsApp manda un nombre de perfil distinto del guardado, salvo que el nombre lo haya escrito una persona del equipo (al crear una reserva para un número nuevo). En los contactos de antes, sin esa marca, gana el perfil.
- P: ¿Una persona con Reservas y sin Bandeja recibe la línea en vivo? → R: Sí, solo con el aviso de reservas.
- P: ¿Suena con la pestaña oculta? → R: Sí. El caso límite decía que no, y eso contradecía 3.2, que solo calla con la conversación abierta **y** la pestaña visible. Lo detectó `/speckit-analyze` el 2026-11-26 y se decidió a favor de 3.2.
- P: ¿Toda la Bandeja pasa a React Query? → R: No. Se comparte la línea y se arregla la reconexión; la lista y la conversación siguen como están (ver «Fuera de alcance»).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — La agenda dice lo que hay (Prioridad: P1)

La persona del negocio cancela, mueve o cambia el estado de una reserva, y la agenda lo enseña al momento. Mientras la tiene abierta, el agente reserva por WhatsApp y la cita aparece sola en segundos.

**Por qué esta prioridad**: es lo que Luis vio fallar, y Jemma trabaja con la agenda abierta todo el día.

**Prueba independiente**: con la agenda abierta en un navegador, se cancela una reserva y se comprueba que desaparece sin recargar. Después, una reserva hecha por detrás (como la del agente) aparece en menos de 5 s.

**Escenarios de aceptación**:

1. **Dado** la agenda abierta en día, semana o lista, **cuando** la persona cancela una reserva, **entonces** la reserva sale de la agenda sin recargar.
2. **Dado** la ficha de una reserva abierta, **cuando** la persona la marca como «No vino», **entonces** la ficha y la agenda enseñan lo mismo, y un segundo clic mientras se guarda no manda otra orden.
3. **Dado** la agenda abierta, **cuando** el agente crea, mueve o cancela una reserva, **entonces** la agenda la enseña en menos de 5 s, sin esperar al sondeo.
4. **Dado** la agenda abierta y la línea en vivo caída, **cuando** pasan 45 s, **entonces** la agenda relee como hoy y dice cuando lo que enseña puede no estar al día.

---

### Historia 2 — El conocimiento del agente se ve al añadirlo (Prioridad: P1)

Quien configura el agente sube un PDF o añade una web, y lo ve en la lista y en «Qué sabe» al momento. Mientras se lee, la fila dice «Leyendo» y pasa sola a «Lista» o «No se pudo leer».

**Por qué esta prioridad**: sin esto parece que la subida no funcionó, y se repite.

**Prueba independiente**: en la pantalla del agente, se añade una fuente y se comprueba la lista y el resumen sin recargar.

**Escenarios de aceptación**:

1. **Dado** la pestaña Conocimiento, **cuando** se sube un archivo, **entonces** aparece en la lista y «Qué sabe» lo cuenta.
2. **Dado** una fuente en «Leyendo», **cuando** termina de leerse, **entonces** la fila cambia sola, sin recargar.
3. **Dado** una fuente quitada, **cuando** se mira «Qué sabe», **entonces** no la cuenta.
4. **Dado** una subida que no responde, **cuando** pasa el plazo, **entonces** se dice que no respondió a tiempo y la lista se vuelve a leer, por si la fuente sí entró.

---

### Historia 3 — La Bandeja avisa (Prioridad: P1)

Jemma está en Reservas y entra un WhatsApp. Suena un aviso, el contador de la barra lateral sube al momento (también con la barra plegada) y la pestaña del navegador dice «(1)». Si se corta la conexión y vuelve, lo que llegó mientras tanto aparece.

**Por qué esta prioridad**: un mensaje que nadie ve es un cliente que se va.

**Prueba independiente**: con la consola abierta fuera de la Bandeja, se simula un mensaje entrante y se comprueba el contador, el título y el sonido.

**Escenarios de aceptación**:

1. **Dado** la consola abierta en cualquier pantalla, **cuando** entra un mensaje de un cliente, **entonces** suena un aviso breve, salvo que la persona lo haya apagado.
2. **Dado** el mismo mensaje, **cuando** llega, **entonces** el contador de la barra lateral y el título de la pestaña suben en menos de 2 s.
3. **Dado** la barra lateral plegada, **cuando** hay mensajes sin leer, **entonces** el número se ve en la esquina del icono de la Bandeja.
4. **Dado** la Bandeja abierta y la línea caída, **cuando** la línea vuelve, **entonces** la lista, la conversación abierta y el contador se vuelven a leer.

---

### Historia 4 — El resumen del agente no miente (Prioridad: P2)

Tras resolver una conversación, el panel del contacto deja de enseñar el resumen del escalado anterior.

**Prueba independiente**: se escala, se resuelve y se reabre una conversación, y se lee su detalle.

**Escenarios de aceptación**:

1. **Dado** una conversación escalada y luego resuelta, **cuando** se abre, **entonces** no hay resumen.
2. **Dado** una conversación que vuelve a escalar, **cuando** se abre, **entonces** enseña el resumen nuevo.

---

### Historia 5 — Cada contacto se reconoce (Prioridad: P2)

En la lista de la Bandeja, cada contacto tiene su inicial sobre un color propio que se lee bien. Un contacto sin nombre tiene un icono de persona, no «·». Si tiene nombre de usuario de WhatsApp, se ve. Si cambia su nombre de perfil, la Bandeja lo enseña con el siguiente mensaje.

**Prueba independiente**: se pinta la lista con contactos con y sin nombre, y se manda un mensaje con un nombre de perfil nuevo.

**Escenarios de aceptación**:

1. **Dado** dos contactos distintos sin foto, **cuando** se pinta la lista, **entonces** cada uno lleva su color, el mismo en la lista, la conversación y el panel.
2. **Dado** un contacto solo con número, **cuando** se pinta, **entonces** lleva el icono de persona.
3. **Dado** un contacto que cambió su nombre en WhatsApp, **cuando** escribe, **entonces** la Bandeja enseña el nombre nuevo, salvo que el nombre lo haya escrito una persona del equipo.

---

### Casos límite

- **Una relectura que falla en parte.** La agenda conserva la última lectura completa y lo dice (spec 064, 2.9), como hoy.
- **Muchos avisos seguidos.** Una ráfaga de avisos es una sola relectura, y suena una sola vez.
- **Navegador que bloquea el sonido.** Hasta que la persona toca algo de la página, no suena, y no se pinta ningún error. Después, sí.
- **Persona con Reservas y sin Bandeja.** Recibe el aviso de reservas por la misma línea, pero ningún aviso de conversaciones.
- **Persona con Bandeja y sin Reservas.** No recibe el aviso de reservas.
- **Pestaña oculta.** No relee por sondeo. Sí suena, porque es cuando más falta hace: el sonido solo calla con la conversación abierta y a la vista (3.2). Al volver, relee lo que tenga más de 15 s.
- **Fuente que nunca termina de leerse.** La lista deja de preguntar a los 10 minutos y la fila sigue diciendo «Leyendo».
- **La ausencia se diseña (§V).** Sin Bandeja, no hay sonido, contador ni título con número. Sin línea en vivo, la consola sondea como hoy y no se pinta nada apagado.

## Requisitos *(obligatorio)*

### Requisito 1 — La agenda al día

**Historia de usuario:** Como persona del negocio, quiero que la agenda enseñe lo que de verdad hay, para no reservar dos veces ni llamar a quien ya canceló.

#### Criterios de aceptación

1. WHEN la persona crea, mueve, cancela o cambia el estado de una reserva desde la consola, y la API lo confirma, THEN la agenda abierta (día, semana, mes o lista) DEBE enseñar el cambio sin recargar, en menos de 2 s.
2. La ficha abierta de una reserva y la agenda DEBEN leer de la misma fuente: un cambio que se ve en una se ve en la otra.
3. WHILE se guarda un cambio de estado desde la ficha, sus botones de acción DEBEN estar ocupados, y un segundo clic NO DEBE mandar otra orden.
4. WHEN el agente, la lista de espera, los automatismos u otra persona crean, mueven, cancelan o cambian el estado de una reserva, THEN el sistema DEBE emitir el aviso `reservations.changed` por la línea en vivo del negocio.
5. El aviso DEBE salir solo después de que el cambio esté confirmado en la base. IF la transacción se deshace THEN NO DEBE salir.
6. El aviso NO DEBE llevar datos de la reserva ni del cliente final.
7. WHEN llega el aviso, THEN la agenda y la ficha abiertas DEBEN releer en menos de 5 s. Una ráfaga de avisos DEBE ser una sola relectura.
8. WHILE la pestaña está visible, la agenda DEBE seguir releyendo cada 45 s, y DEBE decir que puede no estar al día si pasan 150 s sin una lectura nueva (spec 064, 2.6 a 2.9).
9. WHEN la pestaña vuelve a estar visible, o vuelve la conexión, THEN la agenda DEBE releer si su lectura tiene más de 15 s.
10. IF una relectura falla en parte THEN la agenda DEBE conservar la última lectura completa y decirlo (spec 064, 2.9).
11. WHERE la persona tiene Reservas y no Bandeja, la línea en vivo DEBE abrirse y llevarle solo el aviso de reservas.

### Requisito 2 — El conocimiento del agente al día

**Historia de usuario:** Como quien configura un agente, quiero ver al momento lo que le enseño, para saber que lo sabe.

#### Criterios de aceptación

1. WHEN se sube un archivo, se añade una web, se quita, se restaura o se enseña una fuente, THEN la lista DEBE enseñarlo sin recargar.
2. «Qué sabe» DEBE leer de la misma fuente que la lista y DEBE contar solo las fuentes vivas, no las quitadas.
3. WHEN se añade, quita o restaura una fuente, THEN el resto de la pantalla del agente DEBE volver a leerse, como ya pasa al enseñar.
4. WHILE alguna fuente está en «Leyendo» y la pestaña está visible, la lista DEBE releerse cada 5 s, y DEBE parar a los 10 minutos.
5. IF la subida de un archivo no responde en 120 s, o el alta de una web en 60 s, THEN la consola DEBE cortarla, decir que no respondió a tiempo y releer la lista.

### Requisito 3 — La Bandeja avisa y se pone al día

**Historia de usuario:** Como persona del negocio, quiero enterarme de cada mensaje esté donde esté en la consola, para contestar a tiempo.

#### Criterios de aceptación

1. WHEN entra un mensaje de un cliente final (`message.new` con dirección entrante) THEN la consola DEBE sonar un aviso breve, en cualquier pantalla. NO DEBE sonar por los mensajes que salen.
2. IF la persona tiene esa misma conversación abierta y la pestaña visible THEN NO DEBE sonar.
3. Una ráfaga de mensajes DEBE sonar una sola vez cada 3 s como mucho.
4. La persona DEBE poder apagar y encender el sonido en los ajustes de la Bandeja. El ajuste DEBE guardarse en ese navegador, y por defecto está encendido.
5. IF el navegador no deja sonar todavía (política de reproducción automática) THEN la consola NO DEBE pintar ningún error, y DEBE sonar desde la primera vez que la persona toque la página.
6. WHILE hay conversaciones sin leer, el título de la pestaña DEBE empezar por «(N) », con «99+» a partir de 100, en cualquier pantalla de la consola. A cero, sin número.
7. WHEN entra un mensaje o cambia una conversación THEN el contador de la barra lateral y el del título DEBEN ponerse al día en menos de 2 s, también fuera de la Bandeja.
8. WHILE la línea en vivo está caída, el contador DEBE releerse cada 60 s, como hoy.
9. WHERE la barra lateral está plegada, el número DEBE verse en la esquina del icono de la Bandeja, con su nombre para lectores de pantalla.
10. WHEN la línea en vivo vuelve tras cortarse THEN la consola DEBE releer la lista, la conversación abierta, el contador y la agenda.
11. La consola DEBE abrir una sola línea en vivo por pestaña, que comparten la Bandeja, el contador y la agenda.
12. La ruta de la línea en vivo DEBE declarar su duración máxima, para que la plataforma la corte limpia y el navegador reconecte.
13. El contador y el número del título DEBEN ir en neutro o en verde, nunca en ámbar (design system: el ámbar es solo para avisos reales).

### Requisito 4 — El resumen del agente no se queda congelado

**Historia de usuario:** Como persona del negocio, quiero que el resumen que veo sea del problema de ahora, para no actuar sobre uno ya cerrado.

#### Criterios de aceptación

1. IF la conversación se resolvió después de su último escalado THEN el detalle NO DEBE traer el resumen.
2. IF el último escalado es anterior al corte desde el que el agente lee el hilo (`context_from`) THEN el detalle NO DEBE traer el resumen.
3. WHEN la conversación vuelve a escalar THEN el detalle DEBE traer el resumen de ese escalado.
4. El sistema NO DEBE llamar al modelo para esto.

### Requisito 5 — Cada contacto se reconoce

**Historia de usuario:** Como persona del negocio, quiero distinguir a mis contactos de un vistazo, para no contestar al equivocado.

#### Criterios de aceptación

1. WHERE el contacto no tiene foto, su avatar DEBE llevar sus iniciales sobre un color elegido por contacto: siempre el mismo para el mismo contacto, en la lista, la conversación y el panel.
2. Cada combinación de color y texto DEBE cumplir el contraste AA (4,5:1) en los temas claro y oscuro, y DEBE salir de los tokens del design system. NO DEBE usar ámbar ni rojo.
3. IF el nombre del contacto no tiene letras (solo un número) THEN su avatar DEBE llevar un icono de persona. NO DEBE salir «·».
4. WHERE el contacto tiene nombre de usuario de WhatsApp, el panel del contacto y la cabecera de la conversación DEBEN enseñarlo como «@usuario».
5. WHEN entra un mensaje con un nombre de perfil distinto del guardado THEN el sistema DEBE actualizar el nombre del contacto, salvo que lo haya escrito una persona del equipo.

### Entidades clave

- **Aviso `reservations.changed`**: un hecho sin datos («algo cambió en Reservas»), del negocio que hizo el cambio. Viaja por el canal en vivo del negocio (`inbox:{tenant_id}`); la línea lo toma del negocio de la sesión.
- **Contacto (`customers`)**: su nombre, su nombre de usuario y, nuevo, en sus preferencias, el último nombre de perfil que mandó WhatsApp y si el nombre lo escribió una persona. Es del negocio por `tenant_id` y la RLS lo alcanza por esa columna. Sin migración.
- **Escalado y resolución (`conversation_events`)**: el resumen sale del último escalado. Se compara con la última resolución y con el corte `context_from` de la conversación.

## Criterios de éxito *(obligatorio)*

- **CE-001**: tras cancelar, mover o cambiar el estado de una reserva, la agenda lo enseña sin recargar en el 100 % de los intentos de la prueba de navegador.
- **CE-002**: una reserva hecha por detrás aparece en la agenda abierta en menos de 5 s, sin esperar al sondeo.
- **CE-003**: una fuente nueva aparece en la lista y en «Qué sabe» sin recargar, y una que se estaba leyendo cambia de estado sola.
- **CE-004**: fuera de la Bandeja, un mensaje entrante sube el contador y el título en menos de 2 s, y suena una vez.
- **CE-005**: tras un corte de la línea, lo que llegó mientras tanto aparece al reconectar, sin recargar.
- **CE-006**: ningún contacto sale como «·», y todos los avatares pasan el contraste AA en los dos temas.
- **CE-007**: ninguna pantalla nueva o tocada tiene hallazgos graves de accesibilidad (axe) y cabe a 360 px y al 200 %.

## Fuera de alcance

- **Pasar toda la Bandeja a React Query.** Su lista y su conversación ya se releen con la línea en vivo. Aquí solo se arregla la reconexión y la línea se comparte. Reescribirla es un riesgo sin valor nuevo.
- **Avisos del sistema operativo (notificaciones del navegador).** Piden permiso y otro diseño; el sonido y el título cubren lo pedido.
- **Fotos de perfil de WhatsApp.** Meta no las da.
- **Regenerar el resumen con el modelo.** Decidido: se oculta, sin gasto.
- **El sonido en la app del teléfono.** La app ya tiene sus avisos push.
- **Otras pantallas con datos que no cambian solos** (ajustes, ficha del negocio): no tienen datos vivos.

## Supuestos

- **El fallo de cancelación de Luis no se reprodujo.** La investigación (`research.md`, R1) probó en un navegador de verdad la cancelación en las vistas de día, semana y lista y por enlace, en desarrollo y en el build de producción, con lecturas solapadas. En todos los casos la agenda se actualizó. También se probó que la API confirma la escritura antes de responder. El requisito 1 se cumple por diseño: una sola fuente de datos que se invalida tras cada escritura y con cada aviso, en lugar de `router.refresh()`. La prueba de navegador queda como regresión.
- **React Query solo en las pantallas con datos vivos**: la agenda y la ficha de Reservas, el conocimiento del agente y los contadores de la Bandeja. La primera pintura sigue saliendo del servidor.
- **La línea en vivo es la de la Bandeja**, como dice el contrato de la app (spec 044, contrato §8): «en la línea SSE que ya existe».
- **El ajuste del sonido es por navegador**, no por persona: no hay dónde guardarlo en la API sin una migración, y es una preferencia del puesto de trabajo.
