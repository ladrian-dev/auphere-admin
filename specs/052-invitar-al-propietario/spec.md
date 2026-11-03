# Especificación: Invitar al propietario

**Rama**: `052-invitar-al-propietario` · **Creada**: 2026-11-03 · **Estado**: Borrador, pendiente de aprobación

**Entrada**: descripción del usuario: «comunmente los crearemos nosotros desde el admin panel asi que ese correo deberia llegar». Parte como requisito de que crear un partner desde el panel hace llegar el correo a su propietario, y deja resuelto a qué dirección va, cómo se reenvía o revoca y qué ve el operador si el envío falla.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la API y el panel de operador, que ya existen. No se abre ninguna superficie: la invitación, su enlace y su aceptación ya existen; lo nuevo es que también las emite un operador |
| **Garantías de aislamiento tocadas** | **6**: el registro de cada correo lleva el partner al que pertenece. **1, solo rozada**: no se lee ni se escribe ninguna tabla de tenant; partners, personas, invitaciones y cuentas de consola son de plataforma, y el partner sale de la ruta. La misma regla, un nivel más arriba, separa a un partner de otro: se prueba en `tests/isolation/` (Requisito 7) |
| **Nota de KB que la justifica** | `[[research/2026-11-03-invitar-al-propietario]]` |
| **Qué se mide** | Nada de modelo, reloj de máquina ni herramienta de pago. Cada invitación es un correo más en Resend y no gasta saldo del partner |

## Origen

Medido el 2026-11-03 contra `develop` (`4c11bb83`) y staging:

- **Crear un partner desde el panel no envía nada.** Solo escribe el partner y su auditoría. En staging, un partner creado a las 18:56 UTC no recibió nada hasta que Luis envió la invitación a mano a las 19:23. La plantilla funciona: esa invitación se entregó y se aceptó.
- **La pantalla promete lo que no ocurre.** La pestaña Equipo es de solo lectura y su estado vacío dice «Cuando el partner acepte su invitación aparecerá aquí», sin que exista ninguna invitación. El aviso tras crear manda a generar una clave de API, y nada indica que falta invitar a nadie.
- **El operador no tiene cómo invitar.** Su única vía es `seed_console_memberships.py`, que pide acceso a la VPC.
- **La consola nace apagada.** Un partner del panel nace con la consola apagada y uno del alta autónoma, encendida. Quien aceptara una invitación del primero entraría a una pantalla de «sin acceso».
- **El campo de contacto no sirve para esto.** `contact_email` es opcional y su texto promete «avisos de rotación de keys», que no existen en el código. Hoy solo es el repliegue del correo de facturación y un dato que se muestra.
- **Un fallo de envío se calla solo.** El envío nunca lanza: devuelve si el proveedor aceptó el correo. Si nadie mira ese resultado, un fallo pasa por un envío.
- **Una invitación vencida parece viva.** Sigue pendiente hasta que alguien abre su enlace, porque ningún proceso la marca. La pestaña Equipo la enseña bajo «Invitaciones pendientes», y reinvitar a esa dirección choca con ella.

## Decisiones

| # | Pregunta | Decisión | De quién |
|---|---|---|---|
| D1 | ¿La invitación sale al crear o con una acción aparte? | **Al crear.** La acción aparte solo cubre lo que crear no cubre: partners que ya existen y una invitación revocada o vencida | Luis, 2026-11-03 |
| D2 | ¿A qué dirección va? | **A un campo obligatorio, «Correo del propietario»**, que sustituye al contacto opcional del formulario de alta. Esa dirección queda también como `contact_email`. No se piden dos correos cuando el operador solo conoce uno, y el de contacto solo es el repliegue de facturación, que al propietario le corresponde | Propuesta |
| D3 | ¿Se usa el `contact_email` de un partner existente? | **Solo como sugerencia editable.** Nunca se le envía nada sin que el operador pulse: ser el contacto de un partner no da derecho a ser su dueño | Propuesta |
| D4 | ¿Y la consola, que nace apagada? | **Nace encendida** con sus vistas por defecto, como en el alta autónoma. Si no, el correo llevaría a una pantalla de «sin acceso». Se cambia luego en Módulos | Propuesta |
| D5 | ¿Cómo se reenvía? | **Un enlace nuevo para la misma dirección**, con el plazo completo. El anterior deja de servir, porque solo se guarda el hash del token y no se puede volver a enviar el mismo | Propuesta |
| D6 | ¿Cómo se revoca? | **Con confirmación.** El enlace deja de servir al momento y a la persona no se le avisa. Revocar es también la forma de corregir una dirección | Propuesta |
| D7 | ¿Qué ve el operador si el envío falla? | **Una vista que no desaparece**: el partner y la invitación existen, el correo no salió, y ahí tiene el enlace para pasarlo a mano y la acción de reintentar. Tras recargar, la ficha sigue diciendo que no consta el envío | Propuesta |
| D8 | ¿Y un partner que ya tiene propietario? | **No se invita desde el panel.** Desde ese momento el equipo es del partner. Añadir otro dueño o traspasar la propiedad queda fuera | Propuesta |

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Crear el partner hace llegar el correo (Prioridad: P1)

