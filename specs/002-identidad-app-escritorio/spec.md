# Especificación: la identidad y el puesto de trabajo en la aplicación de escritorio

**Rama**: `002-identidad-app-escritorio` · **Creada**: 2026-09-09 · **Estado**: Borrador

**Entrada**: traspaso de
[`.specify/assessments/identidad-y-consumo-en-la-app/decision.md`](../../.specify/assessments/identidad-y-consumo-en-la-app/decision.md)
— veredicto **go** del 2026-09-09, con las tres decisiones tomadas en esa puerta:
el código de emparejamiento, **la máquina pertenece al partner** y `principal_id`
se lee. Ampliado por Luis el mismo día: *«el flujo end to end desde que un
usuario descarga la app, inicia sesión o se registra, configura su espacio de
trabajo como necesitamos que lo configure, y lo guía para hacer cada paso»*.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`0`** —API de la consola— y el tramo de emparejamiento sobre la **`3a`** ya abierta por la 001. **No abre superficie nueva.** |
| **Garantías de aislamiento tocadas** | **1. Postgres RLS** (de frente: la máquina cambia de dueño —del tenant al partner— y se lee por persona) · **2. Tool whitelist por agente** (la lista blanca sigue siendo por tenant, pero la máquina que la ejecuta es del partner: hay que probar que una máquina no alcanza la lista de un tenant que no es suyo) · **6. Log + trace tagging** (emparejar, desemparejar y archivar se auditan con la persona) |
| **Nota de KB que la justifica** | `[[14-mvp-y-fases]]` §3 y `[[10-decisiones]]` decisiones **2** («solo el partner usa la app») y **9** («chats privados por persona»), con la **§2.3 declarada como dependencia abierta**. El diseño de referencia es `Auphere Web v3` (proyecto Claude Design `abc1c221…`), **leído entero** desde el artifact que Luis compartió —159 636 caracteres, seis pantallas y tres superposiciones— y contrastado con `[[00-revision-del-diseno-v3]]`. Todo en `/Users/lmatos/Work/Auphere/teammates/` |
| **Qué se mide** | **Nada nuevo.** El consumo de modelo ya entra en el medidor por la 001 (T015). Esta spec **no** añade contador, y el Requisito 9 lo convierte en prohibición |

> **Por qué no abre superficie (§II):** el valor entero de esta spec —que la
> persona entre, reclame su máquina y vea lo que tiene— cabe en la API de la
> consola y en la máquina del partner, las dos ya pagadas. Se rechazaron con
> motivo escrito las dos opciones que sí abrían superficie: un puente de contexto
> dentro de la cáscara y un esquema de URL propio en el sistema operativo
> (`concept.md` de la evaluación, Opciones B y C).

> **Esta spec enmienda un requisito de la 001.** El Requisito 6.3 de
> `specs/001-puesto-trabajo-partner/spec.md` dice que la credencial de dispositivo
> va «acotada a su tenant». A partir de esta spec va **acotada al partner y a los
> tenants de ese partner**, con el tenant fijado por trabajo y no por la
> credencial. El espíritu —no alcanza otra máquina, no alcanza a quien no le
> corresponde, un número cerrado de operaciones y ni una más— se conserva. La enmienda está en el
> Requisito 4 y lleva sus tests de aislamiento.

## Lo que hereda del diseño *Auphere Web v3*, y lo que el diseño no dibuja

El prototipo se leyó entero para esta spec. Dos hechos ordenan lo que sigue:

1. **No dibuja el escritorio.** Cero apariciones de «máquina», «dispositivo»,
   «MacBook» o «desconectada». Las seis pantallas (`Hilo · Clientes · Cliente ·
   Pendientes · Cuenta · Crear teammate`) y las tres superposiciones (Plugins,
   Tomar control, onboarding de invitación) son **la consola reescrita como
   aplicación de mensajería** — con un botón «Abrir la consola clásica» en Cuenta.
   Ese rediseño es de la beta 1 (los teammates dentro de la consola), no de esta
   spec: la cáscara cargará la consola que exista, sea la de hoy o la del diseño.
   Lo que esta spec añade es **la capa de la máquina debajo de esas pantallas**.
2. **Sí resuelve la capa de gobierno**, y ésa se hereda sin renegociar.

| Del diseño, literal | Dónde aterriza aquí |
|---|---|
| **El onboarding de invitación, paso 1 de 3**: *«Auphere te invitó a llevar tu operación aquí. El alta la hacemos nosotros: tu cuenta ya existe con tus clientes dentro, así que no hay formulario de registro ni nada que configurar.»* — CTA *«Aceptar la invitación»*, con la tarjeta «Partner · Invitación para · Rol · Caduca en 6 días» | Requisito 2: la aplicación no inventa un registro. El diseño, el código de hoy y la evaluación dicen lo mismo — y el Requisito 2.5 lo lleva a decisión |
| **Paso 3 de 3**: *«Listo. Están en las tres pantallas. El mismo hilo en web, escritorio y iPhone. Lo que apruebas en el móvil se aplica antes de que abras el portátil.»* — CTA *«Abrir Auphere»* | Requisito 6: la puesta en marcha del puesto **continúa** ese paso 3 — «tienes teammates; ahora dales tu máquina» — en vez de abrir un segundo onboarding |
| Los seis estados del hilo (`normal · cargando · vacío · error · reconectando · parcial`) y el copy del error: *«La consola respondió, el hilo no. Lo que tenía en marcha sigue corriendo en el servidor: esto es la pantalla, no el trabajo.»* | Requisito 12: la barra del puesto tiene sus siete estados nombrados, y ninguno se pinta como error. El copy del diseño fija el tono: separar la pantalla del trabajo |
| **`pausaPorTope`**: *«Trabajo en pausa: alcanzaste el tope semanal. Los hilos y las confirmaciones siguen vivos. El tope se sube desde la consola de partners.»* y el aviso *«Vas por el 85 % del tope semanal»* | Requisitos 8 y 9: el consumo se ve **como estado del hilo y en `/usage`**, del mismo libro. La barra no lo pinta: la cáscara no sabe de topes |
| **Pendientes**, estado vacío: *«Cuando un teammate necesite permiso para algo que no puede hacer solo, aparece aquí y en el iPhone. Nada se ejecuta antes.»* | Requisito 5.3: la aprobación se presenta a la persona dueña del hilo; la aplicación es una superficie más, no un canal aparte |
| **Plugins**: lo ausente se muestra con un botón *«Pedirla»*, no apagado; *«el catálogo de capacidades: Shopify está ausente, no desactivado»* | Requisitos 6.6 y 8.4: los ejecutables que Auphere no habilitó se piden, no se añaden. Misma palabra, misma disciplina |
| **Cuenta**: «Equipo · Invitar · Reenviar · Cerrar sesión» | Requisito 11.1: cerrar sesión es el de la consola, en Cuenta. La aplicación no añade otro |
| **Borrar no existe** (§3.9 de la revisión) | Requisito 11.5: una máquina se archiva, nunca se borra |
| La auditoría nombra a la persona (§5.6 de la revisión) | Requisito 13 |
| Los tokens del sistema y los dos fallos de contraste que la revisión destapó (§7: `fg-subtle` a 0,5 y `status-warning` con texto claro) | Requisito 12.6 |

