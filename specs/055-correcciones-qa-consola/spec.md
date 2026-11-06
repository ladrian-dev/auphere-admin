# Especificación: Correcciones de QA de la consola

**Rama**: `055-correcciones-qa-consola` · **Creada**: 2026-11-05 · **Estado**: Aprobada por el owner el 2026-11-05, con sus decisiones D1 a D11

**Entrada**: siete anotaciones de QA enviadas al owner en dos fotos el 2026-11-05: no se puede entrar con un partner nuevo porque nunca llega el correo de restablecer; se eligió USD y quedó EUR; el modal de servicios no usa la moneda correcta; hacen falta categorías de servicios; qué significa «Señal» en Políticas; las marcas no se actualizan hasta recargar; y, al crear un agente, la recomendación sustituye el texto en vez de añadirse. El owner pidió revisarlas en el código y abordarlas con Spec Kit.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la API de la consola y la consola, que ya existen. No se abre ninguna superficie |
| **Garantías de aislamiento tocadas** | **1**: la categoría vive en una tabla de tenant que ya tiene RLS, y cambiar la moneda solo toca servicios del cliente en contexto. **9, rozada**: un agente solo ve la categoría de los servicios que ofrece. Además, una regla que no está en esa lista: **«recuperar la contraseña» responde igual para cualquier dirección**, y esta spec no puede romperla. Pruebas en el Requisito 8 |
| **Nota de KB que la justifica** | Ninguna: son correcciones de QA, y el porqué completo está en «Origen». Si el owner quiere nota, se añade antes de `/speckit-plan` |
| **Qué se mide** | Nada de modelo, reloj de máquina ni herramienta de pago. Un correo más en Resend cuando se reenvía una invitación, que no gasta saldo del partner |

## Origen

Revisado el 2026-11-05 contra `develop` (`c565d5b4`). **Lo de la tabla está leído en el código y nada reproducido en un navegador**: el owner paró las pruebas de staging el 2026-11-04. Del punto 1 se leyó además, sin cambiar nada, la ficha y la auditoría del partner de QA en el panel de staging.

**Dónde se probó (owner, 2026-11-05):** en el panel de staging, con el partner «Autprod Staging». Las correcciones se hacen y se prueban **en local, con el partner de pruebas**, y se suben a `develop` ya corregidas. «Autprod Staging» no se toca.

| # | Lo que dice QA | Veredicto | Lo que hace el código hoy |
|---|---|---|---|
| 1 | Con un partner nuevo no se entra, porque nunca llega el correo de restablecer | **Fallo real, con el arreglo principal ya en `develop` y sin comprobar** | Crear «Autprod Staging» no envió ninguna invitación: es el caso que dio origen a la spec 052. Esa spec ya hace que el panel invite al crear, pero nadie lo ha comprobado de punta a punta. **Queda otro hueco**: sin aceptar la invitación no hay cuenta, así que «Recuperar» no envía nada y la pantalla dice «Mira tu correo» |
| 2 | Se eligió USD y quedó EUR | **Fallo confirmado** | «Más ajustes» tiene un solo campo, «Moneda», que es la moneda del **saldo en Auphere**. La moneda de los **precios** es otra y se deduce del país sin enseñarla. Se elige USD, se crea el cliente, y Datos básicos enseña EUR |
| 3 | El modal de servicios no usa la moneda correcta | **Fallo confirmado, con tres causas** | a) Es la consecuencia del punto 2. b) Sin moneda deducida y sin mercado, cae a **CLP**, y un cliente nuevo no lleva mercado. c) Cada servicio guarda la moneda con la que nació: si luego cambia la del negocio, la fila dice EUR, el modal dice «Importe en USD» y al guardar sigue en EUR. La fila, además, calcula los decimales con la moneda del negocio y no con la suya |
| 4 | Hacen falta categorías de servicios | **Función nueva** | Ningún servicio tiene categoría, ni en la ficha ni en Reservas ni en lo que lee el agente |
| 5 | Qué significa «Señal» en Políticas | **Texto poco claro** | La etiqueta es «Señal» (inglés: *Deposit*), sin ninguna explicación. Es el pago por adelantado para reservar, y fuera de España se dice «anticipo» o «abono» |
| 6 | Las marcas no se actualizan hasta recargar | **Fallo confirmado** | El índice lateral de Negocio pinta su marca con los datos de la carga inicial. Solo Sedes y Redes le avisan al guardar. **Datos básicos, Horarios, Servicios, Políticas y Preguntas frecuentes no**. «Es correcto» tampoco. Recargar lo arregla porque vuelve a leer |
| 7 | Al crear un agente, la recomendación sustituye el texto | **Comportamiento aprobado que QA pide cambiar** | Pulsar un ejemplo sustituye la descripción. Lo escribió así el prototipo aprobado (`agente.md` §3.1) y hoy borra lo escrito sin avisar. Hay que corregir también el prototipo |