Una operadora da de alta un partner: escribe el nombre, el identificador y el correo de quien va a ser su propietario. Al pulsar «Crear partner» el partner nace con la consola encendida y esa persona recibe la invitación. La operadora ve que se envió, a qué dirección y hasta cuándo vale. La persona abre el correo, elige su contraseña y entra en su consola como propietaria, sin que nadie haga nada más.

**Por qué esta prioridad**: es la forma habitual de dar de alta un partner, y hoy termina en silencio. Es el motivo de esta spec.

**Prueba independiente**: en staging, crear un partner desde el panel con una dirección de prueba. Sin ninguna otra acción, el correo llega, el enlace abre, se acepta y la persona entra en la consola con el rol de propietaria.

**Escenarios de aceptación**:

1. **Dado** el formulario de alta, **cuando** el correo del propietario está vacío o no tiene forma de correo, **entonces** no se puede crear el partner y el campo dice por qué.
2. **Dado** un formulario válido, **cuando** la operadora crea el partner, **entonces** nacen el partner con la consola encendida y la invitación de propietario, y sale el correo.
3. **Dado** que el correo salió, **cuando** termina la creación, **entonces** la operadora ve el partner creado, la dirección invitada, hasta cuándo vale la invitación y el enlace, por si el correo no llega.
4. **Dado** el correo recibido, **cuando** la persona acepta, **entonces** entra en la consola del partner con el rol de propietaria, y la pestaña Equipo la muestra como persona activa.
5. **Dado** un identificador ya usado, **cuando** la operadora crea el partner, **entonces** no se crea nada ni sale ningún correo.
6. **Dado** un correo que ya es de una persona de otro partner o de un cliente, **cuando** la operadora crea el partner, **entonces** no se crea nada ni sale ningún correo, y el campo dice que esa dirección ya tiene su propia consola.

---

### Historia 2 — Si el correo no sale, el operador lo sabe y puede resolverlo (Prioridad: P1)

El proveedor de correo falla justo en el alta. El partner y la invitación ya existen y no se deshacen. La operadora ve, en una vista que no se va sola, que el correo no salió. Ahí mismo tiene el enlace para copiarlo y pasárselo a la persona por otro medio, y un botón para reintentar. Si se va y vuelve otro día, o si entra otra operadora, la ficha del partner sigue diciendo que no consta que el correo saliera.

**Por qué esta prioridad**: hoy el silencio ya ha costado un alta. Un correo que falla sin que nadie lo sepa deja a un cliente esperando un enlace que no va a llegar.

**Prueba independiente**: con el proveedor rechazando los envíos, crear un partner. Se ve el fallo y el enlace. Ese enlace funciona. Al recargar, la pestaña Equipo dice que no consta el envío, y reintentar con el proveedor ya sano lo deja como enviado.

**Escenarios de aceptación**:

