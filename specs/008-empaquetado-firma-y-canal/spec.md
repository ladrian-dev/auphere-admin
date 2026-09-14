# Especificación: la aplicación se instala, y se arregla sola

**Rama**: `008-empaquetado-firma-y-canal` · **Creada**: 2026-09-14 · **Estado**: Borrador

**Entrada**: traspaso de
[`.specify/assessments/empaquetado-firma-y-actualizacion/decision.md`](../../.specify/assessments/empaquetado-firma-y-actualizacion/decision.md)
— veredicto **go** del 2026-09-11. La aplicación de escritorio está completa y
verificada desde la spec 003, y **el único sitio donde se abre es un repositorio
con `pnpm` y `electron` a mano**. No hay nada que instalar y no hay forma de
hacer llegar una corrección: el puente es saliente por diseño (001), así que una
versión que rompa el puente deja esa máquina fuera hasta que alguien reinstale.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **NUEVA, y hay que decirlo con todas las letras.** Es de la misma clase que la `3a` de la 001: **el canal de actualización puede reemplazar el binario que ejecuta comandos en la máquina del partner.** Ejecución remota de código con otro nombre. Por eso la spec la trata igual que la 001 trató la ejecución local: firma verificada antes de aplicar, canal de solo lectura para todo el mundo menos la cadena, y publicación únicamente desde integración continua |
| **Garantías de aislamiento tocadas** | **Ninguna de las 7 de `architecture/agent-isolation.md` se debilita** — no hay tenant, ni RLS, ni herramienta nueva. Pero la superficie nueva exige su propia prueba, que no es de aislamiento entre tenants sino de **integridad del artefacto**: un paquete manipulado no se instala, y un binario que no lleva nuestra firma no llega ni a preguntarle al canal |
| **Nota de KB que la justifica** | `[[teammates/14-mvp-y-fases]]` §1 — el corte por superficie supone gente con la aplicación instalada · `[[nexus/decisions/ADR-037…]]` no aplica aquí |
| **Qué se mide** | **Nada nuevo.** No consume modelo, ni reloj de máquina, ni herramienta de pago. El coste del canal es de infraestructura y se ve donde ya se ven los demás |

> **Por qué se abre esta superficie ahora (§II).** No hay forma de dar este valor
> dentro de la superficie actual: la alternativa a un canal es que cada partner
> reinstale a mano cada corrección, y eso no es una versión barata de lo mismo —
> es no tenerlo. Se abre por su mitad barata primero: **solo macOS, solo lectura,
> y publicando solo desde la cadena**.

## Estado real, contrastado el 2026-09-14

Los `tasks.md` y el propio assessment han envejecido. Esto es lo que hay:

| Pieza | Estado |
|---|---|
| Entitlements del hardened runtime | **Escritos**, en el commit `e100564` de `feat/desktop-auto-update`, con la excepción de `.gitignore` sin la cual el fichero no viaja y nadie se entera |
| Política de actualización | **Escrita y probada** (pura, 117 líneas de test): no se actualiza un binario sin Developer ID ni con el paquete ya en disco; descargar e instalar son decisiones distintas; se instala al salir |
| Actualizador | **Escrito**: verifica su **propia** firma contra el Team ID antes de escuchar al canal |
| `electron-builder` | **Configurado**: dmg y zip, arm64 y x64, notarización, canal de publicación |
| Certificado y notarización | **Existen desde el 2026-09-13.** `Developer ID Application: FACELAD SpA (CBSWMG766P)`, cadena G2, válido hasta 2031; clave de App Store Connect con acceso Developer. **`T057` de la spec 001 dice que están bloqueados por plazo y es falso** |
| Pruebas de la app en integración continua | **Ya corren** (`ci.yml`, `desktop` y `companion-ui`). El punto 6 del assessment está resuelto |
| Un comando único de verificación | **Ya existe** (`./scripts/verify.sh`). El punto 7 del assessment está resuelto |
| Cadena de release | **No existe.** No hay ningún workflow de release en `.github/workflows/` |
| Infraestructura del canal | **No existe.** `infra/terraform/40-releases/` **no tiene ni un fichero `.tf`**: sólo un `prod.tfplan` binario huérfano de un módulo que nunca se versionó |
| Bucket de releases | **No verificable** con las credenciales de esta máquina (cuenta `831081046687`, producción es `793033583982`) |