**Lo que se comprobó del punto 1 en staging:**

- **El 3 de noviembre:** el partner se creó a las 18:56 sin invitación. La persona se unió como propietaria a las 19:25, después de que se le enviara una a mano a las 19:23 (la hora del envío sale de la spec 052).
- **Por qué no salió:** el formulario de entonces no invitaba. El arreglo es de la spec 052.
- **Hoy:** el panel de staging ya pide «Correo del propietario». En su lista de partners, «Autprod Staging» es el más reciente, así que **no se ha creado ninguno con el arreglo puesto**. La spec 052 dejó esa prueba de punta a punta para hacerla tras fusionar (su CE-001).
- **Producción:** la spec 052 no está en `main`, así que allí crear un partner sigue sin enviar nada.
- **Con cuenta, «Recuperar» funciona:** los registros muestran que a esa dirección le salió el correo de restablecer el 3 de noviembre a las 20:31 UTC, y que el cambio de contraseña se completó 28 segundos después, ya unida como propietaria. Lo que no funciona es pedirlo antes de tener cuenta, que no deja rastro con su dirección en los registros.

**Encontrado de paso, y entra porque es la misma queja:**

- En Datos básicos, la moneda de los precios y el país se escriben a mano en un campo libre. Un código inválido solo da un error genérico.
- En el modal de servicios de Reservas, el ejemplo «15000» y el error «solo con números, como 15000» están fijos, y no valen para una moneda con decimales.

## Decisiones

Las preguntas que haría `/speckit-clarify` se resuelven aquí, y el owner las aprobó con la spec el 2026-11-05. D1, D3 y D5 son las que más cambian el resultado.