1. **Dado** un proveedor que rechaza el correo o no responde, **cuando** se crea el partner, **entonces** el partner y la invitación quedan creados, y la vista de resultado dice que el correo no salió y muestra el enlace completo y copiable.
2. **Dado** esa vista, **cuando** pasa el tiempo, **entonces** el aviso sigue ahí hasta que la operadora se va: no es un mensaje que desaparezca solo.
3. **Dado** esa vista, **cuando** la operadora reintenta, **entonces** recibe un resultado nuevo, y el enlace anterior deja de servir y se sustituye en pantalla por el nuevo.
4. **Dado** que la operadora salió sin resolverlo, **cuando** cualquier operador abre la ficha, **entonces** ve que no consta el envío, y en Equipo puede reenviar o revocar.
5. **Dado** un entorno sin proveedor configurado, **cuando** se crea el partner, **entonces** ocurre lo mismo que con un proveedor que falla, y el partner se crea igual.

---

### Historia 3 — Reenviar, revocar y corregir la dirección (Prioridad: P2)

La persona dice que no le llegó, o la operadora se da cuenta de que escribió mal la dirección. En la pestaña Equipo ve la invitación con su estado y dos acciones. **Reenviar** manda un enlace nuevo a la misma dirección. **Revocar**, con confirmación, mata el enlace y deja invitar a otra dirección.

**Por qué esta prioridad**: sin esto, cualquier error de dirección vuelve a pedir la VPC. Va después de la Historia 1 porque el alta ya funciona sin esto cuando la dirección es correcta.

**Prueba independiente**: sobre una invitación pendiente, reenviar y comprobar que el enlace viejo da «no encontrado» y el nuevo abre. Revocar y comprobar que ninguno abre. Invitar a otra dirección y comprobar que el contacto del partner cambia con ella.

**Escenarios de aceptación**:

1. **Dado** una invitación pendiente, **cuando** la operadora reenvía, **entonces** sale un enlace nuevo con el plazo completo, el anterior deja de servir y ve el mismo resultado que al crear.
2. **Dado** una invitación pendiente, **cuando** la operadora revoca y confirma, **entonces** el enlace deja de servir y la pestaña vuelve a ofrecer invitar.
3. **Dado** una invitación revocada por una dirección mal escrita, **cuando** la operadora invita a la correcta, **entonces** la invitación va a la nueva y el contacto del partner, si era la dirección anterior, pasa a la nueva.
4. **Dado** una invitación vencida, **cuando** la operadora abre Equipo, **entonces** la ve como caducada, con la fecha, y el formulario de invitar ofrece esa dirección para volver a enviarla.
5. **Dado** que la persona aceptó justo antes, **cuando** la operadora reenvía o revoca, **entonces** se le dice que ya aceptó y la pestaña se actualiza, sin tocar a la persona.

---

### Historia 4 — Los partners que ya existen sin propietario (Prioridad: P2)

Hay partners creados antes de esta spec, que nunca invitaron a nadie, y partners cuya invitación se revocó o venció. En su pestaña Equipo la operadora ve que no tienen propietario y un formulario para invitarlo, con el correo de contacto sugerido si lo hay. No sale nada hasta que pulsa.

**Por qué esta prioridad**: cierra el hueco para lo que ya existe y es la acción que usan las Historias 2 y 3. Crear partners nuevos no depende de esto.

**Prueba independiente**: sobre un partner existente sin personas, invitar desde Equipo: el correo sale y se acepta. Comprobar antes que el despliegue no envió nada a ningún partner existente.

**Escenarios de aceptación**:

1. **Dado** un partner sin propietario activo, sin invitación viva, activo y con la consola encendida, **cuando** la operadora abre Equipo, **entonces** ve el formulario de invitar, con el contacto como sugerencia editable si lo hay.
2. **Dado** ese partner con la consola apagada, **cuando** la operadora abre Equipo, **entonces** no hay formulario: se le dice que encienda la consola, con el enlace a Módulos.
3. **Dado** un partner suspendido, **cuando** la operadora abre Equipo, **entonces** no se puede invitar ni reenviar, y se le dice que está suspendido.
4. **Dado** un partner con propietario activo, **cuando** la operadora abre Equipo, **entonces** ve a sus personas y no se le ofrece invitar.
5. **Dado** el despliegue de esta spec, **cuando** termina, **entonces** ningún partner existente ha recibido ni va a recibir nada por sí solo.

---

### Historia 5 — Todo queda dicho y nada cruza de un partner a otro (Prioridad: P1)