**Lo que el diseño propone y no entra aquí** —el hilo como mensajería, Plugins,
Tomar control, los cuatro roles de su tabla (el código tiene cinco), la elección
de teammates del paso 2— queda en §Fuera de alcance con su motivo. Lo que la
integración del sustrato mejoró respecto al diseño —el puente saliente, la
presencia con latido, la lista blanca por tenant, la contención— ya está
construido en la 001 y se adopta tal cual.

## Escenarios de usuario y pruebas *(obligatorio)*

### El recorrido completo, en una página

Éste es el flujo end-to-end que la spec entrega. Cada paso tiene su historia y
sus requisitos debajo; aquí está entero para que nadie tenga que reconstruirlo.

```
 0  Descargar e instalar        paquete firmado (001-R9)          → abre la ventana
 1  Abrir por primera vez       la consola se carga; la barra      → «Esta máquina no está
                                del puesto dice la verdad            emparejada»
 2  Entrar                      login de la consola, dentro        → sesión de 7 días, cookie opaca
                                de la ventana                        (nada de backend en disco)
    ↳ invitado por correo       el enlace abre el navegador,       → la persona entra en la app con
                                fija contraseña y pertenencia        la contraseña recién creada
    ↳ sin pertenencia           `no-access` es un estado           → nada apagado, nada que explicar
 3  Guía del puesto             la consola enseña la lista de      → cuatro pasos, persistente por
                                puesta en marcha, que continúa       persona, se puede cerrar
                                el paso 3 del onboarding del diseño
 4  Emparejar esta máquina      la consola muestra un código;      → credencial de dispositivo,
                                la barra lo pide y lo canjea         un solo uso, máquina con dueño
 5  Nombrar la máquina          la aplicación propone el nombre    → «MacBook de Luis»
                                del sistema; la persona confirma
 6  Elegir a qué clientes       en la consola, entre los clientes  → una máquina, N clientes,
    sirve esta máquina          del partner                          UNA credencial
 7  Declarar el directorio      selector nativo desde la máquina,  → validado en la máquina,
    de cada cliente             nunca una ruta tecleada              guardado en la plataforma
 8  Ejecutables                 los pone Auphere (001-R5.4)        → la ausencia se diseña:
                                                                     «pídelo a Auphere», sin botón
 9  Ver lo que tengo            máquinas, clientes, ejecutables    → una sola verdad; el consumo
                                y `/usage`, dentro de la ventana     en `/usage`, sin contador propio
10  Trabajar                    latido, catálogo con herramientas  → 001 entera, ya construida
                                locales, aprobaciones en la app
11  Renovar sin enterarse       mientras late, la credencial se    → una instalación dura lo que
                                renueva sola                         dure el acceso de la persona
12  Cerrar sesión               la persona sale; el puente se      → sin persona delante no hay
                                detiene y las herramientas locales   quien apruebe: no se ejecuta
                                desaparecen del catálogo
13  Desemparejar / archivar     desde la máquina o desde la        → archivada, nunca borrada;
                                consola; queda quién y cuándo        el puente para de verdad
```

---

### Historia 1 — Entrar y reclamar mi máquina sin que nadie de Auphere intervenga (Prioridad: P1)

Luis descarga la aplicación, la abre, entra con su cuenta de la consola, y la
consola —dentro de la ventana— le ofrece emparejar esta máquina. Le muestra un
código corto. La barra del puesto, en la misma ventana, le pide ese código. Lo
teclea, y la barra pasa a decir *«MacBook de Luis · conectada»*. En ningún
momento ha hablado con Auphere, ha ejecutado nada en una terminal ni ha pegado
un secreto en un fichero.

**Por qué esta prioridad**: es el hueco entero. Sin esto la beta 2 no se puede
entregar a nadie que no tenga acceso a nuestra base de datos.

**Prueba independiente**: instalar en una máquina limpia, entrar con una cuenta de
partner y llegar a «conectada» **sin ningún paso fuera de la ventana**. No
depende de las historias 2 a 5.

**Escenarios de aceptación**:

1. **Dado** una instalación recién abierta, **cuando** la persona mira la
   ventana, **entonces** ve el login de la consola y una barra que dice que esta
   máquina no está emparejada — sin ningún control apagado.
2. **Dado** una persona que ha entrado, **cuando** pide emparejar esta máquina,
   **entonces** la consola le muestra un código de un solo uso con su caducidad
   visible, y la barra del puesto le ofrece introducirlo.
3. **Dado** un código válido introducido en la barra, **cuando** se canjea,
   **entonces** la máquina queda dada de alta a nombre de esa persona y de su
   partner, la barra dice *«conectada»*, y la consola la lista con su dueño.
4. **Dado** un código caducado o ya usado, **cuando** se introduce,
   **entonces** la barra lo dice como estado —*«ese código ya no vale; pide otro
   en la consola»*— y nada queda dado de alta.

---

### Historia 2 — Una máquina, todos mis clientes (Prioridad: P1)