| # | Pregunta | Decisión propuesta | Por qué |
|---|---|---|---|
| D1 | ¿Qué enseña «Más ajustes» al crear un cliente? | **Dos campos con su nombre completo**: «Moneda de los precios» (la lista completa, con lo deducido ya elegido) y «Moneda del saldo en Auphere» (EUR o USD). **Sustituye la revisión del 2026-10-28**, que dejó solo la del saldo | Quien crea un cliente piensa en sus precios. Un campo «Moneda» a secas es lo que causó el punto 2. Quitar el del saldo sería decidir sobre cobros en una corrección de QA |
| D2 | ¿Y si no se sabe la moneda de los precios? | **No se inventa.** Un cliente sin moneda de precios y sin mercado no cae a CLP: al poner un importe, el modal pide elegirla ahí mismo | Enseñar pesos chilenos a alguien de otro país es el fallo que vio QA. Los clientes con mercado guardado no cambian |
| D3 | ¿Qué pasa con los servicios al cambiar la moneda de los precios? | **Siguen a la moneda del negocio, con el mismo número y sin convertir**: 15,50 EUR pasa a 15,50 USD. Antes se pide confirmación diciendo cuántos servicios con precio cambian. Las reservas ya hechas conservan su moneda | Una moneda por negocio es lo que ya promete la ficha. Convertir exigiría un tipo de cambio y un precio que nadie ha decidido. Quien cambia de moneda revisa sus precios |
| D4 | ¿Cómo se arregla el punto 1 sin revelar qué direcciones existen? | **Con la misma respuesta de siempre.** Si la dirección no tiene cuenta pero sí una invitación viva, sale **la invitación** de nuevo con un enlace nuevo, no el correo de restablecer. El enlace anterior deja de valer, como en la D5 de la 052 | No hay contraseña que restablecer. La persona solo quiere entrar, y la invitación es lo que la deja hacerlo. Por fuera no se distingue |
| D5 | ¿Cómo son las categorías? | **Un solo nivel, opcional y escrito por el partner**: «Corte» agrupa los servicios «Básico» y «Heavy». Se elige una existente o se crea al vuelo. No son variantes de un mismo servicio: cada uno sigue teniendo su duración y su precio | Es lo que pide el ejemplo de QA y no cambia cómo se reserva. Las variantes tocarían la agenda y las reservas |
| D6 | ¿En qué orden salen? | **Por orden alfabético, con «Sin categoría» al final.** Sin ninguna categoría, la lista se ve como hoy | Ordenar a mano es otra función, y nadie la ha pedido |
| D7 | ¿Qué hace el agente con la categoría? | **La lee como dato**, agrupando sus servicios. Si preguntan por «un corte», puede ofrecer los que hay en esa categoría. Va como el nombre del servicio: nunca como instrucción | Si no la lee, la categoría solo sirve en la consola |
| D8 | ¿Qué se hace con «Señal»? | **Etiqueta «Señal o anticipo»**, con una línea de ayuda: «Lo que el cliente paga por adelantado para reservar.» En inglés, «Deposit» más su ayuda. También en lo que lee el agente | Se entiende en España y en Latinoamérica, y no cambia ningún dato guardado |
| D9 | ¿Cómo se añade un ejemplo al texto? | **Con la descripción vacía, la rellena. Con texto, lo añade debajo, en un párrafo aparte.** El nombre sigue poniéndose solo si está vacío. Pulsar otra vez el mismo no lo repite. **Si no cabe, no se recorta nada**: se dice que no cabe | Es lo que pide QA, y borrar lo escrito es el peor resultado posible |
| D10 | ¿Y las marcas? | **Se actualizan al guardar, y también con «Es correcto»**, en las cinco secciones. Sin recargar | Es el comportamiento que ya tienen Sedes y Redes |
| D11 | ¿Y los campos libres de Datos básicos? | **Listas**: de monedas y de países, las mismas del alta | Un campo libre es la forma más fácil de equivocarse de moneda |

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Quien fue invitado puede entrar aunque pida «recuperar» (Prioridad: P1)

Una operadora crea un partner y su propietaria recibe la invitación, pero no la abre o la pierde. Días después intenta entrar, no puede, y pulsa «He olvidado mi contraseña». Le llega de nuevo la invitación, con un enlace nuevo, elige su contraseña y entra.

**Por qué esta prioridad**: hoy esa persona se queda fuera, y la pantalla le dice que mire un correo que nunca llega. Es lo primero que vive un partner nuevo.

**Prueba independiente**: en local, donde el correo se registra en vez de enviarse, crear un partner desde el panel y abrir el enlace registrado. Después, con otra invitación sin aceptar, pedir recuperar con esa dirección: se registra la invitación, el enlace nuevo funciona y el anterior ya no. El correo real se comprueba en staging (C1).

**Escenarios de aceptación**:

1. **Dado** el formulario del panel, **cuando** se crea un partner, **entonces** su propietario recibe la invitación sin ninguna otra acción y puede registrarse.
2. **Dado** una dirección sin cuenta y con una invitación viva, **cuando** pide recuperar, **entonces** recibe la invitación con un enlace nuevo y su enlace anterior deja de valer.
3. **Dado** una dirección con cuenta, **cuando** pide recuperar, **entonces** recibe el correo de restablecer, como hoy.
4. **Dado** una dirección sin cuenta y sin invitación viva, **cuando** pide recuperar, **entonces** no sale ningún correo.
5. **Dado** cualquiera de los tres últimos casos, **cuando** se mira la respuesta, **entonces** es la misma, y no tarda más en uno que en otro.

---

### Historia 2 — La moneda elegida es la que se usa (Prioridad: P1)

Un partner crea un cliente y, en «Más ajustes», ve la moneda de los precios y la del saldo, cada una con su nombre. Elige USD para los precios. En Datos básicos sale USD, y el modal de servicios pide el importe en USD. Si más tarde la cambia, le avisan de cuántos servicios cambian, y todos quedan en la moneda nueva.