Invitar a alguien como propietario da las llaves de un negocio. Cada acción queda en la auditoría con el nombre del operador, sin el enlace dentro. Una invitación de un partner no se puede tocar por la ruta de otro. Solo un operador identificado llega a estas acciones.

**Por qué esta prioridad**: es lo que hace aceptable que esta acción exista fuera de la VPC.

**Prueba independiente**: la suite de `tests/isolation/`, con las pruebas nuevas en verde, y la auditoría de un alta completa leída en el panel y en la consola.

**Escenarios de aceptación**:

1. **Dado** cualquier acción de esta spec, **cuando** termina, **entonces** la auditoría nombra al operador y el partner y no contiene el enlace ni el token.
2. **Dado** una invitación del partner A, **cuando** alguien la pide o la toca por la ruta del partner B, **entonces** recibe exactamente la misma respuesta que para una invitación que no existe y no cambia nada.
3. **Dado** una petición sin operador identificado, o hecha con credenciales de una consola, de una clave de partner o de un dispositivo, **cuando** llega a estas acciones, **entonces** se rechaza.
4. **Dado** un correo de invitación, enviado o retenido, **cuando** queda en el registro, **entonces** lleva el partner al que pertenece.

---

### Casos límite

- **El proveedor no responde.** La operadora espera como mucho lo que tarda en vencer el plazo de envío y después ve el fallo. El partner ya está creado.
- **Se pierde la respuesta entre el panel y la API.** Puede que el partner se haya creado sin que la operadora lo sepa. Si repite, el identificador ya está usado. En la ficha verá la invitación y que no consta el envío, y desde ahí la reenvía.
- **Dos operadores invitan a la vez al mismo partner.** Solo uno lo consigue. El otro recibe que ya hay una invitación pendiente.
- **Doble pulsación en reenviar.** El último enlace es el que vale y puede llegar más de un correo. El botón queda bloqueado mientras dura la petición, y un reenvío no se deshace.
- **La persona ya tiene cuenta, pero sin ninguna pertenencia** (alguien que dejó un partner). Se puede invitar. Al aceptar, entra con su contraseña de siempre, como ya hace la aceptación: una invitación nunca reescribe credenciales.
- **La persona ya es de este partner con otro rol** y el partner no tiene propietario activo. Se rechaza diciendo que ya es de este equipo. Cambiar su rol queda fuera de esta spec.
- **La persona tiene otra invitación viva en otro partner.** Se permite. Gana la primera que acepte, y la otra le da el error que ya existe hoy.
- **Se apaga la consola con una invitación pendiente.** La invitación no se toca. La pestaña Equipo avisa de que quien acepte verá que no tiene acceso. Reenviar queda bloqueado hasta encenderla, y revocar sigue disponible.
- **Se suspende el partner con una invitación pendiente.** Igual: se avisa, no se puede reenviar y sí revocar.
- **Invitaciones que no son de Auphere** (las que emite el propio partner desde su consola, o las de otro rol que dejó el script). El panel las sigue mostrando como hoy, sin acciones.
- **Aparece un propietario activo con una invitación de Auphere todavía viva.** Se puede revocar, porque reduce el acceso, y no reenviar, porque daría otro enlace de dueño a un partner que ya tiene quien lo gestione.
- **La dirección es muy larga, en mayúsculas o con espacios.** Se recorta y se guarda en minúsculas, como cualquier invitación, y en pantalla se parte sin desbordar en un móvil de 360 px.
- **Sin capacidad disponible (§V).** Con propietario activo no hay formulario ni botón apagado: solo el equipo del partner.

## Requisitos *(obligatorio)*

### Requisito 1 — El alta desde el panel invita al propietario

**Historia de usuario:** Como operador de Auphere, quiero que crear un partner invite a su propietario, para que nadie se quede esperando un correo que nadie mandó.

#### Criterios de aceptación

