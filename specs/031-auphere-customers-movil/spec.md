# Especificación: Auphere Customers — la Consola Lite en el teléfono

**Rama**: `031-auphere-customers-movil` · **Creada**: 2026-10-19 · **Estado**: Borrador

**Entrada**: prototipo «Consola Lite Movil.dc.html» (Claude Design, proyecto
`e443cbee-f802-4f49-8ec6-422e1d8d97e6`), su revisión del 2026-10-19 y las
decisiones del owner de ese mismo día. Ver §Origen.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`, la API de la consola. Entra la misma persona de la spec 030 (el usuario de un cliente) con un cliente nuevo: una app en su teléfono. Se abre **un camino de salida**: los avisos viajan por los servicios de avisos de Apple y de Google con **lo mínimo que el aviso enseña** (R9), como en cualquier app de mensajería de empresa. Apple y Google pasan a ser encargados de ese dato, y el camino pide su lectura de RGPD |
| **Garantías de aislamiento tocadas** | **1** (RLS). Hay datos nuevos por cliente: los teléfonos de cada persona y lo que quiere que le avisen. El cliente sale del acceso de quien entra, nunca de la petición. **Ejes nuevos**, cada uno con su barrido: un teléfono de una persona de un cliente ↔ los avisos de otro cliente; un teléfono cerrado, una persona quitada o un acceso apagado ↔ cualquier aviso o lectura posterior; lo que viaja a Apple y Google ↔ el mínimo de R9.2 |
| **Nota de KB que la justifica** | `[[decisions/ADR-042-la-consola-lite-en-el-telefono]]` · `[[research/2026-10-19-consola-lite-movil]]` · `[[decisions/ADR-041-consola-lite-del-cliente-final]]` · `[[compliance/2026-10-19-avisos-del-telefono]]` |
| **Qué se mide** | Nada nuevo. No hay modelo ni herramientas de pago nuevas, y enviar avisos no tiene coste por aviso. Los mensajes que una persona envía desde el teléfono entran en el medidor de mensajes enviados igual que los de la Bandeja web (spec 030, R10.5) |

> **Por qué cabe en la superficie 0:** el valor completo de esta spec es la misma
> Consola Lite, sobre las mismas cifras, conversaciones y acciones. No se le da
> nada nuevo al agente ni se lee nada nuevo de fuera.
>
> **Lo que cambia es dónde vive la sesión.** Pasa a un teléfono durante meses, en
> vez de a una cookie de 7 días. Por eso esta spec trata el teléfono como algo
> que se puede perder y revocar.

## Origen

La spec 030 dio al negocio la Consola Lite (Panel, Bandeja y Consumo), pero solo
en la web. El negocio atiende desde el teléfono: el aviso de que una conversación
espera a una persona le llega hoy a la campana y al correo. Si está cortando el
pelo, no lo ve.

Medido en el código el 2026-10-19:

1. **Lo que existe.** Las rutas de la Consola Lite (Panel, Consumo, Bandeja y
   avisos de la campana) sirven a un cliente sin pedir quién es: lo saca del
   acceso de quien entra.
2. **Las sesiones.** La web guarda la sesión en una cookie que dura **7 días
   absolutos y no se renueva por uso, a propósito**. La credencial de máquina de
   la app de escritorio solo sirve a personas de partner.
3. **Los avisos.** No existe nada que envíe avisos al teléfono.
4. **Los reintentos.** Enviar un mensaje desde la Bandeja no es idempotente: un
   reintento con mala red puede mandar dos WhatsApp a un cliente real.
5. **Las tiendas.** Ni Apple ni Google permiten, fuera de EE. UU., que una app
   enlace a comprar saldo fuera de la tienda. La spec 030 ya dejó el saldo en
   solo lectura.

### Decisiones del owner (2026-10-19)

- **Alcance:** Inicio (el Panel), Bandeja y Consumo, que son los tres módulos
  que ya existen. Reservas llega con su propia spec.
- **Nombre:** «Auphere Customers». Habrá otras apps más adelante, como
  «Auphere Partners».
- **Cuenta de las tiendas:** se publica de momento con la cuenta de
  desarrollador de FACELAD, con la migración a Auphere prevista.
- **Orden:** se cerraron antes la spec 030 y el bug «la Bandeja publica antes
  del commit». Los dos están fusionados el 2026-10-19.

## Clarifications

### Session 2026-10-19

- Q: ¿Qué enseña un aviso en la pantalla bloqueada? → A: **El detalle, solo con
  el teléfono desbloqueado.** Con el teléfono bloqueado se ve un texto neutro de
  su tipo; desbloqueado, el nombre del contacto y el motivo. Lo recogen R8.10 y
  R8.11.
- Q: ¿Desde dónde se cierra un teléfono perdido? → A: **Desde dos sitios:** la
  persona, desde la consola web, con la lista de sus teléfonos, y Auphere, desde
  el admin. Lo recogen R7.3 a R7.5. Es el único cambio que esta spec hace en la
  consola web y en el admin.
- Q: ¿Se puede «Tomar el control» desde el propio aviso? → A: **No.** El aviso
  abre la conversación y el control se toma dentro. Ninguna acción escribe desde
  el aviso. Lo recoge R8.12.
- Nota del plan (2026-10-19), sobre R8.10. Ni iOS ni Android dejan a una app
  decidir qué se ve con el teléfono bloqueado: lo decide el ajuste de vistas
  previas del teléfono.
  - En iPhone con Face ID, el valor por defecto es «Al desbloquear», y la
    respuesta del owner se cumple sin hacer nada.
  - En Android y en iPhone con Touch ID, el valor por defecto enseña el
    contenido.
  - Por eso R8.10 obliga a marcar el aviso como privado y a explicar el
    ajuste. El owner lo dio por bueno al pedir avisos normales.
- Q: ¿Cómo son los avisos push? → A: **Normales, sin lógica extra, y que
  funcionen como deben** (owner, en la revisión del plan). El aviso viaja
  completo, con título y texto, y el sistema lo muestra tal cual.
  - No hay extensión que pida el texto ni credencial aparte.
  - Por el camino va solo lo que el aviso enseña: nombre del contacto, motivo o
    principio del mensaje con un máximo de 100 caracteres, y el estado del
    saldo.
  - Nunca va un teléfono, un mensaje completo, un archivo ni una nota.
  - Lo que se ve con el teléfono bloqueado lo decide el ajuste de vistas previas
    del teléfono (R8.10).
  - Sustituye la versión anterior de R9, que exigía que nada de contenido
    viajara por Apple y Google.
- Q: ¿Las pestañas del teléfono son fijas o dinámicas? → A: **Dinámicas, como
  en la consola lite** (owner, en la revisión de la spec). Salen de los módulos
  activos del cliente, con la misma fuente, la misma regla y el mismo orden que
  la barra web. Cambian sin publicar versión y nunca dejan una pestaña rota. Lo
  recoge R3.

### Session 2026-10-20

- Q: ¿Cómo se entra en la app? → A: **Con una entrada propia de Auphere
  Customers: correo y contraseña, o Google** (owner, tras el pase vivo). La
  cuenta de Google tiene que ser la del correo que Auphere dio de alta para esa
  persona. Nada pasa por la consola de partners ni lleva su marca: los partners
  tendrán su propia app. Sustituye a la entrada por la consola en la ventana del
  sistema (R1, versión del 2026-10-19).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Entrar desde el teléfono y quedarse dentro (Prioridad: P1)

Valeria es la dueña de una barbería y ya entra en la Consola Lite por la web.

1. Instala Auphere Customers y, en su pantalla de entrada, escribe el correo con
   el que Auphere le dio acceso y su contraseña, o toca «Continuar con Google» y
   elige la cuenta de ese mismo correo.
2. Está dentro y ve las pestañas de los módulos de su negocio, en el mismo
   orden que la barra de la consola.
3. Durante meses abre la app sin volver a escribir la contraseña.

**Por qué esta prioridad**: sin entrar no hay nada. Además, es la pieza que
decide cuánto dura una sesión en un teléfono y cómo se revoca.

**Prueba independiente**: con un cliente que tenga los tres módulos, la persona
entra, cierra la app, la vuelve a abrir al día siguiente y sigue dentro sin
contraseña.

**Escenarios de aceptación**:

1. **Dado** una persona de un cliente con acceso, **cuando** entra con su correo
   y contraseña, o con la cuenta de Google de ese correo, **entonces** está
   dentro y ve solo los módulos de su cliente.
2. **Dado** un cliente con un solo módulo, **cuando** la persona entra,
   **entonces** la app abre directamente en ese módulo y no hay barra de
   pestañas.
3. **Dado** una persona de partner, **cuando** entra, **entonces** la app le dice
   que es para los negocios que atiende Auphere y no la deja dentro.
4. **Dado** una cuenta de Google de otro correo, **cuando** la persona la elige,
   **entonces** la app le dice que entre con la cuenta del correo con el que
   Auphere le dio acceso, sin enseñar cuál es, y le deja usar la contraseña.
5. **Dado** un cliente con el acceso apagado, **cuando** la persona intenta
   entrar, **entonces** la app le dice que su negocio no tiene acceso y a quién
   pedirlo.

---

### Historia 2 — Enterarse de que una conversación espera a una persona (Prioridad: P1)

El agente de soporte pide ayuda con un reembolso.

1. A Valeria le llega un aviso al teléfono aunque tenga la app cerrada.
2. Lo toca y llega a la conversación, con el motivo del agente a la vista.

**Por qué esta prioridad**: es el trabajo que la web no puede hacer y la razón
de tener una app.

**Prueba independiente**: se fuerza un escalado en un cliente de pruebas. El
aviso llega al teléfono con la app cerrada y, al tocarlo, abre esa conversación.

**Escenarios de aceptación**:

1. **Dado** una persona con los avisos permitidos, **cuando** una conversación de
   su cliente pasa a esperar a una persona, **entonces** recibe un aviso, uno
   solo por escalado, aunque la app esté cerrada.
2. **Dado** ese aviso, **cuando** lo toca, **entonces** la app abre esa
   conversación.
3. **Dado** que la persona aún no ha decidido sobre los avisos, **cuando** entra
   por primera vez, **entonces** la app le explica qué avisa antes de que el
   sistema le pida permiso, y le deja decir «Ahora no».
4. **Dado** que otra persona ya tomó el control, **cuando** Valeria abre el aviso,
   **entonces** ve quién la atiende y no se le ofrece tomarla.

---

### Historia 3 — Atender desde el teléfono (Prioridad: P1)

Valeria toma el control.

1. Contesta con texto, con una respuesta guardada o con una foto de la cámara.
2. Cuando termina, la devuelve al agente o la marca como resuelta.

**Por qué esta prioridad**: avisar sin dejar actuar solo traslada el problema.

**Prueba independiente**: sobre una conversación que espera, la persona toma el
control, envía un texto y una foto, y la devuelve al agente. El contacto recibe
los dos mensajes una sola vez.

**Escenarios de aceptación**:

1. **Dado** una conversación que espera, **cuando** la persona toca «Tomar el
   control», **entonces** la atiende ella y el agente deja de responder.
2. **Dado** que tiene el control, **cuando** envía un mensaje y la red se corta y
   vuelve, **entonces** el contacto lo recibe una sola vez.
3. **Dado** que han pasado más de 24 horas desde el último mensaje del contacto,
   **cuando** abre el cuadro para escribir, **entonces** la app le dice que
   WhatsApp no deja escribir hasta que el contacto vuelva a hacerlo, y no le
   deja enviar.
4. **Dado** que otra persona tomó el control un instante antes, **cuando** Valeria
   lo intenta, **entonces** la app le dice quién la atiende ahora y le enseña el
   estado real.

---

### Historia 4 — La Bandeja en el bolsillo (Prioridad: P2)

Valeria revisa sus conversaciones: filtra las que esperan o las que no ha leído,
busca a un cliente por su nombre o su número, y lee el hilo con las fotos y los
documentos que le enviaron.

**Por qué esta prioridad**: el aviso de la historia 2 entra a una conversación
concreta. Revisar la Bandeja entera es el segundo uso.

**Prueba independiente**: con un cliente con 200 conversaciones, la persona
filtra por «Esperan», busca un nombre y abre una foto recibida.

**Escenarios de aceptación**:

1. **Dado** la Bandeja abierta, **cuando** llega un mensaje nuevo, **entonces**
   aparece sin que la persona tenga que refrescar.
2. **Dado** que la app estuvo en segundo plano, **cuando** vuelve a ella,
   **entonces** ve el estado actual y no uno viejo.
3. **Dado** un cliente con varios agentes, **cuando** la persona filtra por un
   agente, **entonces** ve solo las conversaciones de los números de ese agente.

---

### Historia 5 — Inicio y Consumo (Prioridad: P2)

Valeria mira, en una sola pantalla, lo que necesita su atención, el gasto del
mes, el saldo y los días que le alcanza, y luego el gasto por día y por agente.

**Por qué esta prioridad**: son lecturas que ya existen y sirven tal cual. Sin
ellas, un cliente que solo tenga Panel y Consumo vería una app vacía.

**Prueba independiente**: cada cifra de Inicio y de Consumo coincide al céntimo
con la de la consola web para el mismo cliente y el mismo momento.

**Escenarios de aceptación**:

1. **Dado** un cliente con saldo, **cuando** la persona abre Consumo, **entonces**
   ve el saldo y los días que alcanza, y no ve ninguna forma de comprar ni de
   recargar saldo.
2. **Dado** que el saldo está en riesgo o agotado, **cuando** el sistema lo
   detecta, **entonces** la persona recibe el aviso, si lo tiene activado.

---

### Historia 6 — Un teléfono perdido, una persona que se va (Prioridad: P2)

Valeria pierde el teléfono y lo cierra a distancia, o un empleado deja la
barbería y Auphere le quita el acceso. En los dos casos ese teléfono deja de
recibir avisos y de poder leer nada.

**Por qué esta prioridad**: el teléfono guarda conversaciones con datos
personales de los clientes del negocio y la sesión dura meses. Revocar es la
otra cara de no pedir contraseña.

**Prueba independiente**: se quita el acceso a una persona con la app abierta.
En menos del plazo de R7.2 la app la saca y su teléfono no recibe más avisos.

**Escenarios de aceptación**:

1. **Dado** una persona dentro, **cuando** toca «Cerrar sesión», **entonces** ese
   teléfono deja de recibir avisos y los demás teléfonos de la persona siguen
   dentro.
2. **Dado** un teléfono perdido, **cuando** la persona lo cierra desde la consola
   web, o Auphere desde el admin, **entonces** ese teléfono deja de poder leer y
   de recibir avisos.
3. **Dado** que Auphere apaga el acceso del cliente o quita a la persona,
   **cuando** el teléfono vuelve a pedir algo, **entonces** sale y no recibe más
   avisos.

---

### Historia 7 — Decidir qué me avisa (Prioridad: P3)

Valeria abre Ajustes y deja activados solo los avisos de conversaciones que
esperan y de mensajes donde responde ella.

**Por qué esta prioridad**: la configuración por defecto sirve; ajustarla es un
refinamiento.

**Prueba independiente**: con un tipo apagado, se provoca ese hecho y no llega
aviso; los demás tipos siguen llegando.

**Escenarios de aceptación**:

1. **Dado** un tipo de aviso apagado en Ajustes, **cuando** ocurre ese hecho,
   **entonces** ese teléfono no recibe aviso.
2. **Dado** que la persona negó el permiso del sistema, **cuando** abre Ajustes,
   **entonces** la app le dice que los avisos están desactivados en el teléfono
   y la lleva a los ajustes del sistema. No le enseña interruptores que no hacen
   nada.

---

### Historia 8 — Contacto y notas (Prioridad: P3)

Desde una conversación, Valeria ve los datos del contacto, sus etiquetas y la
nota interna del equipo, y puede editarlas.

**Por qué esta prioridad**: ayuda a atender, pero se puede atender sin ello.

**Prueba independiente**: la persona añade una etiqueta y edita la nota desde el
teléfono, y la consola web lo muestra.

**Escenarios de aceptación**:

1. **Dado** una conversación abierta, **cuando** la persona abre «Contacto y
   notas», **entonces** ve lo mismo que en la web y puede cambiar la nota y las
   etiquetas.

---

### Casos límite

- **El aviso llega sin red.** Se ve igual, porque el texto viaja en el propio
  aviso. Al tocarlo, la app abre la conversación y dice que no hay red
  (R14.2).
- **Varias personas del mismo cliente reciben el mismo aviso.** La primera que
  toma el control se la queda. Las demás, al abrirla, ven quién la atiende.
- **La conversación está abierta en la app y llega un mensaje suyo.** No sale
  aviso en el teléfono: el mensaje aparece en el hilo.
- **El WhatsApp del cliente se desconecta.** La Bandeja deja leer el historial,
  dice que el número está desconectado y no deja enviar, igual que la web
  (spec 030, R6.2).
- **La app instalada es más vieja que la mínima.** Pide actualizar y no deja
  operar.
- **Un archivo no cumple el tipo o el tamaño.** Se rechaza antes de subirlo,
  diciendo el límite.
- **El módulo de la Bandeja se quita al cliente mientras la persona está
  dentro.** La pestaña desaparece y la app vuelve al primer módulo disponible.
  No queda pantalla rota ni botón apagado.
- **La persona cambia el idioma o el modo claro/oscuro del teléfono.** La app lo
  sigue sin reiniciarse.
- **Texto del sistema al tamaño máximo, o nombres largos.** Nada se corta ni se
  solapa, y las cifras siguen siendo legibles.
- **Dos teléfonos de la misma persona.** Los dos reciben los avisos que tengan
  activados. Cerrar uno no cierra el otro.
- **Una cuenta en un teléfono compartido de recepción.** Es una sola persona por
  teléfono; para cambiar de persona se cierra la sesión.
- **La cuenta de las tiendas se migra de FACELAD a Auphere.** Se asume que todas
  las personas vuelven a entrar una vez (ver Supuestos).

## Requisitos *(obligatorio)*

### Requisito 1 — Entrar

**Historia de usuario:** Como persona de un cliente, quiero entrar en la app con
el correo con el que Auphere me dio acceso, con mi contraseña o con Google, sin
pasar por la consola de partners.

#### Criterios de aceptación

1. WHEN la persona abre la app sin sesión THEN el sistema DEBE mostrar la
   entrada propia de Auphere Customers con dos métodos: correo y contraseña, y
   Google. NO DEBE pasar por la consola de partners ni mostrar su marca.
2. WHEN la persona entra con correo y contraseña THEN el sistema DEBE
   comprobarlos con las mismas reglas que la web (bloqueo de la cuenta por
   intentos y límites por correo y por IP). IF no valen THEN DEBE decir que el
   correo o la contraseña no son correctos, sin decir cuál falla ni si el correo
   existe.
3. WHEN la persona elige «Continuar con Google» THEN el sistema DEBE abrir la
   elección de cuenta de Google en la ventana segura del sistema, y DEBE
   aceptar la cuenta solo si Google verifica su correo y ese correo es el que
   Auphere dio de alta para la persona en el cliente. IF no coincide THEN DEBE
   decirlo, sin enseñar el correo dado de alta, y DEBE ofrecer la contraseña.
4. WHEN la entrada termina bien THEN el sistema DEBE dejar a la persona dentro
   sin otro paso y con el cliente de su acceso, que nunca elige ella.
5. IF la cuenta es de una persona de partner THEN el sistema DEBE decir que la
   app es para los negocios que atiende Auphere y NO DEBE dejarla dentro.
6. IF el cliente no tiene la Consola Lite activa, o la persona ya no pertenece al
   cliente, THEN el sistema DEBE decirlo, DEBE decir a quién pedir acceso y NO
   DEBE dejarla dentro.
7. WHEN la persona toca «¿Olvidaste tu contraseña?» THEN el sistema DEBE pedir
   el correo y enviar el enlace para crear una nueva, con la misma respuesta
   exista o no la cuenta.
8. El sistema DEBE dejar que el gestor de contraseñas del teléfono rellene el
   correo y la contraseña, y NO DEBE guardar la contraseña: solo la sesión del
   teléfono (R2.3).
9. IF la entrada se cancela o falla THEN el sistema DEBE volver a la pantalla de
   entrada diciendo qué pasó, sin pantallas en blanco.

### Requisito 2 — Quedarse dentro

**Historia de usuario:** Como persona de un cliente, quiero no tener que entrar
cada semana.

#### Criterios de aceptación

1. WHILE la persona usa la app al menos una vez cada 90 días el sistema DEBE
   mantenerla dentro sin pedir la contraseña.
2. IF pasan 90 días sin que la app se abra en ese teléfono THEN el sistema DEBE
   pedir entrar de nuevo.
3. El sistema DEBE guardar la sesión solo en el almacenamiento seguro del
   teléfono, y NO DEBE poder leerla otra app.
4. El sistema DEBE tratar cada teléfono como una sesión distinta, con su nombre y
   su fecha de último uso.

### Requisito 3 — Pestañas dinámicas = módulos

**Historia de usuario:** Como negocio, quiero ver en el teléfono los mismos
módulos que en la consola, y que cambien cuando Auphere cambia los míos.

#### Criterios de aceptación

1. El sistema DEBE construir las pestañas a partir de los módulos que el
   cliente tiene activos en ese momento. Usa la misma fuente y la misma regla
   que la barra de la consola lite, incluida la de disponibilidad de la Bandeja
   (spec 030, R6.1). NO DEBE salir de una lista fija dentro de la app.
2. El orden de las pestañas DEBE ser el de la barra de la consola lite, y lo DEBE
   fijar una sola fuente para la web y para la app.
3. WHEN Auphere activa o quita un módulo del cliente THEN la app DEBE
   reflejarlo. Un número desconectado no quita la pestaña: es un estado dentro
   de la Bandeja (spec 030, R6.2), igual que en la web. La app lo refleja:
   - al volver al primer plano o en la siguiente petición;
   - sin cerrar la sesión, sin reinstalar y sin publicar una versión nueva.
4. WHERE el cliente tiene un solo módulo EL sistema DEBE abrir en ese módulo, sin
   barra de pestañas.
5. IF el módulo de la pestaña abierta deja de estar activo THEN el sistema DEBE
   llevar a la persona al primer módulo disponible, sin pantalla rota ni botón
   apagado.
6. IF el cliente tiene activo un módulo que esta versión de la app aún no sabe
   mostrar THEN el sistema:
   - NO DEBE pintar una pestaña vacía ni rota;
   - DEBE seguir con los demás módulos;
   - DEBE pedir actualizar solo cuando Auphere lo exija con la versión mínima
     (R13).
7. IF el cliente no tiene ningún módulo activo THEN el sistema DEBE tratarlo como
   un cliente sin acceso (R1.5).
8. El sistema DEBE ofrecer en Ajustes un enlace para abrir la consola en la web.

### Requisito 4 — Inicio y Consumo

**Historia de usuario:** Como negocio, quiero saber en el teléfono cómo va y
cuánto me queda.

#### Criterios de aceptación

1. El sistema DEBE mostrar en Inicio lo mismo que el Panel de la consola lite:
   lo que necesita atención (con acceso a su pantalla), el gasto del mes, el
   saldo y los días que alcanza, y las conversaciones de los últimos 7 días.
2. El sistema DEBE mostrar en Consumo el saldo, los días que alcanza, el gasto del
   mes con su proyección, el gasto por día (7, 30 y 90 días) y el reparto por
   agente.
3. Cada cifra DEBE coincidir al céntimo con la de la consola web para el mismo
   cliente y el mismo momento, y en la misma moneda.
4. El sistema NO DEBE ofrecer comprar, recargar ni pedir saldo, NI enlazar a una
   página donde hacerlo.
5. El detalle técnico del Consumo y su exportación NO DEBEN estar en la app; se
   quedan en la web.

### Requisito 5 — La Bandeja

**Historia de usuario:** Como negocio con WhatsApp conectado, quiero leer y
contestar a mis clientes desde el teléfono.

#### Criterios de aceptación

1. El sistema DEBE ofrecer la Bandeja con las mismas reglas de disponibilidad que
   la web (spec 030, R6).
2. El sistema DEBE listar las conversaciones con sus filtros (todas, sin leer,
   esperan, resueltas), el filtro por agente cuando hay más de uno, y búsqueda
   por nombre o número del contacto.
3. El sistema DEBE mostrar el hilo con los mensajes del contacto, del agente y de
   las personas, los avisos del sistema (pidió ayuda, control tomado, devuelta,
   resuelta) y los archivos recibidos, que se pueden abrir.
4. WHILE la app está en primer plano el sistema DEBE pintar los cambios de la
   Bandeja y del hilo abierto en menos de 5 segundos, sin refrescar a mano.
5. WHEN la app vuelve del segundo plano THEN el sistema DEBE pedir el estado
   actual antes de dejar actuar sobre él.
6. El sistema DEBE dejar marcar una conversación como no leída, resolverla y
   reabrirla.

### Requisito 6 — Tomar el control, contestar y devolver

**Historia de usuario:** Como negocio, quiero atender una conversación desde el
teléfono y devolvérsela al agente.

#### Criterios de aceptación

1. WHEN una conversación espera a una persona THEN el sistema DEBE mostrar el
   motivo del agente antes de la acción «Tomar el control», con la acción al
   alcance del pulgar.
2. IF otra persona cambió el control antes THEN el sistema DEBE decir quién la
   atiende ahora y DEBE mostrar el estado real, sin aplicar la acción.
3. WHILE la persona tiene el control el sistema DEBE dejarle enviar texto,
   elegir una respuesta guardada (que se queda en el cuadro sin enviarse) y
   adjuntar una foto de la cámara o de la galería, o un documento, dentro de los
   tipos y tamaños de la web.
4. IF el envío se reintenta por cualquier motivo THEN el contacto DEBE recibir el
   mensaje una sola vez.
5. IF han pasado más de 24 horas desde el último mensaje del contacto THEN el
   sistema NO DEBE dejar enviar y DEBE decir por qué, antes de que la persona
   escriba.
6. IF el envío falla THEN el sistema DEBE dejar el mensaje en el hilo marcado
   como no enviado, con la opción de reintentar, y NO DEBE perder el texto.
7. El sistema DEBE ofrecer, como primera opción del menú de la conversación,
   «Devolver al agente», con el nombre del agente.
8. El sistema DEBE medir cada mensaje enviado desde el teléfono como cualquier
   mensaje saliente del cliente.

### Requisito 7 — Revocar

**Historia de usuario:** Como negocio y como Auphere, quiero que un teléfono
perdido o una persona que se va dejen de ver y de recibir nada.

#### Criterios de aceptación

1. WHEN la persona cierra la sesión en un teléfono THEN el sistema DEBE dejar de
   enviar avisos a ese teléfono, DEBE borrar lo que la app guardaba de ese
   cliente y NO DEBE cerrar sus otros teléfonos.
2. WHEN Auphere apaga el acceso del cliente, quita a la persona o cierra un
   teléfono THEN ese teléfono DEBE dejar de poder leer en menos de 15 minutos y
   NO DEBE recibir ningún aviso posterior al cambio.
3. El sistema DEBE mostrar a la persona, en la consola web, la lista de sus
   teléfonos con su nombre y su último uso, y DEBE dejarle cerrar cualquiera de
   ellos.
4. El sistema DEBE dejar que Auphere, desde el admin, vea los teléfonos de las
   personas de un cliente y cierre cualquiera de ellos.
5. Una persona NO DEBE ver ni cerrar los teléfonos de otra persona, ni siquiera
   del mismo cliente.
6. El sistema DEBE dejar constancia de cada entrada y de cada cierre de un
   teléfono, con la persona, el teléfono y quién lo cerró.

### Requisito 8 — Avisos

**Historia de usuario:** Como negocio, quiero enterarme en el teléfono de lo que
necesita a una persona, sin perderme nada y sin ruido.

#### Criterios de aceptación

1. El sistema DEBE ofrecer tres tipos de aviso:
   - «Una conversación espera a una persona»;
   - «Mensaje nuevo en una conversación que atiendes tú»;
   - «Saldo bajo o agotado».
2. WHEN una conversación pasa a esperar a una persona THEN el sistema DEBE avisar
   a los teléfonos de las personas del cliente que tengan ese tipo activado, una
   vez por escalado.
3. WHEN el contacto escribe en una conversación que atiende una persona THEN el
   sistema DEBE avisar solo a los teléfonos de esa persona.
4. WHEN la campana del cliente recibe un aviso de saldo bajo o agotado THEN
   el sistema DEBE avisar a los teléfonos que tengan ese tipo activado, una vez
   por aviso de la campana.
5. El sistema DEBE avisar solo después de que el hecho haya quedado guardado, y
   NO DEBE avisar de algo que luego no ocurrió.
6. WHEN la persona toca un aviso THEN el sistema DEBE abrir la pantalla del
   hecho: la conversación o Consumo.
7. WHILE la conversación del aviso está abierta en primer plano el sistema NO
   DEBE mostrar el aviso de esa conversación.
8. WHERE el teléfono permite niveles de interrupción EL aviso de «espera a una
   persona» DEBE ir en el nivel urgente (el que atraviesa los modos de
   concentración si la persona lo permite), y los demás en el normal.
9. WHERE el sistema del teléfono permite canales de avisos EL sistema DEBE crear
   un canal por tipo, para que la persona decida su importancia en los ajustes
   del teléfono.
10. WHILE el teléfono está bloqueado y su ajuste de privacidad oculta el
    contenido de los avisos, el aviso NO DEBE mostrar datos de un cliente
    final: se ve un texto neutro de su tipo o el texto oculto del sistema. El
    sistema DEBE marcar cada aviso como privado ante el sistema del teléfono, y
    DEBE explicar, en la pantalla de permiso y en Ajustes, cómo activar ese
    ajuste.
11. WHILE el teléfono está desbloqueado el aviso DEBE mostrar el nombre del
    contacto y el motivo del agente, o el principio del mensaje en el aviso de
    «mensaje nuevo».
12. El aviso NO DEBE ofrecer acciones que escriban: ni tomar el control ni
    responder. Tocarlo DEBE abrir la pantalla del hecho (R8.6), y el control se
    toma desde dentro.

### Requisito 9 — Lo mínimo en el camino de los avisos

**Historia de usuario:** Como Auphere, quiero avisos normales, que lleguen
siempre, y que por el camino viaje solo lo que el aviso enseña.

#### Criterios de aceptación

1. El aviso DEBE llegar completo con lo que enseña: título y texto en el idioma
   del teléfono. El teléfono NO DEBE pedir nada a la red para mostrarlo.
2. El texto que viaja a los servicios de avisos de Apple y de Google DEBE
   limitarse a:
   - el nombre del contacto;
   - el motivo del agente o el principio del mensaje, como mucho 100
     caracteres;
   - el estado del saldo.

   Y NO DEBE incluir números de teléfono, mensajes completos, archivos ni
   notas internas.
3. El sistema NO DEBE enviar ningún aviso a un teléfono revocado, ni a una
   persona sin acceso o sin el módulo.

### Requisito 10 — Pedir el permiso de avisos

**Historia de usuario:** Como persona de un cliente, quiero saber qué me van a
avisar antes de decir que sí.

#### Criterios de aceptación

1. WHEN la persona entra por primera vez en un teléfono THEN el sistema DEBE
   explicar qué avisa, en una pantalla propia, antes del diálogo del sistema, y
   DEBE dejarle decir «Ahora no» sin lanzar ese diálogo.
2. IF la persona dijo «Ahora no» THEN el sistema DEBE dejar activar los avisos más
   tarde desde Ajustes.
3. IF el permiso del sistema está negado THEN el sistema DEBE decirlo en Ajustes y
   llevar a los ajustes del teléfono, y NO DEBE mostrar interruptores sin
   efecto.

### Requisito 11 — Ajustes

**Historia de usuario:** Como persona de un cliente, quiero controlar lo mío
desde la app.

#### Criterios de aceptación

1. El sistema DEBE mostrar en Ajustes la persona, su correo, su negocio y su
   papel.
2. El sistema DEBE ofrecer un interruptor por tipo de aviso, que aplica a ese
   teléfono.
3. El sistema DEBE ofrecer «Cerrar sesión» en ese teléfono.
4. El sistema DEBE ofrecer «Solicitar el borrado de la cuenta», que avisa a
   Auphere y dice qué pasa después.

### Requisito 12 — Contacto y notas

**Historia de usuario:** Como negocio, quiero ver y anotar quién es el contacto
mientras le atiendo.

#### Criterios de aceptación

1. El sistema DEBE mostrar los datos del contacto, sus etiquetas y la nota
   interna del equipo, lo mismo que la web (spec 030, R13).
2. El sistema DEBE dejar editar la nota y las etiquetas, y la web DEBE verlo en
   su siguiente lectura.

### Requisito 13 — Versión mínima

**Historia de usuario:** Como Auphere, quiero poder retirar una versión de la app
que ya no es segura o compatible.

#### Criterios de aceptación

1. IF la versión instalada es más vieja que la mínima que Auphere fija THEN el
   sistema DEBE pedir actualizar con un enlace a la tienda, y NO DEBE dejar
   operar.
2. Auphere DEBE poder subir la versión mínima sin publicar una versión nueva de
   la app.

### Requisito 14 — Estados, accesibilidad, idioma y tema

**Historia de usuario:** Como persona de un cliente, quiero que la app me diga
siempre la verdad y que la pueda usar como uso mi teléfono.

#### Criterios de aceptación

1. Cada pantalla que muestra datos DEBE tener sus estados de carga, vacío, error,
   reconectando y parcial, y NO DEBE enseñar cifras o listas viejas como si
   fueran actuales (constitución §V).
2. IF el teléfono no tiene red THEN el sistema DEBE decirlo, DEBE dejar leer lo
   último que se cargó, marcado como no actualizado, y NO DEBE dejar acciones que
   escriban.
3. El sistema DEBE seguir el modo claro u oscuro del teléfono.
4. El sistema DEBE seguir el tamaño de texto del sistema hasta su máximo, sin
   cortes ni solapes.
5. El sistema DEBE cumplir WCAG 2.2 AA: contraste, objetivos táctiles de al menos
   44 × 44 pt en iOS y 48 × 48 dp en Android, nombres accesibles para los
   lectores de pantalla, y una alternativa sin gesto para cada acción que se
   haga deslizando.
6. El sistema DEBE estar en español e inglés y seguir el idioma del teléfono, con
   el mismo vocabulario que la consola («Tomar el control», «Necesita humano»).
7. El sistema DEBE respetar la reducción de movimiento del teléfono.
8. El sistema DEBE usar las transiciones, las hojas y los gestos del sistema de
   cada plataforma, y NO DEBE inventar transiciones propias entre pantallas.
9. WHEN la persona toma el control, envía un mensaje o choca con un cambio de
   otra persona THEN la app DEBE confirmarlo con un movimiento breve y una
   vibración propia de cada caso. Ninguna animación DEBE pasar de 300 ms ni
   repetirse en bucle, salvo el indicador «Reconectando».

### Requisito 15 — Aislamiento comprobado

**Historia de usuario:** Como Auphere, quiero que las fronteras nuevas se prueben
barriendo, no enumerando.

#### Criterios de aceptación

1. El sistema DEBE tener un test que, con dos clientes del mismo partner y
   personas con teléfonos en los dos, compruebe que ningún hecho de un cliente
   produce un aviso en un teléfono del otro, para todos los tipos de aviso.
2. El sistema DEBE tener un test que recorra todas las rutas que la app puede
   alcanzar y compruebe que, con la sesión de un teléfono, solo devuelven datos
   del cliente de esa persona y de sus módulos.
3. El sistema DEBE tener un test que compruebe que, después de cerrar un
   teléfono, quitar a una persona o apagar el acceso, ese teléfono no lee nada ni
   recibe ningún aviso.
4. El sistema DEBE tener un test que recorra todos los tipos de aviso y
   compruebe que lo que se entrega a Apple y a Google solo lleva los campos de
   R9.2, dentro de sus límites. Los datos de prueba incluirán números de
   teléfono, mensajes largos, notas y archivos «canario», y ninguno debe
   aparecer.
5. El sistema DEBE tener un test que compruebe que la sesión de un teléfono de
   persona de cliente no alcanza ninguna ruta de partner ni de admin.
6. El sistema DEBE tener un test que compruebe dos cosas:
   - la lista de teléfonos de la consola web solo devuelve y deja cerrar los
     teléfonos de la persona que la pide;
   - la del admin solo devuelve los del cliente consultado.

### Entidades clave

- **Teléfono de una persona**: cada teléfono donde una persona de un cliente ha
  entrado. Guarda la plataforma, un nombre legible, cuándo entró, cuándo se usó
  por última vez y si sigue activo. Pertenece al cliente de la persona y la RLS
  lo alcanza por ese cliente; nunca por un cliente que mande la app.
- **Destino de avisos**: la dirección a la que los servicios de Apple o de Google
  entregan los avisos de un teléfono, y qué tipos tiene activados. Uno por
  teléfono. Pertenece al cliente. Al cerrar el teléfono deja de usarse.
- **Aviso entregado**: constancia de qué aviso se envió a qué teléfono y por qué
  hecho, **sin contenido**. Sirve para no repetir y para auditar. Pertenece al
  cliente.
- **Versión mínima**: la versión más vieja de la app que se deja operar, por
  plataforma. Es de Auphere, no de un cliente.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Una persona que ya tiene cuenta instala la app y está dentro de su
  negocio en menos de 2 minutos.
- **CE-002**: El 95 % de los avisos de «espera a una persona» llegan al teléfono
  en menos de 10 segundos desde que el agente pide ayuda.
- **CE-003**: Desde tocar el aviso, con el teléfono desbloqueado, hasta poder
  escribir la primera respuesta hay como mucho 2 toques.
- **CE-004**: En una prueba de 100 envíos con cortes de red forzados, el
  contacto recibe cada mensaje exactamente una vez.
- **CE-005**: Cada cifra de Inicio y Consumo coincide al céntimo con la consola
  web.
- **CE-006**: Los seis barridos de aislamiento de R15 pasan con cero
  excepciones no escritas.
- **CE-007**: Tras revocar un teléfono, una persona o un acceso, ese teléfono no
  recibe ningún aviso y deja de leer en menos de 15 minutos.
- **CE-008**: Ninguna pantalla tiene incidencias graves o críticas de
  accesibilidad, en claro y en oscuro, ni con el texto del sistema al tamaño
  máximo.
- **CE-009**: Una persona que abre la app al menos una vez al mes no vuelve a
  escribir su contraseña en 90 días.
- **CE-010**: En el piloto, la mediana entre que una conversación pide una
  persona y que alguien toma el control, en horario del negocio, es menor de
  10 minutos.
- **CE-011**: Un módulo que Auphere activa o quita en el admin aparece o
  desaparece en la app la siguiente vez que vuelve al primer plano, sin publicar
  ninguna versión.

## Fuera de alcance

- **Reservas** (agenda, lista de espera, choques, calendarios conectados): no
  tiene spec web ni API; irá en su propia spec, y luego en la app.
- **Comprar o recargar saldo, y cualquier enlace para hacerlo**: el saldo es de
  solo lectura (spec 030, C2), y las tiendas prohíben enlazar a una compra fuera
  de ellas salvo en EE. UU.
- **Responder desde el aviso**: decisión del owner. Se responde dentro de la app.
- **Plantillas de WhatsApp fuera de la ventana de 24 horas**: igual que en la web,
  se quedan en la consola del partner.
- **Instagram, Messenger, YCloud y TikTok**: solo se usa WhatsApp por Meta.
- **Una app por partner o con su marca** (C4): las tiendas rechazan las apps de
  plantilla y los duplicados. Se publica una sola app, Auphere Customers.
- **Personas de partner**: tendrán su propia app más adelante (Auphere Partners).
- **Crear, editar y borrar respuestas guardadas**: en la app se usan; se
  gestionan en la web.
- **Detalle técnico del Consumo y exportación**: se quedan en la web.
- **Enviar sin red y mandarlo después**: sin red no se escribe. El texto escrito
  no se pierde, pero no se envía solo.
- **Enlaces de los correos que abren la app**: siguen abriendo la web.
- **Diseño propio para tableta, reloj, widgets y actividades en vivo**: no hacen
  falta para el trabajo de la v1.
- **Bloqueo de la app con huella o cara**: la v1 confía en el bloqueo del
  teléfono. Se revisa con el uso del piloto.

## Supuestos

- **Las personas ya tienen cuenta.** Las invita Auphere desde el admin (spec 030,
  R1). La invitación se acepta en la web; la app no gestiona invitaciones. El
  enlace para crear una contraseña nueva también se abre en la web.
- **Google y la guía 4.8 del App Store.** Ofrecer Google suele obligar a ofrecer
  también una opción equivalente («Iniciar sesión con Apple»), salvo en apps de
  empresa que solo aceptan cuentas que da la organización. Esta app solo acepta
  cuentas que Auphere da de alta, y así se presenta a revisión. Si App Review lo
  exige, se añade Apple con la misma regla del correo. TestFlight interno no
  pasa revisión.
- **La spec 030 está desplegada y su Bandeja publica después del commit.** Las
  dos cosas se fusionaron el 2026-10-19. La app no añade ningún dato que la web
  no tenga.
- **Plazos de sesión.** La sesión del teléfono dura mientras se use al menos una
  vez cada 90 días. Revocar llega en menos de 15 minutos. Son los valores por
  defecto de apps de mensajería de empresa, y se pueden afinar en el plan.
- **Plataformas.** Se publica en el App Store y en Google Play, visible en las
  dos tiendas, con la cuenta de desarrollador de FACELAD.
  - Al migrar a la cuenta de Auphere, cada persona tendrá que volver a entrar
    una vez. Se acepta mientras las personas sean pocas.
  - El identificador de la app es de Auphere desde el primer día
    (`com.auphere.customers`).
- **Versiones del sistema.** La app funciona en las dos últimas versiones
  mayores de iOS y de Android que exijan las tiendas en el momento de
  publicar.
- **Una persona por teléfono.** Una recepción compartida usa una sola cuenta
  cada vez.
- **Moneda y horario.** Son la moneda y el horario que ya muestra la consola
  lite para ese cliente.
- **Piloto.** Un cliente con la Bandeja activa y WhatsApp conectado, que el
  owner elige en `/speckit-clarify` o en el plan, por los canales de prueba
  cerrada de cada tienda.
- **Cuenta para la revisión de las tiendas.** Hace falta un cliente de
  demostración en producción, bajo Auphere Internal Partner, cuya Bandeja no
  envíe WhatsApp a personas reales. Es requisito para publicar, no una función
  de la app.
- **El cómo queda para el plan:** dónde se comprueba la sesión del teléfono y
  con qué se construye la app. Las opciones y la recomendación están
  en la nota de KB. El plan cita la licencia de todo lo que instale
  (constitución §VIII).