Luis administra cuatro clientes desde el mismo portátil. Empareja la máquina
**una vez**, elige en la consola a qué clientes sirve, y declara el directorio de
cada uno con el selector de carpetas de su sistema. Cuando el teammate de un
cliente necesita ejecutar algo, lo hace en el directorio de **ese** cliente y con
la lista blanca de **ese** cliente. El teammate de otro cliente no puede ver ni
tocar el directorio del primero.

**Por qué esta prioridad**: es la decisión D-1 de la evaluación. Sin ella, la
aplicación pediría emparejar la misma máquina una vez por cliente, y la persona
acabaría con varias credenciales que la aplicación no puede llevar a la vez. Y es
la que toca §I: la máquina cambia de dueño.

**Prueba independiente**: con dos clientes del mismo partner, un solo
emparejamiento, dos directorios declarados; pedir a cada teammate que liste su
directorio y comprobar que ninguno alcanza el del otro. No necesita la historia 3.

**Escenarios de aceptación**:

1. **Dado** una máquina emparejada, **cuando** la persona elige dos clientes,
   **entonces** la máquina aparece en el puesto de trabajo de los dos, con **una**
   credencial y **una** fila de presencia.
2. **Dado** un cliente elegido, **cuando** la persona declara su directorio,
   **entonces** lo hace con el selector nativo de su sistema, y la plataforma
   guarda una ruta que la máquina ha validado antes de enviar.
3. **Dado** dos clientes con directorio en la misma máquina, **cuando** el
   teammate de uno ejecuta, **entonces** la ejecución ocurre en su directorio y
   con su lista blanca, y **no puede** alcanzar el directorio ni la lista del otro.
4. **Dado** una credencial de esta máquina, **cuando** se usa para pedir trabajo
   de un tenant que no es de este partner, **entonces** se deniega y el intento
   queda registrado.

---

### Historia 3 — La consola me lleva de la mano, y me deja en paz cuando acabo (Prioridad: P2)

Daniela entra por primera vez. La consola le enseña una lista de puesta en marcha
con cuatro pasos —emparejar, elegir clientes, declarar directorios, ejecutables— y
qué falta de cada uno. Hace el primero, cierra la lista, vuelve al día siguiente y
la lista sigue donde la dejó. Cuando termina los cuatro, desaparece y no vuelve.

**Por qué esta prioridad**: es lo que separa una app que *se puede* configurar de
una que *se sabe* configurar. Va después de las historias 1 y 2 porque guía lo que
ellas construyen.

**Prueba independiente**: una persona ajena al equipo instala la aplicación y llega
a «conectada» con un cliente y su directorio siguiendo **solo** lo que la pantalla
dice. Se mide en minutos y en preguntas hechas por otro canal (objetivo: cero).

**Escenarios de aceptación**:

1. **Dado** una persona sin máquina emparejada, **cuando** entra, **entonces** la
   consola le muestra la lista de puesta en marcha con el primer paso pendiente
   señalado, y **no** la bloquea: puede ir a cualquier otra pantalla.
2. **Dado** una lista cerrada con pasos pendientes, **cuando** la persona vuelve,
   **entonces** la lista reaparece con el estado real de cada paso, calculado
   desde la plataforma y no desde lo que la pantalla recordaba.
3. **Dado** los cuatro pasos completos, **cuando** la persona entra,
   **entonces** la lista no aparece, y no hay forma de «volver a verla» — la
   ausencia se diseña.
4. **Dado** el paso «ejecutables», **cuando** la persona lo abre, **entonces** ve
   qué ha habilitado Auphere para cada cliente y cómo pedir más — sin ningún
   control para añadirlos ella misma.

---

### Historia 4 — Cerrar sesión, desemparejar, archivar: tres actos con consecuencias (Prioridad: P1)

Luis cierra sesión al terminar el día. El puente se detiene y el teammate deja de
tener herramientas locales — no porque falle, sino porque no hay nadie delante
que pueda aprobar. Semanas después, Luis cambia de portátil: desde el viejo pulsa
«desemparejar», y desde la consola ve la máquina archivada con su nombre y la
fecha. Si en cambio el portátil se lo roban, un administrador la archiva desde la
consola, y el puente se para en menos de un minuto.

**Por qué esta prioridad**: es P1 porque hoy **ninguna** de las tres palancas
detiene el puente, y una aplicación instalada en la máquina de otra persona que
no se puede apagar desde ningún sitio no es entregable.

**Prueba independiente**: para cada uno de los tres actos, comprobar qué hace el
puente en el minuto siguiente y qué dice la barra. No depende de la historia 3.

**Escenarios de aceptación**:

1. **Dado** una máquina conectada, **cuando** la persona cierra sesión,
   **entonces** el latido para, las herramientas locales salen del catálogo del
   turno siguiente, y la barra dice *«sin sesión»* como estado.
2. **Dado** una máquina conectada, **cuando** la persona la desempareja desde la
   barra, **entonces** la aplicación olvida su credencial, la plataforma archiva
   la máquina, y la consola la muestra archivada con quién y cuándo.
3. **Dado** una máquina archivada desde la consola, **cuando** la aplicación
   late, **entonces** la plataforma la rechaza, la aplicación pasa a *«archivada
   desde la consola»*, y no vuelve a latir hasta que se empareje de nuevo.
4. **Dado** una persona que deja de pertenecer al partner, **cuando** se le
   retira la pertenencia, **entonces** sus máquinas quedan archivadas sin que
   nadie tenga que acordarse.

---

### Historia 5 — La misma máquina, dos personas (Prioridad: P2)

Luis y Daniela comparten un ordenador de la oficina. Cada uno entra con su cuenta.
Daniela no ve los hilos de Luis, y cuando un teammate pide aprobación en un hilo
de Luis, no se la pide a Daniela. Cada uno empareja «su» máquina —la misma— y la
consola las lista como dos: *«iMac de recepción · Luis»* y *«iMac de recepción ·
Daniela»*.

**Por qué esta prioridad**: es la decisión 9 aplicada al puesto de trabajo. La
001 supuso mono-usuario; el partner administra un equipo. P2 porque la beta puede
salir con máquinas de una sola persona, pero no puede salir contradiciendo la
decisión 9.