1. El formulario de alta DEBE pedir como obligatorio un «Correo del propietario», y DEBE explicar antes de enviar que al crear se enciende la consola y se invita a esa persona como propietaria.
2. WHEN un operador crea un partner desde el panel THEN el sistema DEBE crear, en una sola transacción, el partner con la consola encendida y sus vistas por defecto, la invitación de propietario y la auditoría de ambos.
3. IF el correo del propietario falta o no tiene forma de correo THEN el sistema DEBE rechazar la creación y NO DEBE crear nada, tanto en el formulario como en la API.
4. IF falla cualquier parte de esa transacción, incluido un identificador ya usado, THEN el sistema NO DEBE dejar partner ni invitación, y NO DEBE enviar ningún correo.
5. IF el correo del propietario ya es de una persona de otro partner o de un cliente, activa o no, THEN el sistema DEBE rechazar la creación diciendo por qué, y NO DEBE crear nada: esa invitación fallaría al aceptarla, porque una cuenta pertenece a un solo sitio.
6. WHEN la transacción termina THEN el sistema DEBE enviar la invitación fuera de ella, de modo que un fallo de envío no deshaga el partner ni la invitación.
7. La invitación DEBE ser de rol propietario, sin que el operador pueda elegir otro, y DEBE usar la plantilla de invitación de equipo ya publicada, con «Auphere» como quien invita, el nombre del partner y la fecha de caducidad.
8. El correo DEBE salir en el idioma de la cuenta de la persona si ya tiene una, y en español si no.
9. El enlace del correo y el que se muestra al operador DEBEN ser absolutos, construidos desde la dirección pública de la consola del entorno.
10. WHEN se emite una invitación de propietario AND el contacto del partner está vacío o es la dirección de la invitación a la que sustituye THEN el sistema DEBE dejar la dirección invitada como contacto del partner, y DEBE constar en la auditoría. En cualquier otro caso NO DEBE cambiar el contacto.
11. WHEN un operador crea un partner THEN el formulario NO DEBE pedir un correo de contacto aparte. Ese dato se sigue editando en la ficha del partner.

### Requisito 2 — Lo que ve el operador tras cada envío

**Historia de usuario:** Como operador, quiero saber sin dudas si el correo salió y tener cómo resolverlo si no, para no enterarme por el cliente.

#### Criterios de aceptación

1. WHEN termina un intento de envío THEN el panel DEBE mostrar el resultado en una vista que permanezca hasta que el operador decida salir, y NO DEBE confiarlo solo a un aviso que desaparece.
2. WHEN el proveedor acepta el correo THEN la vista DEBE decir a qué dirección se envió y hasta cuándo vale la invitación, y DEBE ofrecer el enlace como recurso por si no llega.
3. IF el correo no sale, por rechazo, por falta de respuesta, por falta de proveedor o por un error interno THEN la vista DEBE decir que el partner y la invitación existen, que el correo no salió y que ese enlace no se volverá a mostrar, y DEBE ofrecer copiar el enlace completo y reintentar.
4. WHEN el operador reintenta THEN el sistema DEBE aplicar el Requisito 4 y la vista DEBE sustituir el enlace anterior por el nuevo, diciendo que el anterior ya no sirve.
5. El sistema DEBE guardar por invitación la fecha del último envío que el proveedor aceptó. Sin esa fecha, la pantalla DEBE decir que no consta el envío, de modo que una caída entre crear y enviar no se pinte como un envío.
6. WHERE una invitación de Auphere está pendiente, la pestaña Equipo DEBE mostrar su estado: enviada y cuándo, o no consta el envío.
7. El panel NO DEBE decir «entregado» ni «recibido», porque la plataforma solo sabe que el proveedor aceptó el correo. La pestaña DEBE aclararlo en una línea.
8. El texto de la sección de invitaciones pendientes NO DEBE decir «Enlaces enviados», porque ahora puede haber enlaces cuyo correo no salió.
9. El resultado DEBE anunciarse a los lectores de pantalla y DEBE poder alcanzarse y usarse con teclado.
10. El aviso de tras crear NO DEBE mandar a crear una clave de API como siguiente paso.

### Requisito 3 — Invitar desde la pestaña Equipo

**Historia de usuario:** Como operador, quiero invitar al propietario de un partner que aún no lo tiene, para no necesitar la VPC.

#### Criterios de aceptación