**Nada de lo que falta es código de cliente.** Lo que falta es la cadena, sus
secretos y el sitio donde publicar.

## Clarifications

### Session 2026-09-14

- Q: ¿Hay una vía de publicación manual de emergencia, o la cadena es el único camino? → A: **disparo manual de la cadena**, sí; **subida directa al canal, no**. Se puede lanzar la cadena a mano además de por marca de versión, pero sigue firmando y notarizando en integración continua y deja rastro de quién la disparó. Hay precedente: cuatro workflows del repo ya admiten disparo manual, incluido el de producción.
- Q: ¿Se exige una versión mínima desde el primer despliegue? → A: **la cañería se construye y se deja apagada**, siguiendo el patrón de la industria (ver §El patrón que se sigue). Ningún mínimo declarado el día uno; preaviso obligatorio antes de exigir uno; y el bloqueo duro se reserva a incompatibilidad de contrato o seguridad.
- Q: No existe ningún estado de pantalla para «hay una versión esperando». ¿Qué ve la persona? → A: **un estado nuevo y discreto** en la barra. Sin él, la aplicación cambia de versión al reabrir sin que nadie sepa por qué, y cuando el actualizador *espera* por una sesión viva no hay forma de saber que espera ni por qué (§V: la ausencia se diseña).
- Q: ¿Hace falta publicación gradual y un canal de pruebas separado desde el día uno? → A: **canal único, sin gradual**. Lo que contiene una versión mala con tres partners es que la anterior siga en el canal (R2.5) y una llamada de teléfono. Se registra el contra: el concepto del assessment lo pedía expresamente porque el puente es saliente.

### El patrón que se sigue para la versión mínima

Buscado, no recordado (2026-09-14). Las aplicaciones de escritorio con servidor
detrás convergen en lo mismo:

