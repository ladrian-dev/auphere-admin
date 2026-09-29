# Especificación: el número se puede mover

**Rama**: `021-numero-puede-mover` · **Creada**: 2026-09-29 · **Estado**: Borrador

**Entrada**: descripción del usuario: ver §Origen.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. Las llamadas a Meta son las mismas que el alta ya hace, deshechas |
| **Garantías de aislamiento tocadas** | Ninguna en su promesa. La única novedad: una fila desvinculada de otro tenant deja de **bloquear** un alta ajena, y eso no revela nada — la regla de unicidad deja de chocar con ella, no la lee |
| **Nota de KB que la justifica** | `[[sessions/2026-09-29-spec-019-iteracion-1]]` · `[[architecture/agent-isolation]]` §1 |
| **Qué se mide** | Nada |

## Origen

El 2026-09-29 el owner preguntó: *«si desactivo un WhatsApp en un agente, ¿puedo
activarlo en otro agente de otro partner, con el mismo número?»*. La respuesta
medida fue **no**, por tres cierres apilados, cada uno en un sitio distinto:

| Cierre | Dónde | Qué hace |
|---|---|---|
| **La regla de unicidad** | la base de datos | un número existe **una vez en toda la plataforma**, sin mirar de quién es ni si sigue en uso |
| **Desvincular conserva la fila** | spec 019, en staging desde hoy | la decisión —correcta para guardar historial— deja el número **ocupado** por una fila que ya no atiende |
| **Meta** | la cuenta del partner | el número está registrado en la WABA de A; desvincular hoy **no deshace nada** allí |

Lo que le pasa hoy a un partner B que intenta conectar un número que A
desvinculó: el alta no encuentra la fila de A (no la puede ver), intenta crear
la suya, y **falla con un error de base de datos** — no con un mensaje que
explique nada.

## Clarifications

### Session 2026-09-29

- Q: Cuando A desvincula un número y un partner B distinto quiere conectarlo, ¿quién autoriza el traspaso? → A: **autoservicio, Meta arbitra**. A desvincula, B conecta, sin pantalla de aprobación en Auphere. El árbitro ya existe: B no puede registrar un número que A no haya soltado en su Business Manager. Añadir una aprobación nuestra sería vigilar una puerta que Meta ya vigila.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Desvincular suelta el número de verdad (Prioridad: P1)

Un partner desvincula un número de un cliente. A partir de ese momento el
número **no está ocupado**: el mismo cliente puede volver a conectarlo, otro
cliente del mismo partner puede conectarlo, y un cliente de otro partner
también — siempre que en Meta lo hayan soltado.

**Por qué esta prioridad**: es la pregunta del owner, literal. Sin esto,
«desvincular» significa «apagar», y un número que un negocio deja de usar se
queda muerto en la plataforma para siempre.

**Prueba independiente**: desvincular un número en el cliente A, conectarlo
en el cliente B, y ver que B atiende por él y A ya no.

**Escenarios de aceptación**:

1. **Dado** un número desvinculado del cliente A, **cuando** el cliente B lo
   conecta, **entonces** B queda atendiendo por él y A sigue viendo su
   historial con ese número, marcado como desvinculado.
2. **Dado** un número desvinculado del cliente A, **cuando** A lo vuelve a
   conectar, **entonces** recupera **su misma** ficha de canal —historial
   incluido— en vez de estrenar otra.
3. **Dado** un número **activo** en A, **cuando** B intenta conectarlo,
   **entonces** B recibe un mensaje que dice que el número está en uso, y
   **nada** de A cambia.

---

### Historia 2 — Desvincular deshace en Meta lo que conectar hizo (Prioridad: P1)

Conectar ata el número a nuestra aplicación en Meta. Desvincular lo desata:
el número deja de estar registrado bajo nosotros, y si era el último de esa
cuenta de WhatsApp Business, nuestra aplicación deja de estar suscrita a ella.

**Por qué esta prioridad**: es lo que el owner pidió con esas palabras —«que
se desvincule del Meta Business, no solo desactivarlo»— y sin ello la
Historia 1 no cierra: B no puede registrar un número que sigue registrado
bajo nosotros para A.