**Prueba independiente**: dos cuentas del mismo partner en la misma máquina;
comprobar hilos, aprobaciones y la lista de máquinas.

**Escenarios de aceptación**:

1. **Dado** una máquina emparejada por Luis, **cuando** Daniela entra en la misma
   aplicación, **entonces** la barra le dice que esta máquina está emparejada por
   otra persona y le ofrece emparejar la suya — sin exponer nada de Luis.
2. **Dado** dos emparejamientos en la misma máquina, **cuando** un administrador
   mira el puesto de trabajo, **entonces** ve dos máquinas con el mismo nombre de
   sistema y dueños distintos.
3. **Dado** un hilo de Luis con una aprobación pendiente, **cuando** Daniela tiene
   la sesión abierta en esa máquina, **entonces** la aprobación **no** se le
   presenta a Daniela.

---

### Casos límite

- ¿Qué pasa si el código se introduce en una máquina cuya persona ha entrado con
  **otro** partner del que emitió el código? Se deniega, y se registra: el código
  nombra partner y persona.
- ¿Qué pasa si el código se teclea mal varias veces seguidas? Hay un límite de
  intentos y una espera; el estado lo dice, y no revela si el código existe.
- ¿Qué pasa si la aplicación se cierra a mitad del canje? El código sigue siendo
  de un solo uso: o se canjeó, o no. Al volver a abrir, la barra muestra la verdad.
- ¿Qué pasa si la sesión de la consola caduca a los 7 días con el puente vivo? La
  consola pide entrar de nuevo; el puente se comporta como en un cierre de sesión
  (Historia 4.1) hasta que la persona vuelva a entrar.
- ¿Qué pasa si dos máquinas del mismo partner tienen el mismo nombre de sistema?
  Se distinguen por dueño y por fecha de alta; el nombre se puede editar.
- ¿Qué pasa si el directorio elegido con el selector nativo está en un disco
  externo que luego se desconecta? Lo cubre la 001 (Requisito 1.4): toda ejecución
  se deniega hasta que se vuelva a declarar, y la barra lo dice como estado.
- ¿Qué pasa si el sistema operativo niega a la aplicación el acceso a la carpeta
  elegida (permisos por carpeta de macOS)? La declaración falla **en la máquina**,
  antes de enviar nada, y se explica qué permiso hace falta.
- ¿Qué pasa si la persona pierde el permiso de puesto de trabajo mientras su
  máquina está emparejada? La máquina se archiva con motivo, y la barra lo dice.
- ¿Qué pasa si el reloj de la máquina está mal? La caducidad la decide la
  plataforma, nunca la máquina.
- ¿Qué pasa si la conexión de un canal de Meta se intenta dentro de la ventana?
  No se puede intentar: dentro de la aplicación ese control **no existe**, y en su
  lugar hay una indicación de continuar en el navegador (decisión D-2 de la
  evaluación).
- ¿Qué ve una persona con rol que no puede emparejar? Nada apagado: la lista de
  puesta en marcha no le muestra el paso.

## Requisitos *(obligatorio)*

### Requisito 1 — La primera apertura dice la verdad y no guarda nada

**Historia de usuario:** Como partner, quiero abrir la aplicación recién instalada
y entender en qué estado está, para no buscar un botón que no existe ni encontrar
una llave que no debería estar ahí.

#### Criterios de aceptación

1. WHEN la aplicación se abre sin máquina emparejada THEN el sistema DEBE cargar el
   login de la consola y mostrar en la barra del puesto el estado `sin emparejar`,
   y NO DEBE ofrecer ninguna herramienta local ni ningún control desactivado.
2. El sistema NO DEBE guardar en disco ninguna credencial de backend, antes ni
   después de emparejar. Lo único persistente de la persona es la cookie opaca de
   la consola (001-R15.2, heredado).
3. WHILE no hay máquina emparejada la aplicación DEBE ser útil como ventana de la
   consola: todo lo que no requiere máquina funciona igual que en el navegador.

### Requisito 2 — Entrar es entrar en la consola, y la aplicación no inventa un registro

**Historia de usuario:** Como partner, quiero entrar en la aplicación con la misma
cuenta y la misma pantalla que en el navegador, para que haya una sola forma de
ser quien soy.

#### Criterios de aceptación

1. El sistema DEBE autenticar a la persona con el login de la consola cargado
   dentro de la ventana, y NO DEBE tener un flujo de autenticación propio de la
   aplicación.
2. WHEN la sesión de la consola caduca THEN la aplicación DEBE presentarlo como
   estado —volver a entrar— y NO DEBE presentarlo como error.
3. WHERE una persona ha aceptado una invitación en el navegador del sistema EL
   sistema DEBE permitirle entrar en la aplicación con la contraseña que acaba de
   fijar, sin ningún paso adicional.
4. IF la persona entra y no pertenece a ningún partner THEN la aplicación DEBE
   mostrar el estado de sin acceso de la consola, y NO DEBE mostrar la barra del
   puesto como si hubiera algo que emparejar.
5. El alta de un partner DEBE ser un acto de Auphere seguido de una invitación
   por correo — *«el alta la hacemos nosotros»*, como dice el diseño v3 —, y el
   sistema NO DEBE ofrecer ningún formulario de registro, ni en la aplicación ni
   en la consola. Cierra la decisión §2.3 de `[[10-decisiones]]` (ver
   §Clarificaciones cerradas).

### Requisito 3 — El emparejamiento por código

**Historia de usuario:** Como partner, quiero reclamar esta máquina desde la
ventana que tengo delante, para no copiar secretos entre programas ni depender de
nadie de Auphere.

#### Criterios de aceptación

1. WHEN una persona con permiso pide emparejar una máquina THEN el sistema DEBE
   emitir un código corto, legible, de **un solo uso**, con caducidad visible, y
   ligado a esa persona y a su partner.
2. WHEN la barra del puesto canjea un código válido THEN el sistema DEBE dar de
   alta la máquina a nombre de esa persona y de ese partner, entregarle su
   credencial de dispositivo **una sola vez**, y NO DEBE volver a mostrar ni el
   código ni la credencial.