**Por qué esta prioridad**: un precio en la moneda equivocada es lo que el agente le dirá a un cliente final. Son los puntos 2 y 3.

**Prueba independiente**: crear un cliente eligiendo USD como moneda de los precios, con un navegador de la zona euro. Datos básicos, los dos modales de servicios y lo que responde el agente dicen USD.

**Escenarios de aceptación**:

1. **Dado** «Más ajustes» abierto, **cuando** se mira la moneda, **entonces** aparecen dos campos con su nombre completo, y el de los precios trae lo deducido ya elegido.
2. **Dado** un cliente creado con USD en los precios, **cuando** se abre Datos básicos o cualquier modal de servicios, **entonces** dicen USD.
3. **Dado** un cliente con USD en los precios y EUR en el saldo, **cuando** se abre Consumo, **entonces** el saldo no cambia por ello.
4. **Dado** un cliente sin moneda de precios ni mercado, **cuando** se pone un importe en un servicio, **entonces** se pide elegir la moneda y no se usa ninguna por su cuenta.
5. **Dado** un negocio con tres servicios con precio, **cuando** se cambia la moneda de los precios, **entonces** se avisa de que cambian tres y, al confirmar, quedan con el mismo número en la moneda nueva.
6. **Dado** ese aviso, **cuando** se cancela, **entonces** no cambia nada.
7. **Dado** una moneda sin decimales y otra con ellos, **cuando** se cambia de una a otra, **entonces** el número que se ve es el mismo: 15.000 CLP pasa a 15.000,00 USD.
8. **Dado** reservas ya hechas, **cuando** cambia la moneda, **entonces** conservan la suya.

---

### Historia 3 — La marca cambia al guardar (Prioridad: P1)

Un partner completa Horarios y pulsa «Guardar horario». La marca del índice lateral aparece en ese momento, igual que después de recargar.

**Por qué esta prioridad**: quien configura un cliente cree que no se ha guardado y lo repite. Es el punto 6, y se arregla en poco.

**Prueba independiente**: en Negocio, guardar cada sección y comprobar la marca sin recargar.

**Escenarios de aceptación**:

1. **Dado** una sección pendiente de las cinco, **cuando** se guarda y queda completa, **entonces** su marca del índice cambia sin recargar.
2. **Dado** una sección leída de la web, **cuando** se pulsa «Es correcto», **entonces** su marca cambia sin recargar.
3. **Dado** un servicio añadido o una política aceptada desde lo sugerido, **cuando** termina, **entonces** su marca cambia sin recargar.
4. **Dado** cualquiera de esos casos, **cuando** se recarga, **entonces** la marca es la misma.
5. **Dado** un guardado que falla, **cuando** termina, **entonces** la marca no cambia.

---

### Historia 4 — Un ejemplo no borra lo escrito (Prioridad: P1)

Un partner escribe qué tiene que hacer su agente y pulsa «Recepción y citas» para ver qué más puede pedirle. El ejemplo aparece debajo de su texto.

**Por qué esta prioridad**: hoy pierde lo escrito sin aviso y sin deshacer.

**Prueba independiente**: en «Nuevo agente», escribir algo, pulsar un ejemplo y comprobar que están los dos textos.

**Escenarios de aceptación**:

1. **Dado** una descripción vacía, **cuando** se pulsa un ejemplo, **entonces** se rellena con él.
2. **Dado** una descripción con texto, **cuando** se pulsa un ejemplo, **entonces** se añade debajo, en un párrafo aparte, y lo escrito sigue igual.
3. **Dado** un ejemplo ya añadido, **cuando** se pulsa otra vez, **entonces** no se repite.
4. **Dado** un texto al que no le cabe el ejemplo, **cuando** se pulsa, **entonces** el texto no cambia y se dice que no cabe.
5. **Dado** un nombre ya escrito, **cuando** se pulsa un ejemplo, **entonces** el nombre no cambia.

---

### Historia 5 — «Señal» se entiende (Prioridad: P2)