**Prueba independiente**: desvincular y comprobar contra Meta que el número
ya no está registrado bajo la aplicación.

**Escenarios de aceptación**:

1. **Dado** un número conectado, **cuando** se desvincula, **entonces** deja
   de estar registrado bajo nuestra aplicación en Meta.
2. **Dado** que era el **último** número vivo de esa cuenta de WhatsApp
   Business en ese cliente, **cuando** se desvincula, **entonces** nuestra
   aplicación deja de estar suscrita a esa cuenta y las credenciales
   guardadas para ella se borran.
3. **Dado** que **quedan otros números vivos** en esa misma cuenta,
   **cuando** se desvincula uno, **entonces** la aplicación **sigue suscrita**
   y los demás números siguen atendiendo sin interrupción.

---

### Historia 3 — Si Meta falla, el partner se entera y sabe qué hacer (Prioridad: P1)

Meta puede no contestar, o contestar que no. El canal **no puede quedarse a
medias en silencio**: en nuestro lado se desvincula igual —el agente deja de
atender, que es lo que el partner pidió— y la pantalla dice qué quedó
pendiente en Meta y cómo terminarlo.

**Por qué esta prioridad**: es el modo de fallo nuevo. Un «desvinculado» que
sigue registrado en Meta sin que nadie lo sepa es peor que no desvincular.

**Prueba independiente**: desvincular con Meta caído y leer la pantalla.

**Escenarios de aceptación**:

1. **Dado** que Meta no responde al dar de baja el número, **cuando** el
   partner desvincula, **entonces** el canal queda desvinculado en la
   consola, el agente deja de atender, y la ficha dice que en Meta queda
   pendiente y qué hacer.
2. **Dado** un canal con algo pendiente en Meta, **cuando** el partner lo
   mira, **entonces** puede reintentar desde ahí sin volver a desvincular.

### Casos límite

- ¿Y si el número que B quiere conectar sigue registrado en la WABA de A en
  Meta? El alta de Meta se lo dirá a B; nuestra pantalla explica que el dueño
  anterior tiene que soltarlo en su Business Manager. **No lo soltamos
  nosotros**: es su activo.
- ¿Dos clientes intentan conectar el mismo número a la vez? Gana el primero;
  el segundo recibe «en uso», como en la Historia 1.3.
- ¿Y el playground, que tiene un canal interno por cliente? No es un número
  y no entra en la regla de unicidad de números.
- ¿Qué ve quien no puede escribir en canales? La tarjeta sin la acción, como
  hoy.

## Requisitos *(obligatorio)*

### Requisito 1 — Un número desvinculado no ocupa sitio

**Historia de usuario:** Como partner, quiero que un número que ya no uso
quede libre, para poder ponerlo donde haga falta.

#### Criterios de aceptación

1. El sistema DEBE impedir que dos canales **vivos** compartan un número, en
   toda la plataforma.
2. El sistema NO DEBE contar los canales desvinculados en esa regla: un número
   desvinculado DEBE poder conectarse en cualquier otro cliente.
3. WHERE un cliente vuelve a conectar un número que él mismo desvinculó EL
   sistema DEBE reactivar **su** canal, conservando el historial, y NO DEBE
   crear uno nuevo.
4. IF un cliente intenta conectar un número **vivo** en otro sitio THEN el
   sistema DEBE decirlo con palabras —«este número está en uso»— y NO DEBE
   fallar con un error técnico ni tocar el canal ajeno.
5. El sistema NO DEBE revelar a quién pertenece un número en uso: solo que lo
   está.

### Requisito 2 — Desvincular deshace lo que conectar hizo

**Historia de usuario:** Como partner, quiero que desvincular signifique
soltar el número de verdad, para que deje de estar atado a mi cuenta.

#### Criterios de aceptación

1. WHEN se desvincula un número THEN el sistema DEBE darlo de baja en Meta,
   de modo que deje de estar registrado bajo nuestra aplicación.