3. IF el código está caducado, ya usado, o pertenece a otra persona u otro partner
   THEN el sistema DEBE denegarlo con un mensaje que no distinga entre los tres
   casos, y DEBE registrar el intento.
4. IF se superan los intentos permitidos desde una misma máquina THEN el sistema
   DEBE imponer una espera creciente y decirlo como estado.
5. El canal entre la consola y la aplicación DEBE ser la persona. El sistema NO
   DEBE abrir ningún canal de comunicación entre la página cargada y la cáscara,
   ni registrar ningún esquema de URL propio.
6. WHEN una máquina se empareja THEN la aplicación DEBE proponer el nombre de
   sistema de la máquina como nombre visible, y la persona DEBE poder cambiarlo
   desde la consola.

### Requisito 4 — La máquina pertenece al partner *(enmienda del 001-R6.3)*

**Historia de usuario:** Como partner que administra varios clientes, quiero
emparejar mi máquina una sola vez y usarla con todos ellos, para que la
herramienta refleje cómo trabajo y no cómo está modelada la base.

#### Criterios de aceptación

1. El sistema DEBE modelar la máquina como propiedad del **partner**, y una
   máquina DEBE poder servir a cualquier subconjunto de los clientes de ese
   partner con **una sola** credencial y **una sola** presencia.
2. La credencial de dispositivo DEBE ir acotada al partner y a los tenants de ese
   partner, y DEBE estar limitada a **cinco** operaciones — latir, sondear,
   devolver resultados, renovar y declarar el directorio de un cliente —, sin
   ninguna más. *(Enmendado en el plan: el Requisito 7 exige que el directorio se
   declare desde la máquina, y eso es una operación de la máquina; contarla como
   parte de otra habría sido esconderla.)*
3. WHEN la plataforma despacha trabajo a una máquina THEN el tenant DEBE fijarse
   por trabajo desde el contexto de la plataforma, y NO DEBE llegar nunca del
   llamante ni viajar dentro de la credencial.
4. IF una credencial de máquina se usa para pedir, latir o devolver trabajo de un
   tenant que no es de su partner, o de otra máquina THEN el sistema DEBE
   denegarlo y registrar el intento.
5. El sistema DEBE conservar por tenant la lista blanca de ejecutables y la
   contención de escrituras de la 001: una máquina del partner que ejecuta para el
   cliente A DEBE hacerlo con la lista y el directorio de A, y NO DEBE alcanzar los
   de B.
6. Esta enmienda DEBE llevar test de aislamiento por cada garantía tocada (1, 2 y
   6), y un test en rojo DEBE bloquear el merge.

### Requisito 5 — Cada máquina tiene dueño, y el dueño se lee

**Historia de usuario:** Como miembro del equipo, quiero que mi máquina sea mía y
mis hilos sean míos, para que compartir un partner no signifique compartir mi
trabajo.

#### Criterios de aceptación

1. WHEN una máquina se da de alta THEN el sistema DEBE registrar a la persona que
   la emparejó como su dueña, y esa pertenencia DEBE decidir qué ve cada cual —
   no una columna que nadie consulta.
2. WHEN una persona consulta el puesto de trabajo THEN el sistema DEBE mostrarle
   sus propias máquinas; WHERE la persona administra el partner EL sistema DEBE
   mostrarle todas, con el dueño de cada una nombrado.
3. WHEN un teammate pide aprobación desde un hilo THEN la aplicación DEBE
   presentarla **solo** a la persona dueña de ese hilo, y NO DEBE presentársela a
   otra persona con sesión en la misma máquina.
4. El sistema DEBE aplicar la visibilidad por persona con el mismo patrón que ya
   protege los hilos del Companion —cerrado por defecto: sin persona en el
   contexto, cero filas— y NO DEBE reimplementarlo de otra forma.

### Requisito 6 — La puesta en marcha guiada

**Historia de usuario:** Como partner nuevo, quiero que la consola me diga qué me
falta para tener el puesto listo, para no descubrirlo cuando el teammate no pueda
hacer algo.

#### Criterios de aceptación

1. WHILE la puesta en marcha de una persona está incompleta la consola DEBE
   mostrarle una lista con cuatro pasos —emparejar esta máquina · elegir a qué
   clientes sirve · declarar el directorio de cada cliente · ejecutables
   habilitados por Auphere— y el estado real de cada uno.
2. El estado de cada paso DEBE calcularse desde la plataforma en cada visita, y
   NO DEBE depender de lo que la pantalla recordara.
3. La lista NO DEBE bloquear ninguna otra pantalla, y la persona DEBE poder
   cerrarla; WHEN vuelva con pasos pendientes THEN la lista DEBE reaparecer.
4. WHEN los cuatro pasos están completos THEN la lista NO DEBE mostrarse, y NO
   DEBE existir un control para volver a verla.
5. WHERE un paso no le corresponde a la persona por su permiso EL sistema NO DEBE
   mostrárselo — ni apagado ni explicado.
6. El paso «ejecutables» DEBE mostrar lo que Auphere ha habilitado por cliente y
   ofrecer **pedir** los que faltan —la palabra del diseño es «Pedirla»—, y NO
   DEBE ofrecer añadirlos (001-R5.4, heredado).

### Requisito 7 — El directorio de trabajo se declara desde la máquina

**Historia de usuario:** Como partner, quiero elegir la carpeta de cada cliente
con el selector de mi sistema, para no equivocarme tecleando una ruta y para que
la máquina compruebe que existe antes de prometerla.

#### Criterios de aceptación

1. WHEN la persona declara el directorio de un cliente THEN la aplicación DEBE
   ofrecer el selector nativo del sistema, y la consola NO DEBE aceptar una ruta
   tecleada.
2. WHEN se elige un directorio THEN la máquina DEBE validarlo antes de enviarlo —
   existe, es un directorio, resuelve dentro de sí mismo, y la aplicación tiene
   permiso del sistema para leerlo—, y solo entonces el sistema DEBE guardarlo.