Un partner abre Políticas y ve «Señal o anticipo», con una línea que explica qué es.

**Por qué esta prioridad**: no bloquea nada, pero quien no la entiende la deja vacía, y el agente no sabrá contestar.

**Prueba independiente**: abrir Políticas en los dos idiomas, en lectura y en edición.

**Escenarios de aceptación**:

1. **Dado** Políticas, en lectura o en edición, **cuando** se mira ese campo, **entonces** se lee la etiqueta nueva y su ayuda, en el idioma de la consola.
2. **Dado** una señal ya escrita, **cuando** se abre, **entonces** el valor sigue igual.
3. **Dado** un agente con señal escrita, **cuando** le preguntan por el anticipo o por la señal, **entonces** responde con ese texto.

---

### Historia 6 — Los servicios se agrupan por categoría (Prioridad: P2)

Una barbería tiene muchos servicios. Crea la categoría «Corte» y mete en ella «Básico» y «Heavy». Los ve agrupados en la ficha y en Reservas. Cuando un cliente pregunta por un corte, el agente le ofrece esos dos.

**Por qué esta prioridad**: es función nueva y lo más grande de esta spec, y las demás historias no dependen de ella. Va en su propia iteración.

**Prueba independiente**: crear dos servicios en una categoría y uno sin ella. Se ven agrupados en la ficha y en Reservas, y el agente responde con los de esa categoría.

**Escenarios de aceptación**:

1. **Dado** el modal de servicio, en la ficha o en Reservas, **cuando** se escribe una categoría, **entonces** se puede elegir una existente o crear una nueva.
2. **Dado** servicios con y sin categoría, **cuando** se ve la lista, **entonces** salen agrupados por orden alfabético, con «Sin categoría» al final.
3. **Dado** un negocio sin ninguna categoría, **cuando** se ve la lista, **entonces** se ve como hoy, sin grupos.
4. **Dado** «corte» y «Corte», **cuando** se guardan, **entonces** son la misma categoría.
5. **Dado** el último servicio de una categoría, **cuando** se archiva o se cambia, **entonces** la categoría deja de ofrecerse.
6. **Dado** un agente que ofrece solo algunos servicios, **cuando** lee sus datos, **entonces** ve solo las categorías de esos servicios.
7. **Dado** un servicio con categoría, **cuando** se duplica, **entonces** la copia la conserva.
8. **Dado** un servicio que ya existía, **cuando** se publica esta función, **entonces** sigue igual y sin categoría.

---

### Casos límite

- **Una invitación vencida o revocada**: al pedir recuperar no sale nada, y la respuesta es la misma. El operador ya la ve vencida en Equipo y puede reinvitar (052).
- **Varias invitaciones vivas para una dirección**: se reenvía solo la más reciente.
- **Alguien pide recuperar con la dirección de otra persona, varias veces**: el enlace anterior muere, igual que en un restablecimiento, y el tope de cinco peticiones por dirección es el mismo. Esa persona recibe el correo y su enlace nuevo vale.
- **El envío de la invitación falla**: la respuesta es la misma y el fallo queda en los registros.
- **La moneda cambia con un modal de servicio abierto en otra pestaña**: al guardar salta el conflicto de revisión que ya existe, y no se guarda un precio en la moneda vieja.
- **Un servicio de precio «gratis» o sin precio**: al cambiar la moneda no cambia nada, y no cuenta en el aviso.
- **Datos que ya están mezclados**: servicios en una moneda distinta a la del negocio. No se tocan solos: ver C2.
- **La consola sin Negocio o sin Reservas**: la categoría solo aparece donde ya están los servicios, y no se añade ninguna pantalla.
- **Un ejemplo en una descripción casi llena**: se trata como «no cabe» aunque falten pocos caracteres. Nunca se corta un ejemplo a medias.
- **Categoría muy larga, vacía o solo con espacios**: hasta 40 caracteres, y vacía equivale a sin categoría.

## Requisitos *(obligatorio)*

### Requisito 1 — Entrar con una invitación pendiente

**Historia de usuario:** Como persona invitada que no llegó a aceptar, quiero que «recuperar» me deje entrar, para no quedarme fuera esperando un correo que no llega.