1. WHERE un partner no tiene propietario activo ni invitación de Auphere viva, y está activo y con la consola encendida, la pestaña Equipo DEBE ofrecer un formulario de invitar con una sola dirección.
2. WHERE ese partner tiene correo de contacto, el formulario DEBE ofrecerlo ya escrito y editable, y el sistema NO DEBE enviar nada hasta que el operador pulse.
3. WHEN el operador invita THEN el sistema DEBE aplicar los criterios 1.5 a 1.10, rechazando la invitación donde 1.5 rechaza la creación, y DEBE mostrar el resultado del Requisito 2.
4. IF el partner ya tiene propietario activo THEN el sistema DEBE rechazar la invitación diciendo por qué, y la pestaña NO DEBE ofrecer el formulario.
5. IF el partner ya tiene una invitación de Auphere viva, a esa dirección o a otra THEN el sistema DEBE rechazar la nueva y pedir revocar antes, para que no haya dos enlaces de dueño a la vez, incluso con dos peticiones simultáneas.
6. IF la consola del partner está apagada THEN el sistema DEBE rechazar la invitación, y la pestaña DEBE decir que hay que encenderla, con el enlace a Módulos.
7. IF el partner está suspendido THEN el sistema DEBE rechazar la invitación, y la pestaña DEBE decir que está suspendido.
8. IF la dirección ya es de una persona de este partner THEN el sistema DEBE rechazar la invitación diciendo que ya es de su equipo.
9. Una invitación pendiente cuyo plazo ya pasó DEBE tratarse como caducada en toda la pantalla y en esta acción, aunque nadie haya abierto su enlace: NO DEBE contarse como viva ni impedir invitar de nuevo a esa dirección.
10. WHERE la última invitación de Auphere de un partner sin propietario activo está caducada, la pestaña DEBE decirlo con su fecha, y el formulario DEBE ofrecer esa dirección ya escrita, por encima del contacto.
11. WHEN se despliega esta spec THEN el sistema NO DEBE enviar nada a los partners existentes por sí solo.
12. WHERE un partner no tiene propietario activo, la cabecera de su ficha DEBE decirlo en todas las pestañas, con el estado de la invitación si la hay y el enlace a Equipo.

### Requisito 4 — Reenviar

**Historia de usuario:** Como operador, quiero mandar de nuevo la invitación, para que un correo perdido no pare un alta.

#### Criterios de aceptación

1. WHERE hay una invitación de Auphere viva, la pestaña Equipo DEBE ofrecer reenviarla, salvo en los casos de 4.4.
2. WHEN el operador reenvía THEN el sistema DEBE dejar sin efecto el enlace anterior y emitir otro para la misma dirección y el mismo rol, con el plazo completo, en una sola transacción, y después enviar el correo.
3. WHEN termina el reenvío THEN el panel DEBE mostrar el resultado del Requisito 2, y DEBE decir que el enlace anterior ya no sirve.
4. IF el partner tiene ya un propietario activo, está suspendido o tiene la consola apagada THEN el sistema DEBE rechazar el reenvío diciendo por qué, y NO DEBE tocar el enlace que hay.
5. IF la invitación ya no está viva porque se aceptó, se revocó o caducó THEN el sistema DEBE rechazar el reenvío diciendo cuál de esas cosas pasó, y la pestaña DEBE actualizarse.

### Requisito 5 — Revocar

**Historia de usuario:** Como operador, quiero anular una invitación, para que un enlace enviado a quien no era deje de abrir la puerta.

#### Criterios de aceptación

1. WHERE hay una invitación de Auphere viva, la pestaña Equipo DEBE ofrecer revocarla, sea cual sea el estado del partner, de su consola o de sus personas.
2. WHEN el operador pide revocar THEN el panel DEBE pedir confirmación diciendo qué enlace y qué dirección dejan de servir.
3. WHEN el operador confirma THEN el sistema DEBE dejar el enlace sin efecto al momento, y quien lo abra DEBE ver lo mismo que con un enlace que no existe.
4. WHEN se revoca una invitación ya revocada THEN el sistema DEBE responder éxito sin cambiar nada ni escribir otra auditoría.
5. IF la invitación ya se aceptó THEN el sistema DEBE rechazar la revocación diciendo que la persona ya está dentro, y NO DEBE retirarle el acceso.
6. WHEN se revoca THEN el sistema NO DEBE enviar ningún correo a la persona.