2. WHEN el número desvinculado era el último vivo de su cuenta de WhatsApp
   Business en ese cliente THEN el sistema DEBE desuscribir nuestra aplicación
   de esa cuenta y borrar las credenciales guardadas para ella.
3. IF quedan otros números vivos en esa misma cuenta THEN el sistema NO DEBE
   desuscribir la aplicación ni tocar las credenciales, y los demás números
   DEBEN seguir atendiendo.
4. El sistema NO DEBE intentar sacar el número de la cuenta del partner en
   Meta: es su activo, y el aviso DEBE decir que eso se hace allí.

### Requisito 3 — Nada se queda a medias en silencio

**Historia de usuario:** Como partner, quiero saber si desvincular terminó del
todo, para no descubrir dentro de un mes que el número seguía atado.

#### Criterios de aceptación

1. IF Meta falla al dar de baja o al desuscribir THEN el sistema DEBE
   desvincular igualmente el canal en la consola —el agente deja de atender—
   y DEBE dejar constancia de qué quedó pendiente.
2. WHERE un canal tiene algo pendiente en Meta EL sistema DEBE enseñarlo en su
   tarjeta con lo que falta y una forma de reintentar.
3. El sistema DEBE anotar en la auditoría cada desvinculación con lo que se
   consiguió y lo que no.

### Requisito 4 — Un número cambia de manos sin pedir permiso

**Historia de usuario:** Como owner, quiero saber quién autoriza que un número
pase de un partner a otro.

#### Criterios de aceptación

1. El traspaso DEBE ser **autoservicio**: A desvincula, B conecta, y el
   sistema NO DEBE pedir aprobación de Auphere en ningún caso. *(Owner,
   2026-09-29. El árbitro real ya existe: B no puede registrar un número que
   A no haya soltado en su Business Manager de Meta. Una aprobación nuestra
   sería vigilar una puerta que Meta ya vigila.)*
2. WHERE el número sigue registrado en la cuenta de A en Meta EL sistema DEBE
   decirle a B que el dueño anterior tiene que soltarlo allí, y NO DEBE
   presentarlo como un fallo de la consola.

### Entidades clave

- **Canal**: un número por el que atiende un cliente. Pertenece a **un
  tenant** y la RLS lo alcanza por `tenant_id`. Lo que cambia es **qué hace
  única a su identidad**: dos canales vivos no pueden compartir número; uno
  vivo y uno desvinculado sí.
- **Credenciales de Meta**: el acceso a una cuenta de WhatsApp Business.
  Pueden ser del canal o del tenant (respaldo). Pertenecen al tenant. Se
  borran cuando el último número de esa cuenta se desvincula.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un número desvinculado en un cliente **se conecta en otro
  cliente de otro partner** y atiende por él.
- **CE-002**: el cliente que lo desvinculó **conserva su historial** con ese
  número, y si lo reconecta, lo recupera.
- **CE-003**: intentar conectar un número vivo en otro sitio produce una
  frase, no un error técnico, y **no altera** al dueño actual.
- **CE-004**: tras desvincular, Meta ya no tiene el número registrado bajo
  nuestra aplicación.
- **CE-005**: desvincular un número **no interrumpe** a otro número de la
  misma cuenta.
- **CE-006**: con Meta caído, desvincular termina en la consola y la ficha
  dice qué falta y cómo terminarlo.

## Fuera de alcance

- **Sacar el número de la cuenta de Meta del partner** — es su activo; lo
  suelta él en su Business Manager.
- **Migrar un número entre cuentas de WhatsApp Business** — es un flujo de
  Meta con sus propias condiciones (PIN, verificación); aquí solo dejamos de
  retener el número.
- **Borrar el historial** del canal desvinculado — se conserva a propósito.

## Supuestos

- Un cliente puede tener números de más de una cuenta de WhatsApp Business;
  «el último de la cuenta» se mide **dentro de ese cliente**.
- Dar de baja el número en Meta es reversible repitiendo el alta, que es lo
  que hoy ya hace conectar.
- Lo que la spec 019 dejó en staging —el endpoint, la acción, la tarjeta, el
  diálogo y el vocabulario de auditoría— se **reutiliza**, no se rehace.