#### Criterios de aceptación

1. WHEN se crea un partner desde el panel THEN el sistema DEBE enviar la invitación a su propietario, como pide la spec 052. Si algo falla, se corrige aquí; si no, este criterio solo se comprueba.
2. WHEN se pide recuperar con una dirección sin cuenta y con una invitación viva a la consola THEN el sistema DEBE enviar esa invitación con un enlace nuevo.
3. WHEN se reenvía así una invitación THEN el sistema DEBE dejar sin valor el enlace anterior, y conservar el partner, el rol y el plazo que le corresponden.
4. IF la dirección no tiene cuenta ni invitación viva THEN el sistema DEBE no enviar nada.
5. WHEN la dirección tiene cuenta THEN el sistema DEBE enviar el correo de restablecer, como hoy, aunque además tenga una invitación.
6. El sistema DEBE contestar lo mismo, sin diferencia de tiempo apreciable, en todos estos casos, y contar la petición contra el mismo tope antes de mirar nada.
7. IF el envío falla THEN el sistema DEBE dejarlo en los registros y no decirlo en la respuesta.
8. WHEN se reenvía una invitación por esta vía THEN el sistema DEBE dejarlo en la auditoría, con el partner que sale de la invitación, nunca de la petición.

### Requisito 2 — Las dos monedas, con su nombre

**Historia de usuario:** Como partner, quiero distinguir la moneda de los precios de la del saldo, para no elegir una creyendo que es la otra.

#### Criterios de aceptación

1. WHEN se abre «Más ajustes» al crear un cliente THEN el sistema DEBE enseñar «Moneda de los precios» y «Moneda del saldo en Auphere», cada una con su ayuda.
2. WHEN hay moneda deducida THEN el sistema DEBE traerla elegida, y lo que la persona elija DEBE ganar a lo deducido.
3. WHEN se crea el cliente THEN el sistema DEBE guardar cada moneda en su sitio, sin que una cambie la otra.
4. WHEN se edita Datos básicos THEN el sistema DEBE ofrecer la moneda de los precios y el país como listas.
5. El resumen de «Más ajustes» DEBE decir la moneda de los precios.

### Requisito 3 — Una sola moneda de precios por negocio

**Historia de usuario:** Como partner, quiero que todos mis servicios estén en la moneda de mi negocio, para no dar un precio equivocado.

#### Criterios de aceptación

1. WHEN se crea o edita un servicio THEN los dos modales DEBEN pedir y guardar el importe en la moneda de los precios del negocio.
2. IF el negocio no tiene moneda de precios ni mercado THEN el sistema DEBE pedir elegirla antes de aceptar un importe, y NO DEBE usar una por defecto.
3. WHEN se cambia la moneda de los precios y hay servicios con importe THEN el sistema DEBE pedir confirmación diciendo cuántos cambian.
4. WHEN se confirma THEN el sistema DEBE pasar esos servicios a la moneda nueva con el mismo número visible, en una sola operación con el cambio de moneda.
5. IF no se confirma o falla THEN el sistema DEBE dejar la moneda y todos los importes como estaban.
6. El sistema NO DEBE cambiar la moneda ni el importe de una reserva ya hecha.
7. WHEN se pinta el importe de un servicio THEN el sistema DEBE calcular sus decimales con la moneda de ese mismo importe.
8. WHERE la moneda de los precios tiene decimales los modales DEBEN aceptarlos, y su ejemplo y su error DEBEN corresponder a esa moneda.
9. WHEN el agente dice un precio THEN el sistema DEBE dárselo en la moneda de ese servicio.

### Requisito 4 — Las marcas al momento

**Historia de usuario:** Como partner, quiero ver el avance al guardar, para saber que ya está sin tener que recargar.

#### Criterios de aceptación

1. WHEN se guarda bien Datos básicos, Horarios, Servicios, Políticas o Preguntas frecuentes THEN el índice DEBE pintar el estado que devuelve la API, sin recargar.
2. WHEN se pulsa «Es correcto» en una sección THEN el índice DEBE cambiar su marca, sin recargar.
3. WHEN se acepta o se descarta algo sugerido y cambia el estado de la sección THEN el índice DEBE reflejarlo.
4. IF el guardado falla THEN el índice DEBE conservar la marca que tenía.
5. El estado que se pinta al momento DEBE ser el mismo que se lee al recargar.