### Requisito 6 — Auditoría

**Historia de usuario:** Como responsable de Auphere, quiero saber quién dio las llaves de cada partner, para poder responder cuando alguien pregunte (constitución §IV).

#### Criterios de aceptación

1. WHEN un operador crea un partner, invita, reenvía o revoca THEN el sistema DEBE escribir una fila de auditoría de plataforma que nombre a la persona que actuó, no un prefijo del token del panel, junto con el partner y la dirección invitada.
2. La auditoría de creación DEBE dejar constancia de que la consola nació encendida.
3. IF la petición no identifica a un operador válido THEN el sistema DEBE rechazarla y NO DEBE hacer ningún cambio, también al crear un partner.
4. Cada acción nueva DEBE tener su frase en el vocabulario de auditoría, de modo que se lea completa en el panel y en la consola del partner, donde el actor se muestra como el equipo de Auphere.
5. El sistema NO DEBE escribir el token ni el enlace en la auditoría, ni en el registro cuando el correo se envía de verdad. La única excepción es la que ya fijó la spec 051 para un correo retenido, que producción no permite.
6. El panel NO DEBE poner el token en la dirección de ninguna de sus propias páginas: el resultado se muestra sin navegar a una URL que lo lleve.

### Requisito 7 — Aislamiento

**Historia de usuario:** Como responsable de Auphere, quiero que estas acciones no puedan cruzar de un partner a otro, para que operar uno nunca toque al de al lado (constitución §I).

#### Criterios de aceptación

1. Toda acción de esta spec DEBE tomar el partner de la ruta y DEBE limitar a ese partner cada lectura y cada escritura de personas e invitaciones.
2. IF una invitación se pide por la ruta de otro partner THEN el sistema DEBE responder con el mismo código y el mismo cuerpo, carácter a carácter, que para una que no existe, y NO DEBE cambiar nada.
3. Estas acciones DEBEN exigir el token del panel y un operador identificado. IF llega una credencial de consola, de clave de partner o de dispositivo THEN el sistema DEBE rechazarla.
4. Toda entrada de registro de estos correos, enviada o retenida, DEBE llevar el partner al que pertenece (garantía 6).
5. Las acciones de esta spec NO DEBEN leer ni escribir ninguna tabla de tenant, ni recibir un `tenant_id` del llamante (garantía 1).
6. Aceptar una invitación DEBE seguir respetando que una cuenta pertenece a un solo partner o cliente: esta spec NO DEBE relajarlo.
7. DEBE existir en `tests/isolation/` una prueba de los criterios 7.1 a 7.5. La prueba DEBE barrer las rutas de escritura de invitaciones del panel en vez de enumerarlas, para que una ruta nueva quede cubierta al montarse (constitución §I).

### Requisito 8 — Documentación viva

**Historia de usuario:** Como quien opere esto dentro de seis meses, quiero que los documentos digan lo que hace el sistema.

#### Criterios de aceptación

1. `docs/registro-de-partners.md` DEBE explicar el alta desde el panel y en qué se diferencia del alta autónoma.
2. `docs/pendientes-tras-el-go-live.md` §1 DEBE dejar de presentar el script como la vía del operador.
3. `seed_console_memberships.py` DEBE decir en su ayuda que es para desarrollo y emergencias, y que el alta normal se hace desde el panel.

### Entidades clave *(si la feature toca datos)*