3. IF la validación falla THEN la aplicación DEBE decir cuál de las cuatro
   condiciones falla y qué hacer, y NO DEBE guardar nada.
4. El directorio DEBE ser **por cliente y por máquina**: el mismo cliente en dos
   máquinas puede tener dos directorios, y dos clientes en la misma máquina NO
   DEBEN compartir directorio.
5. WHILE un cliente elegido no tiene directorio declarado en esta máquina el
   sistema NO DEBE ofrecer herramientas locales a los teammates de ese cliente, y
   la ausencia DEBE diseñarse.

### Requisito 8 — Ver lo que tengo, desde una sola verdad

**Historia de usuario:** Como partner, quiero ver de un vistazo qué máquinas
tengo, para qué clientes, qué puede ejecutar cada una y cuánto llevo consumido,
sin que dos pantallas me den dos cifras.

#### Criterios de aceptación

1. WHEN la persona abre el puesto de trabajo THEN la consola DEBE mostrar sus
   máquinas con presencia y desde cuándo, los clientes a los que sirve cada una,
   el directorio declarado por cliente, y los ejecutables habilitados por cliente.
2. La barra del puesto DEBE mostrar únicamente el nombre de esta máquina y su
   estado, y NO DEBE mostrar ninguna cifra de consumo.
3. El consumo DEBE verse en `/usage` dentro de la ventana, igual que en el
   navegador; el sistema NO DEBE calcular ni mostrar ninguna cifra de consumo fuera
   de ese libro.
4. WHERE una capacidad no está disponible —máquina ausente, cliente sin
   directorio, sin ejecutables— EL sistema DEBE diseñar su ausencia, y NO DEBE
   mostrar un control apagado ni una pantalla que explique lo que no se tiene.

### Requisito 9 — Nada de esto añade un contador

**Historia de usuario:** Como responsable de Auphere, quiero que el consumo siga
saliendo de un solo libro, para que las cifras que ve el partner cuadren con las
que cobramos.

#### Criterios de aceptación

1. El sistema NO DEBE introducir ningún contador, agregado o caché de consumo
   nuevo: todo lo que se muestre DEBE salir del medidor que ya alimenta la 001.
2. WHEN se empareja, se renueva, se cierra sesión, se desempareja o se archiva
   THEN el sistema NO DEBE debitar nada: ninguno de esos actos consume modelo,
   reloj de máquina ni herramienta de pago.

### Requisito 10 — La credencial se renueva sola y caduca con el abandono

**Historia de usuario:** Como partner, quiero que la aplicación siga funcionando
semana tras semana sin volver a emparejar, y que una máquina que dejé de usar
deje de valer sola.

#### Criterios de aceptación

1. WHILE la máquina mantiene su latido el sistema DEBE renovar su credencial sin
   intervención de la persona, y la renovación DEBE ser una de las cinco
   operaciones del Requisito 4.2, no una más.
2. IF una máquina no late durante **30 días** THEN el sistema DEBE dejar de
   renovarla; WHEN vuelva THEN la barra DEBE mostrar `hay que volver a emparejar`
   como estado, y NO DEBE ofrecer herramientas locales hasta entonces.
3. La caducidad DEBE decidirla la plataforma con su reloj, y NO DEBE depender del
   reloj de la máquina.
4. WHEN una credencial se renueva THEN la anterior DEBE dejar de valer, y el
   sistema DEBE registrar la renovación sin la persona — fue la máquina.

### Requisito 11 — Cerrar sesión, desemparejar y archivar

**Historia de usuario:** Como partner, quiero que salir de la aplicación, quitar
esta máquina y anular una máquina desde la consola sean tres cosas distintas con
consecuencias dichas, para saber siempre qué he apagado.

#### Criterios de aceptación

1. WHEN la persona cierra sesión en la consola dentro de la aplicación THEN el
   sistema DEBE detener el latido, retirar las herramientas locales del catálogo
   del turno siguiente y mostrar `sin sesión` en la barra; la credencial de
   máquina DEBE conservarse sellada para cuando la **misma** persona vuelva a
   entrar, y NO DEBE hacer falta volver a emparejar. La razón es la 001-R11.1:
   sin persona delante no hay quien apruebe, y una máquina que ejecuta sin nadie
   que pueda parar no es un puesto de trabajo, es un servidor.
2. WHEN la persona desempareja desde la barra THEN la aplicación DEBE olvidar su
   credencial de forma irrecuperable, detener el latido, y decir que la máquina
   queda pendiente de archivar desde la consola; la plataforma DEBE mostrarla
   `ausente` hasta que una persona la archive o la pertenencia se retire.
   *(Enmendado en `tasks.md` T048: archivar es un acto de persona con su nombre
   —R13.1— y la credencial no gana una sexta operación —R4.2.)*
3. WHEN un administrador archiva una máquina desde la consola THEN el sistema
   DEBE rechazar su siguiente latido, la aplicación DEBE pasar a `archivada desde
   la consola` y dejar de latir, y el puente DEBE estar parado en menos de un
   minuto.
4. WHEN una persona deja de pertenecer al partner THEN el sistema DEBE archivar
   todas sus máquinas con ese motivo.
5. Archivar DEBE ser terminal: una máquina archivada NO DEBE volver a
   emparejarse; se da de alta otra. Borrar no existe.
6. Este requisito depende de que la revocación de la credencial de dispositivo
   funcione — hoy no funciona (001-R6.3 incumplido, con su propio expediente de
   bug). Esta spec NO DEBE darse por completa mientras el criterio 11.3 no tenga
   test en verde.

### Requisito 12 — La única superficie propia de la aplicación

**Historia de usuario:** Como partner, quiero que lo poco que la aplicación pinta
por su cuenta esté a la altura del resto, para que no se note dónde acaba la
consola y empieza la cáscara.

#### Criterios de aceptación