### Requisito 5 — Los ejemplos se añaden

**Historia de usuario:** Como partner, quiero usar un ejemplo sin perder lo que escribí, para aprovechar los dos.

#### Criterios de aceptación

1. IF la descripción está vacía THEN pulsar un ejemplo DEBE rellenarla con él.
2. IF la descripción tiene texto THEN pulsar un ejemplo DEBE añadirlo detrás, en un párrafo aparte, sin cambiar lo escrito.
3. IF ese ejemplo ya está en la descripción THEN pulsarlo NO DEBE repetirlo.
4. IF el resultado supera el máximo THEN el sistema DEBE dejar la descripción como estaba y decir que no cabe, y NO DEBE recortar nada.
5. WHEN se pulsa un ejemplo THEN el sistema DEBE poner su nombre solo si el nombre está vacío.
6. Los textos de la pantalla y el prototipo (`agente.md` §3.1) DEBEN dejar de decir que el ejemplo sustituye.

### Requisito 6 — «Señal» explicada

**Historia de usuario:** Como partner, quiero entender cada política, para rellenarla bien.

#### Criterios de aceptación

1. WHEN se ve la política de señal, en lectura o en edición THEN el sistema DEBE enseñar «Señal o anticipo» (*Deposit*) y su línea de ayuda en el idioma de la consola.
2. El constructor de agentes y lo que lee el agente DEBEN usar la misma etiqueta.
3. El sistema NO DEBE cambiar ni mover ningún valor guardado.

### Requisito 7 — Categorías de servicios

**Historia de usuario:** Como partner, quiero agrupar mis servicios, para encontrarlos y para que el agente los ofrezca ordenados.

#### Criterios de aceptación

1. Un servicio PUEDE tener una categoría, de hasta 40 caracteres, y vacía equivale a ninguna.
2. WHEN se edita un servicio, en la ficha o en Reservas THEN el sistema DEBE ofrecer las categorías que ya usa el negocio y dejar crear una nueva.
3. WHEN dos categorías solo se diferencian en mayúsculas o en espacios de los extremos THEN el sistema DEBE tratarlas como una, con la primera forma guardada.
4. WHERE hay alguna categoría las listas de servicios DEBEN agruparse por orden alfabético, con «Sin categoría» al final; y WHERE no hay ninguna DEBEN verse como hoy.
5. WHEN se lee un servicio por la API, se duplica o se exporta la ficha THEN el sistema DEBE conservar su categoría.
6. WHEN se compila lo que sabe un agente THEN el sistema DEBE incluir la categoría junto a cada servicio que ofrece, como dato.
7. Los servicios que ya existen DEBEN seguir igual, sin categoría y sin cambiar sus reservas.

### Requisito 8 — Aislamiento y seguridad

**Historia de usuario:** Como Auphere, quiero que estas correcciones no abran ninguna puerta, para seguir cumpliendo las garantías.

#### Criterios de aceptación

1. Un test DEBE comprobar que «recuperar» contesta lo mismo con cuenta, con invitación viva, con invitación vencida, sin nada y pasado el tope.
2. Un test de `tests/isolation/` DEBE comprobar que cambiar la moneda de un cliente no toca los servicios de otro.
3. Un test de `tests/isolation/` DEBE comprobar que un cliente no ve ni recibe como sugerencia las categorías de otro.
4. Un test DEBE comprobar que un agente con lista de servicios no ve las categorías de los servicios que no ofrece.
5. Un test DEBE comprobar que una categoría con forma de instrucción llega al agente como dato.
6. WHEN se cambia la moneda de los precios THEN el sistema DEBE dejarlo en la auditoría, con cuántos servicios cambiaron.

### Entidades clave