- **[Slack](https://slack.com/intl/en-fi/help/articles/1500000026321-Slack-deprecation-policy-for-app-versions-browsers-and-operating-systems)**
  deprecia versiones dos veces al año, en un calendario publicado, y avisa con
  **seis meses** de antelación. Exigir un mínimo por organización es una opción
  del administrador, no el comportamiento por defecto.
- **[Zoom](https://www.it.northwestern.edu/about/news-events/2023/zoom-minimum-version-requirement.html)**
  fija un mínimo trimestral en fechas conocidas de antemano y avisa **90 días**
  antes. Por debajo del mínimo el cliente deja de funcionar y queda el navegador.
- La práctica corriente en Electron es **actualización blanda por defecto**, con
  bloqueo reservado a incompatibilidad de contrato o parche de seguridad, y
  **sin forzar el reinicio**: se da tiempo a guardar el trabajo
  ([guía de auto-update](https://www.emadibrahim.com/electron-guide/auto-updates)).

Tres cosas de ahí que esta spec adopta y que no estaban en el borrador: **el
preaviso es obligatorio**, **avisar y bloquear son dos cosas distintas**, y **el
bloqueo se reserva** a que el contrato se rompa o a seguridad. Lo de no forzar
el reinicio ya lo cumple la política rescatada.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Alguien ajeno instala la aplicación y entra (Prioridad: P1)

Una persona que nunca ha visto el proyecto recibe un enlace, abre el instalador,
arrastra la aplicación, la abre y entra. **Sin tocar la terminal y sin ver un
solo aviso del sistema** sobre un desarrollador no identificado.

**Por qué esta prioridad**: sin esto no hay beta. Todo lo demás son mejoras de
algo que todavía no existe.

**Prueba independiente**: se construye el artefacto, se copia a un Mac que nunca
ha visto el proyecto, y se abre. Se prueba sola y sin canal.

**Escenarios de aceptación**:

1. **Dado** un Mac limpio, **cuando** alguien abre el instalador descargado y
   arrastra la aplicación, **entonces** la aplicación arranca al primer intento
   y sin aviso de desarrollador no identificado.
2. **Dado** el artefacto construido, **cuando** se comprueba su firma y su
   notarización, **entonces** la cadena llega hasta la raíz de Apple y el sello
   de notarización está grapado al propio artefacto.
3. **Dado** un artefacto al que se le ha cambiado un byte, **cuando** alguien
   intenta abrirlo, **entonces** el sistema lo rechaza.
4. **Dado** que la aplicación se firma con el runtime endurecido, **cuando**
   arranca, **entonces** el motor de JavaScript funciona — es decir, los
   permisos declarados son los que hacen falta y no se descubre al publicar.

---

### Historia 2 — Una corrección llega sola, sin interrumpir trabajo (Prioridad: P2)

Se publica una versión nueva. La aplicación instalada se entera, la descarga en
segundo plano y **la aplica cuando la persona cierra**, nunca en medio de una
tarea que espera ni de un comando corriendo en su disco.

**Por qué esta prioridad**: es la mitad que convierte «hay algo instalado» en
«se puede arreglar». Va después porque sin la Historia 1 no hay nada instalado
que actualizar.

**Prueba independiente**: se publican dos versiones seguidas y se observa a una
instalación real coger la segunda.

**Escenarios de aceptación**:

1. **Dado** una aplicación instalada y una versión nueva publicada, **cuando**
   la aplicación comprueba el canal, **entonces** la descarga sin preguntar y
   sin interrumpir nada.
2. **Dado** una versión ya descargada y una sesión de agente viva o una acción
   esperando confirmación, **cuando** llega el momento de instalar, **entonces**
   el sistema **espera**, y lo dice en pantalla con los estados que ya tiene.
3. **Dado** una versión descargada y ningún trabajo vivo, **cuando** la persona
   cierra la aplicación, **entonces** la actualización se aplica al salir.
4. **Dado** un binario que no lleva nuestra firma de distribución, **cuando**
   arranca, **entonces** **no le pide una versión al canal siquiera**, y esa
   negativa se mantiene aunque ya haya un paquete descargado en el disco.
5. **Dado** un artefacto publicado y manipulado después, **cuando** la
   aplicación intenta aplicarlo, **entonces** lo rechaza por la firma.

---

### Historia 3 — La plataforma puede dejar fuera una versión vieja (Prioridad: P3)

Cuando una versión antigua deja de ser admisible —porque el contrato del puente
cambió o porque tenía un fallo—, la plataforma la rechaza **con una respuesta
legible**, y la aplicación lo cuenta en vez de comportarse como si no hubiera
red.

**Por qué esta prioridad**: es la red de seguridad de las otras dos, y no hace
falta el día uno. Pero la cañería tiene que estar antes de que haya versiones
viejas ahí fuera, porque después ya es tarde.

**Prueba independiente**: se fija un mínimo por encima de la versión instalada y
se comprueba qué ve la persona.

**Escenarios de aceptación**:

1. **Dado** una versión por debajo del mínimo exigido, **cuando** la aplicación
   llama a la plataforma, **entonces** recibe una respuesta que dice **qué pasa
   y qué hacer**, y no un error de red.
2. **Dado** esa respuesta, **cuando** la aplicación la recibe, **entonces** la
   pantalla lo nombra como un estado más y ofrece actualizar.

---

### Casos límite

- **La barra gana un estado, y sólo uno.** Los siete que hay son de conexión y
  emparejamiento; ninguno sirve para «hay una versión esperando». Es superficie
  de interfaz nueva —pequeña, y del mismo tipo que las que ya existen— y por eso
  se nombra aquí en vez de colarse como detalle de implementación.
- **Una versión rompe el puente.** Es el peor caso de esta superficie: el puente
  es saliente, así que no se puede empujar el arreglo a una máquina que ya no
  llama. Lo que lo contiene es que **la versión anterior siga disponible en el
  canal** y que la publicación sea gradual.
- **El certificado se revoca.** Distinto de caducar: caducar no rompe nada ya
  firmado; **revocar deja las aplicaciones instaladas sin arrancar**. Y quien
  puede revocar hoy es el titular del equipo de firma, que **no es Auphere**.
- **La cadena publica un artefacto que no arranca.** El runtime endurecido sin
  los permisos correctos no falla al construir: falla al abrir. Tiene que haber
  una prueba de humo **antes** de publicar.
- **Dos publicaciones a la vez**, o una publicación a medias que deje el canal
  anunciando una versión cuyo binario no está entero.
- **Qué ve la persona cuando no hay nada que actualizar** (§V): nada. No hay
  botón apagado ni pantalla que explique lo que no tienes — la ausencia se
  diseña.

## Requisitos *(obligatorio)*

### Requisito 1 — Un artefacto que se abre en una máquina limpia

**Historia de usuario:** Como partner, quiero instalar la aplicación como
cualquier otra, para empezar a usarla sin que nadie me ayude.

#### Criterios de aceptación

1. El sistema DEBE producir un artefacto de instalación y otro de actualización
   para macOS, **cubriendo tanto Apple Silicon como Intel**.
2. Los artefactos DEBEN ir firmados con una identidad de distribución, con el
   runtime endurecido y con los permisos que la aplicación necesita declarados.
3. Los artefactos DEBEN estar notarizados y llevar el sello **grapado al propio
   fichero**, para que la primera apertura no dependa de tener red.
4. WHEN alguien abre el artefacto en un Mac que nunca ha visto el proyecto THEN
   la aplicación DEBE arrancar sin aviso de desarrollador no identificado y sin
   que haya que tocar la terminal.
5. IF el artefacto se modifica después de firmarlo THEN el sistema DEBE
   rechazarlo.
6. WHERE la aplicación se firma con el runtime endurecido EL sistema DEBE
   comprobar **antes de publicar** que el artefacto firmado **abre**, y NO DEBE
   publicar uno que no se haya abierto.

### Requisito 2 — El canal es de solo lectura, y sólo la cadena escribe

**Historia de usuario:** Como responsable del producto, quiero que nadie pueda
poner un binario delante de mis partners sin pasar por la cadena.

#### Criterios de aceptación

1. El sistema DEBE publicar los artefactos en un canal accesible por HTTPS y
   **de solo lectura para todo el mundo**.
2. El sistema NO DEBE permitir escribir en el canal a ninguna identidad que no
   sea la de la cadena de integración continua.
3. El sistema NO DEBE exigir ningún secreto **dentro del binario del cliente**
   para leer el canal.
4. WHEN se publica una versión THEN DEBE quedar rastro de qué se publicó, desde
   qué punto de la historia del código y quién lo disparó.
5. La versión inmediatamente anterior DEBE seguir disponible en el canal después
   de publicar una nueva.
6. El sistema DEBE permitir **disparar la cadena a mano**, además de por marca
   de versión, y ese disparo DEBE quedar registrado con quién lo hizo.
7. El sistema NO DEBE admitir que se coloque un artefacto en el canal por
   ninguna vía que no sea la cadena. Un binario firmado en el portátil de
   alguien y subido a mano **no es una emergencia resuelta: es la garantía de
   esta superficie rota**, y el disparo manual de R2.6 existe precisamente para
   que esa tentación no haga falta.

### Requisito 3 — La actualización no interrumpe trabajo

**Historia de usuario:** Como partner, quiero que la aplicación se arregle sola
sin perder lo que estoy haciendo.

#### Criterios de aceptación

1. El sistema DEBE descargar una versión nueva en segundo plano, sin preguntar.
2. WHILE haya una sesión de agente viva o una acción esperando confirmación EL
   sistema NO DEBE instalar, y DEBE decir en la barra que hay una versión
   esperando **y que está esperando por eso**.
3. WHEN la persona cierra la aplicación y hay una versión descargada THEN el
   sistema DEBE aplicarla al salir, y NO DEBE reiniciar por su cuenta.
4. IF el binario en ejecución no lleva la firma de distribución THEN el sistema
   NO DEBE pedir ninguna versión al canal, ni siquiera con un paquete ya
   descargado en el disco.
5. IF un artefacto no supera la comprobación de firma THEN el sistema NO DEBE
   aplicarlo.
6. El sistema DEBE servir **un solo canal**, sin publicación gradual ni canal de
   pruebas separado. Lo que contiene una versión mala es que la anterior siga
   disponible (R2.5) y que el cohorte quepa en una llamada de teléfono.
7. WHERE haya una versión descargada esperando EL sistema DEBE decirlo en la
   barra con un estado propio, y ese estado DEBE distinguir **«lista, se
   instala al cerrar»** de **«esperando a que termine lo que hay vivo»**.
8. WHEN no haya ninguna versión esperando THEN la barra NO DEBE mostrar nada
   sobre actualizaciones: ni indicador apagado ni texto que explique lo que no
   hay (§V).

### Requisito 4 — Una versión vieja recibe una respuesta legible

**Historia de usuario:** Como operador, quiero poder dejar fuera una versión sin
que la persona vea un error incomprensible.

#### Criterios de aceptación

1. La plataforma DEBE poder declarar una versión mínima admisible.
2. WHEN una aplicación por debajo del mínimo llama a la plataforma THEN la
   respuesta DEBE decir qué ocurre y qué hacer, y NO DEBE parecer un fallo de
   red.
3. WHERE la aplicación recibe esa respuesta EL sistema DEBE nombrarlo como un
   estado de la pantalla y ofrecer actualizar.
4. El sistema NO DEBE rechazar ninguna versión mientras no se declare un
   mínimo, y **el primer despliegue NO DEBE declarar ninguno**. La capacidad se
   construye ahora porque después ya habría versiones viejas instaladas sin
   forma legible de avisarlas; exigir un mínimo con una sola versión publicada
   no protegería de nada y podría cerrarle la puerta a la primera beta.
5. WHEN se vaya a exigir un mínimo THEN las instalaciones afectadas DEBEN
   haber sido avisadas **antes** de que empiece a rechazarse nada.
6. El sistema DEBE distinguir **avisar** de **bloquear**: una versión vieja
   admisible recibe un aviso y sigue funcionando; sólo una por debajo del mínimo
   se rechaza.
7. El bloqueo DEBE reservarse a que el contrato del puente se haya roto o a un
   problema de seguridad, y NO DEBE usarse para empujar mejoras.

### Requisito 5 — La identidad de firma es un secreto de producción

**Historia de usuario:** Como responsable, quiero que firmar no dependa del
portátil de nadie, y saber qué hacer el día que la identidad se pierda.

#### Criterios de aceptación

1. La cadena DEBE firmar con una identidad guardada como secreto, **sin depender
   del llavero de ninguna persona**.
2. El sistema NO DEBE dejar la identidad ni sus claves accesibles después de la
   ejecución que las usó.
3. El repositorio NO DEBE aceptar material de firma en ningún commit.
4. El procedimiento de **rotación y de revocación** DEBE estar escrito, y la
   rotación DEBE haberse probado al menos una vez.
5. La documentación DEBE decir **quién puede revocar** la identidad y qué les
   pasa a las instalaciones existentes si ocurre.

### Requisito 6 — Lo que ya existe se rescata, no se reescribe

**Historia de usuario:** Como equipo, quiero no volver a escribir lo que ya está
escrito y probado.

#### Criterios de aceptación

1. El sistema DEBE incorporar el trabajo del commit `e100564` —entitlements,
   política de actualización, actualizador y configuración de empaquetado—
   conservando su autoría y sus pruebas.
2. WHEN se incorpore THEN las pruebas que trae DEBEN ejecutarse en la tubería y
   estar en verde antes de construir ningún artefacto.
3. La tarea de la spec 001 que declara la firma bloqueada por falta de
   certificados DEBE actualizarse: los certificados existen desde el 2026-09-13.

### Requisito 7 — La infraestructura del canal está versionada

**Historia de usuario:** Como quien tenga que reconstruir esto, quiero que el
canal esté descrito en el repositorio y no en la memoria de alguien.

#### Criterios de aceptación

1. La infraestructura del canal DEBE estar declarada en el repositorio, de modo
   que se pueda reconstruir desde cero.
2. El repositorio NO DEBE conservar planes de infraestructura binarios ni
   artefactos de estado.
3. WHEN se aplique infraestructura THEN el plan DEBE leerse entero antes, y si
   aparece algo que nadie pidió, DEBE pararse y preguntarse.
4. IF una clave declarada en la infraestructura no existe en el almacén de
   secretos THEN eso DEBE detectarse antes de aplicar, y no al arrancar un
   servicio.

### Entidades clave

- **Artefacto de versión**: el paquete publicado. Lleva versión, arquitectura,
  huella de firma y el punto de la historia del código del que salió. **No
  pertenece a ningún tenant**: es de plataforma, y el canal no distingue quién
  descarga.
- **Canal**: el índice de lo publicado y los propios paquetes. Solo lectura para
  todo el mundo; escritura únicamente desde la cadena.
- **Versión mínima admisible**: un dato de plataforma que la API compara con la
  que declara cada máquina. Ya viaja en el latido y en el agente de usuario.

## Criterios de éxito *(obligatorio)*

- **CE-001**: una persona ajena al equipo instala la aplicación en un Mac limpio
  y entra, sin terminal y sin ningún aviso del sistema.
- **CE-002**: se publica una versión y una instalación existente la adopta sola,
  aplicándola al cerrar y nunca sobre trabajo vivo.
- **CE-003**: la cadena entera corre sin nadie delante, disparada por una marca
  en la historia del código.
- **CE-004**: un artefacto manipulado no se instala, y un binario sin la firma de
  distribución no llega ni a consultar el canal.
- **CE-005**: el canal no es escribible por ninguna identidad que no sea la
  cadena, comprobado y no supuesto.
- **CE-006**: la infraestructura del canal se reconstruye desde el repositorio.
- **CE-007**: con una versión esperando, la barra dice que espera y por qué; sin
  ninguna, no dice nada sobre actualizaciones.

## Fuera de alcance

- **El emparejamiento sin código tecleado.** Está investigado y respondido —la
  credencial de máquina se mantiene, el código de 8 símbolos se puede sustituir
  por un canje silencioso con la sesión que la aplicación ya ve— pero es **otra
  superficie y otro cambio de comportamiento**, y §II pide no abrir dos a la
  vez. Va en su propia spec.
- **Windows.** Otra cadena de firma y otro instalador, y la contención de
  escrituras **no está portada**: empaquetar allí prometería lo que no se cumple.
- **La App Store.** Su caja de arena rompe la ejecución local.
- **La edición empaquetada sobre KiroCrew** (`apps/edition`): otro artefacto.
- **Telemetría de instalación.** Si hace falta, es una spec con su propia
  conversación sobre qué se recoge.
- **Actualizaciones diferenciales.** El paquete completo basta a este tamaño.
- **El icono de la aplicación.** El assessment lo listaba **dentro** del alcance;
  aquí queda fuera y conviene decir por qué, porque es un desacuerdo entre
  documentos y no un olvido: es trabajo de diseño, no bloquea la cadena, y
  meterlo dentro haría que una decisión estética pudiera retrasar la beta. La
  aplicación se publica con el icono que tenga.
- **Migrar la identidad de firma al equipo de Auphere.** Decidido aparte; esta
  spec deja escrito el coste de hacerlo.

## Supuestos

- **Se firma con el equipo de FACELAD SpA (`CBSWMG766P`), y es temporal.** Es un
  acuerdo ya tomado: había una membresía activa y esperar al enrolamiento de
  Auphere habría bloqueado la beta semanas. Tiene dos consecuencias que esta
  spec no puede ocultar: **quien puede revocar la identidad es Facelad**, y una
  revocación deja sin arrancar las aplicaciones ya instaladas; y **cambiar de
  equipo más adelante altera el identificador de la aplicación**, así que macOS
  la tratará como otra: nadie se actualizará solo, el llavero dejará de leerse y
  **cada partner tendrá que volver a emparejar**. De ahí que el momento de
  migrar sea **mientras el cohorte quepa en una llamada de teléfono**.
- La identidad de firma y la clave de notarización **ya existen y están
  probadas** contra Apple (2026-09-13). Esta spec no las obtiene: las usa.
- Las pruebas de la aplicación y del paquete compartido **ya corren en la
  tubería**, y hay un comando único de verificación. Los puntos 6 y 7 del
  assessment están cerrados y no se repiten aquí.
- La cuenta de producción es `793033583982` en `eu-south-2`, donde ya vive todo
  lo demás.
- El volumen inicial es de unas pocas instalaciones: el dimensionado del canal
  no es un problema todavía.