1. La aplicación DEBE tener **una sola** superficie propia —la barra del puesto—
   y NO DEBE reimplementar ninguna pantalla de la consola (001-R15.1, heredado).
   Esa barra existe porque pregunta y muestra cosas que **solo la máquina sabe**:
   si está emparejada, con qué nombre, y en qué estado está su puente.
   > **Superado por `specs/003-teammates-app-escritorio` (R12.1).** Son **dos**
   > superficies propias: la barra y la pantalla de operar, cada una con su
   > partición y su `preload`. El criterio de aquí se mantiene como regla de la
   > barra, y el de la 003 explica por qué la segunda no es reimplementar la
   > consola: la consola no tiene esas pantallas.
2. La barra DEBE tener exactamente estos estados, nombrados y diseñados, y
   ninguno DEBE pintarse como error: `sin emparejar` · `emparejando` ·
   `conectada` · `reconectando` · `sin sesión` · `hay que volver a emparejar` ·
   `archivada desde la consola`.
3. WHILE la barra está en cualquier estado distinto de `conectada` el sistema NO
   DEBE ofrecer herramientas locales (001-R15.4, heredado y ampliado).
4. La barra DEBE cumplir WCAG 2.2 AA: foco visible, objetivo de ≥ 24 px, contraste
   ≥ 4,5:1 en todo texto de estado, y respeto de `prefers-reduced-motion` y
   `prefers-color-scheme`.
5. La barra DEBE usar los tokens del sistema de diseño, y NO DEBE contener ningún
   color, tamaño ni tipografía fuera de la escala declarada.
6. La barra NO DEBE usar el token de texto sutil para ningún texto que haya que
   leer, ni el de aviso con texto claro encima — los dos fallos de contraste que
   `[[00-revision-del-diseno-v3]]` §7 documentó sobre el sistema.
7. WHERE la consola se carga dentro de la aplicación EL sistema NO DEBE ofrecer
   la conexión de canales de Meta dentro de la ventana; en su lugar DEBE indicar
   cómo continuar en el navegador — como estado, no como error. La consola
   DEBE poder reconocer que la carga la cáscara, y ese reconocimiento DEBE usarse
   **solo** para este control: una bifurcación escrita y probada, no un «modo
   aplicación». Cualquier segunda bifurcación DEBE justificarse en su propia spec.

### Requisito 13 — Todo lo que cambia la identidad de una máquina queda auditado

**Historia de usuario:** Como responsable de Auphere, quiero reconstruir quién
emparejó, renovó, desemparejó o archivó cada máquina, para responder a un
incidente sin depender de la memoria de nadie.

#### Criterios de aceptación

1. WHEN una máquina se empareja, se renueva, se desempareja o se archiva THEN el
   sistema DEBE registrar el acto con partner, máquina, persona —o «la máquina»
   en la renovación— y motivo.
2. WHEN un código se deniega THEN el sistema DEBE registrar el intento con su
   motivo real, aunque a la persona no se le distinga.
3. El registro DEBE estar etiquetado por partner y alcanzado por la garantía 6
   igual que cualquier otra traza.

### Requisito 14 — Emparejar no debilita lo que la cáscara ya garantiza

**Historia de usuario:** Como responsable de seguridad, quiero que añadir el
emparejamiento no reabra lo que la 001 cerró, para que los tests que hoy están en
verde sigan diciendo la verdad.

#### Criterios de aceptación

1. El sistema DEBE conservar la separación entre la sesión de la persona y el
   ambiente del agente (001-R15.3), y los tests de `session-isolation` y
   `shell-credentials` DEBEN seguir en verde sin relajarse.
2. La credencial de máquina DEBE guardarse en la máquina de forma que no sea
   legible desde el ambiente del agente ni desde la página cargada, y la spec de
   plan DEBE decir dónde y con qué protección del sistema.
3. El puente DEBE seguir siendo saliente (001-R6.1): ni el emparejamiento ni la
   renovación DEBEN introducir ninguna conexión entrante.

### Entidades clave

- **Máquina del partner** (evoluciona `partner_devices`): la máquina declarada,
  su nombre, su plataforma, su presencia, su dueño (la persona) y su estado de
  ciclo de vida. **Pertenece al partner**, no a un tenant; la alcanza la RLS por
  su columna de partner y la visibilidad por persona por su dueño.
- **Servicio de máquina a cliente** (nuevo): qué clientes atiende una máquina y
  el directorio declarado para cada uno. Pertenece al tenant del cliente —es
  donde vive la contención y la lista blanca— y a la máquina.
- **Código de emparejamiento** (nuevo): secreto corto, de un solo uso, con
  caducidad, ligado a la persona y al partner que lo pidió. Pertenece al partner;
  muere al canjearse o caducar.
- **Credencial de máquina** (evoluciona): acotada al partner y sus tenants;
  renovable mientras late; revocable de verdad.
- **Registro de identidad de máquina** (nuevo o ampliación de la auditoría):
  quién hizo qué con qué máquina, y cuándo.

## Criterios de éxito *(obligatorio)*

- **CE-001**: el 100 % de las altas de máquina las completa el partner sin
  intervención de Auphere y sin ningún paso fuera de la ventana.
- **CE-002**: cero accesos a la base de producción para dar de alta una máquina.
- **CE-003**: una máquina se empareja **una** vez con independencia de cuántos
  clientes administre el partner.
- **CE-004**: una instalación sigue operativa indefinidamente mientras la persona
  conserve acceso y la máquina lata; una máquina abandonada 30 días deja de valer
  sola.
- **CE-005**: cerrar sesión, desemparejar y archivar detienen el puente, cada uno
  en menos de un minuto — tres de tres.
- **CE-006**: el 100 % de las máquinas responde a «¿de quién es?» con una
  consulta, y una persona no ve máquinas, hilos ni aprobaciones de otra.
- **CE-007**: una persona ajena al equipo llega a «conectada» con un cliente y su
  directorio siguiendo solo la pantalla, en menos de diez minutos y con cero
  preguntas por otro canal.
- **CE-008**: contadores de consumo distintos en el producto: exactamente uno.
- **CE-009**: cero pantallas de la consola que funcionan en el navegador y se
  rompen dentro de la ventana — la única excepción, la conexión de canales de
  Meta, está diseñada como ausencia y no como rotura.
- **CE-010**: los tests de aislamiento de la 001 siguen en verde, y los nuevos
  —máquina del partner que no alcanza tenants ajenos ni máquinas ajenas— están
  en verde.