- **Servicio** (ya existe, de tenant, RLS por `tenant_id`): gana una categoría opcional. Su moneda pasa a seguir siempre a la del negocio.
- **Categoría**: no es una entidad aparte, sino un texto del servicio. Las existentes se deducen de los servicios vivos del cliente.
- **Perfil del negocio** (ya existe, de tenant): su moneda de los precios puede estar vacía, y entonces no se inventa.
- **Invitación** (ya existe, de plataforma, con su partner): se puede volver a emitir desde «recuperar». No cambia de forma.

## Criterios de éxito *(obligatorio)*

- **CE-001**: quien tiene una invitación viva y pide recuperar entra en la consola sin ayuda de un operador.
- **CE-002**: en los cinco sitios donde se ve la moneda de un cliente nuevo (el resumen del alta, Datos básicos, los dos modales y lo que dice el agente) se lee la que se eligió, en el 100 % de los casos probados.
- **CE-003**: tras esta spec, ningún cliente nuevo queda con precios en una moneda que nadie eligió ni se dedujo.
- **CE-004**: las cinco secciones actualizan su marca sin recargar, y coincide con la que se ve al recargar.
- **CE-005**: pulsar un ejemplo no borra nunca lo escrito.
- **CE-006**: quien lee la política de señal entiende qué es sin preguntar: se comprueba con quien hizo este QA.
- **CE-007**: un negocio con diez servicios o más los ve agrupados en la ficha y en Reservas, y el agente ofrece los de una categoría cuando se los piden.
- **CE-008**: el aislamiento y «recuperar» siguen sin distinguir nada: los tests del Requisito 8 pasan.

## Condiciones de salida *(lo que no es código)*

- **C1**: al subir a `develop`, crear en staging un partner de prueba desde el panel, con una dirección que dé el owner, y comprobar que el correo llega y que se puede registrar. Crea un partner y envía un correo real, así que se hace con su autorización. Es el CE-001 de la spec 052, que sigue pendiente.
- **C2**: contar, solo con lectura, cuántos servicios están en una moneda distinta a la de su negocio. Con ese número, el owner decide si se corrigen y cómo. No se tocan datos sin su visto bueno. En producción, el script lo corre el owner.
- **C3**: en producción, la invitación al crear un partner no existe hasta promover la spec 052. La promoción la hace el owner.
- **C4**: tras probar en local, repasar en staging lo que dependa del entorno real, cuando el owner lo autorice, sin tocar Meta Review Demo ni Jemma's Hair.
- **C5**: revisar `/cso` para el Requisito 1, que toca una ruta que acepta la dirección de cualquiera.

## Fuera de alcance

- **Convertir precios con un tipo de cambio**: decidir un precio nuevo es del negocio.
- **Varias monedas de precios en un mismo negocio**: la ficha promete una.
- **Variantes de un servicio y subcategorías**: tocarían la agenda y las reservas.
- **Ordenar las categorías a mano**: nadie lo ha pedido.
- **Quitar o cambiar la moneda del saldo**: es una decisión de cobros (spec 027 y 047).
- **Que el alta autónoma duplique partners**: es otro problema, ya anotado.
- **Que «Generar borrador» falle en staging**: es otro fallo, ya anotado, y no se resuelve aquí aunque sea en la misma pantalla que el punto 7.
- **Las categorías en la app móvil**: la app sigue funcionando sin enseñarlas.
- **Que sean fiables los envíos en general**: es la spec 054.

## Supuestos

- La «recomendación» del punto 7 son los cuatro ejemplos de «Nuevo agente», los únicos que escriben en esa descripción. Elegir una plantilla no la cambia.
- La «check» del punto 6 es la marca del índice lateral de Negocio, porque el ejemplo que da QA (el horario) es el que se comporta así. Dentro de la tarjeta ya se actualiza.
- «Heavy» en el punto 4 es una lectura de la letra de la foto, y es solo un ejemplo: no cambia nada.
- «Politics» en el punto 5 es «Políticas», y «Señal» es el pago por adelantado de la política de ese nombre.
- Un cliente con mercado guardado conserva la moneda de ese mercado si no tiene moneda de precios.
- La consola del cliente (lite) comparte la sección de servicios y recibe la moneda y los grupos, pero no edita la categoría: conserva la que hay. Corregido al planificar, porque su API de servicios es otra.