- **Partner**: el negocio que se da de alta. Es de plataforma, sin `tenant_id` y sin RLS: el operador lo alcanza por la ruta. Nace activo, con la consola encendida y con el correo del propietario como contacto.
- **Invitación de propietario de Auphere**: una invitación de rol propietario que no emitió ninguna persona del partner. Es de plataforma, va atada a su partner por una columna, y de su token solo se guarda el hash. Vale 21 días. Se añade la fecha del último envío que el proveedor aceptó.
- **Persona del partner**: quien entra en la consola. Es de plataforma. «Propietario activo» es una persona activa con rol de propietario. La crea la aceptación de una invitación, nunca el operador.
- **Fila de auditoría**: de plataforma, sin tenant, con el partner como objetivo y el operador como actor.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Una persona dada de alta desde el panel recibe el correo, acepta y entra en su consola como propietaria sin que el operador haga nada más que crear el partner. Comprobado de punta a punta en staging.
- **CE-002**: El operador conoce el resultado del envío en menos de 30 segundos desde que pulsa, también con el proveedor sin responder.
- **CE-003**: Con el proveedor fallando, en el 100 % de los intentos el operador ve el fallo y un enlace que funciona, y ninguna invitación aparece como enviada sin que el proveedor la haya aceptado.
- **CE-004**: Dar de alta un partner, reenviar, revocar y corregir una dirección no requiere en ningún caso acceso a la VPC.
- **CE-005**: El 100 % de las acciones de esta spec aparecen en la auditoría con el nombre de la persona, y ninguna fila ni registro de producción contiene un enlace de invitación.
- **CE-006**: La persona invitada nunca llega a una pantalla de «sin acceso» si el partner seguía activo y con la consola encendida al aceptar.
- **CE-007**: La suite `tests/isolation/` pasa en verde con las pruebas nuevas, y una invitación de otro partner no se distingue de una inexistente.

## Fuera de alcance

- **Saber si el correo se entregó de verdad** (rebotes, avisos del proveedor): no hay esa señal en la plataforma, y abrirla es trabajo aparte. Por eso se dice «enviado» y se deja el enlace a mano.
- **Reintentos automáticos**: un correo que saliera solo más tarde podría llegar después de que el operador pasara el enlace a mano o lo revocara. Hay una persona delante y decide ella.
- **Invitar con un propietario activo, añadir otro dueño o traspasar la propiedad**: desde ese momento el equipo es del partner. Es otra decisión, con otro riesgo.
- **Gestionar desde el panel otras personas o roles del partner**: se hace desde su consola.
- **Invitar en bloque a los partners existentes sin propietario**: enviar a quien no lo espera, con datos antiguos, exige que un operador lo decida partner a partner.
- **Elegir el idioma del correo desde el panel**: se sigue la regla de la spec 051.
- **Una columna «sin propietario» en el listado de partners**: basta la cabecera de la ficha. Se añade si hace falta buscarlos.
- **La invitación vencida en la consola del partner** (`/console/team`): tiene el mismo defecto, pues reinvitar choca con una fila vencida sin marcar hasta que se revoca. Esta spec lo resuelve solo en la acción del operador.
- **La invitación de personas de un cliente en el panel**: enseña una ruta relativa y avisa de un fallo solo con un mensaje que desaparece. Es otra pantalla, y queda para su propio cambio.
- **Retirar `seed_console_memberships.py`**: sigue siendo útil para entornos de desarrollo y para desbloquear a alguien.

## Supuestos

- Una cuenta de consola pertenece a un solo partner o cliente (hoy, por diseño), y por eso una dirección que ya vive en otro sitio se rechaza al invitar en vez de fallar al aceptar. Aquí no hay oráculo: quien pregunta es un operador, que ya ve todos los partners.
- El rol de un operador solo gatea el QA Playground: en el resto del panel todos pueden lo mismo (ADR-009). Esta spec no añade permisos por rol, así que un operador «Solo lectura» también podrá invitar, igual que hoy puede suspender un partner o rotar una clave.
- La plantilla `auphere-team-invite-{es,en}` no cambia. No hace falta publicar nada en Resend.
- Un correo que el modo del entorno retiene cuenta como enviado (spec 051, R1.2). Eso solo ocurre en local y en CI. En staging, una invitación es un correo de acceso y sale de verdad, a la dirección que se escriba.
- El interruptor global de la consola está encendido en los entornos donde se usa el panel.
- Las vistas por defecto de una consola recién nacida son las que ya tiene hoy un partner nuevo; el operador las cambia en Módulos.
- El alta autónoma (spec 006) no cambia: su propietario entra sin invitación por correo.
- Solo el formulario del panel y las pruebas llaman a la ruta de creación de partners, así que puede exigir el correo sin romper a nadie más.
- Esta spec toca autorización y entrada de un correo, así que antes de darla por terminada pasan `/cso` y las revisiones de UI del espacio de trabajo (`ui-states-checklist`, `a11y-audit`, `responsive-audit`, `design-tokens`).