- **CE-011**: la barra del puesto pasa la auditoría WCAG 2.2 AA sin excepciones.

## Fuera de alcance

- **Un login propio de la aplicación** — el de la consola basta y es una sola
  forma de ser quien eres (evaluación, research D-1).
- **Puente de contexto entre la página y la cáscara, y esquema de URL propio** —
  rechazados con motivo en la evaluación (Opciones B y C): abren superficie.
- **Que el enlace de invitación abra la aplicación** — nace en el navegador del
  sistema y ahí se queda; la persona entra en la app con su contraseña. Aspereza
  conocida, escrita.
- **Conectar canales de Meta desde la aplicación** — decisión D-2: en el
  navegador, y se mejora cuando toque.
- **Notificaciones de escritorio y los tres niveles de aviso del diseño (§3.5)** —
  son de las betas 3 y 4; aquí solo se garantiza que nada las contradiga.
- **Arreglar la revocación rota del 001-R6.3** — tiene su propio expediente; el
  Requisito 11.6 declara la dependencia.
- **Precio, facturación y cuánto cuesta el consumo** — se mira qué se ve.
- **Controlar el escritorio (`3b`)**, navegador embebido, beta 5 y contención en
  Windows — siguen donde la 001 los dejó.
- **La consola reescrita como aplicación de mensajería** —las seis pantallas del
  diseño v3, Plugins, Tomar control y la elección de teammates del onboarding— es
  la spec de la beta 1. La cáscara cargará esa consola cuando exista; esta spec no
  la dibuja ni la bloquea.
- **Memoria e instrucciones de equipo, búsqueda en contenido, «tomar control»**
  (`[[00-revision-del-diseno-v3]]` §5.4, §5.7, §5.8) — huecos del diseño que no
  son de identidad.

## Supuestos

- **Los certificados de firma siguen sin estar** (001-T057 bloqueada). El paso 0
  del recorrido se asume resuelto por la 001 y no se repite aquí.
- **Toda persona con acceso al puesto de trabajo puede emparejar su propia
  máquina**; añadir ejecutables sigue siendo de Auphere. Emparejar no es «escribir
  la configuración del tenant»: es reclamar lo que es tuyo.
- **El código de emparejamiento** es legible en voz alta y sin ambigüedad
  tipográfica, caduca en **diez minutos**, y el límite de intentos sigue el mismo
  criterio que las invitaciones. Los números concretos se validan en el plan.
- **Treinta días** de ausencia es el umbral para dejar de renovar. Es un valor de
  producto, no técnico, y se puede cambiar sin tocar la forma.
- **La sesión de la consola dura 7 días** y eso no cambia aquí.
- **El diseño `Auphere Web v3` se leyó entero** desde el artifact compartido
  (159 636 caracteres). No contiene ninguna pantalla de escritorio, máquina ni
  emparejamiento; lo que sí contiene —el onboarding de tres pasos, los estados del
  hilo, la pausa por tope, «Pedirla», Cuenta y Pendientes— está recogido arriba
  con su copy literal. Si el diseño evoluciona y dibuja la máquina, se enmienda
  esta spec — no se improvisa en el plan.
- **La aplicación conoce su nombre de sistema** y lo propone; no lo impone.
- **La salida de un comando es dato, nunca instrucción** (§III), igual que
  cualquier otro contenido leído. Heredado, se repite porque emparejar no lo
  cambia.

## Clarificaciones cerradas (2026-09-09)

Las tres marcas de clarificación que llevaba el borrador se cerraron con Luis el
mismo día, con la recomendación de la spec en los tres casos. Se dejan escritas
porque cada una cambió un criterio.

| Pregunta | Decisión | Qué cambió |
|---|---|---|
| ¿Qué le pasa al puente al cerrar sesión? | **Se detiene y conserva la credencial sellada** para la misma persona. Sin persona delante no hay quien apruebe (001-R11.1) | Requisito 11.1 — deja de ser marca y pasa a criterio, con su motivo |
| ¿Puede la consola saber que corre dentro de la aplicación? | **Sí, con acoplamiento mínimo**: una sola bifurcación, para esconder la conexión de canales de Meta y decir «continúa en el navegador» | Requisito 12.7 — la bifurcación es única y cualquier otra exige su propia spec |
| ¿Se cierra la decisión §2.3 de la KB —registro— aquí? | **Sí: solo por invitación.** *«El alta la hacemos nosotros»*, como dice el diseño v3, el código de hoy y la evaluación | Requisito 2.5 — de «hereda lo que la consola tenga» a prohibición del formulario de registro. La KB lo recoge en `[[10-decisiones]]` §2.3 con enlace a esta carpeta |

## Enmiendas que el plan y las tareas devolvieron a esta spec (2026-09-09)

| Criterio | Antes | Ahora | Por qué |
|---|---|---|---|
| 4.2 | cuatro operaciones | **cinco**: latir · sondear · devolver resultados · renovar · **declarar directorio** | R7 exige declarar desde la máquina; esconderlo dentro de otra operación sería mentir sobre lo que la credencial abre |
| 10.1 | «una de las cuatro» | «una de las cinco» | consecuencia de la anterior |
| 11.2 | desemparejar desde la barra **archiva** la máquina | desemparejar **olvida la credencial**; archivar queda para una persona en la consola o para la pertenencia retirada | archivar lleva nombre de persona (R13.1) y la credencial no gana una sexta operación (R4.2) |

## Riesgo asumido a propósito

El Requisito 4 —la máquina pertenece al partner— **enmienda un requisito de una
spec ya construida y en verde**. Se acepta con los ojos abiertos porque la
alternativa era entregar un emparejamiento por cliente que el partner tendría que
repetir, y la consecuencia es de plan, no de spec:

**la enmienda del modelo y sus tests de aislamiento van al principio del plan, no
al final.** Son la apuesta de esta spec, y se resuelve antes de construir la
pantalla de emparejamiento encima. Si el cambio de dueño resulta más caro de lo
que la evaluación estimó, se para y se vuelve a `shape`, no se recorta en silencio.
