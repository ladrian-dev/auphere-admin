# Especificación: la consola customers — mejoras del diseño y la Beta a la vista

**Rama**: `045-consola-customers-mejoras-y-beta` · **Creada**: 2026-10-22 · **Estado**: Aclarada (decisiones del 2026-10-22 en §Clarifications)

**Entrada**: diseño «Consola Customers.dc.html» (Claude Design, proyecto
`e443cbee-f802-4f49-8ec6-422e1d8d97e6`, descargado el 2026-10-22) y decisiones
del owner del mismo día. Ver §Origen.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. Las mismas personas de cliente (web y app) por la misma puerta; no entra nada nuevo de fuera |
| **Garantías de aislamiento tocadas** | **1** (RLS: la Bandeja, sus contadores y el push leen columnas nuevas de `conversations`, todas bajo la RLS del cliente) · **8** (sin cambio de regla: ninguna herramienta nueva). **Eje que se estrecha**: lo que una persona del cliente ve de las conversaciones de su propio número — solo las que el agente atiende o atendió. Lleva su test de barrido |
| **Nota de KB que la justifica** | `[[research/2026-10-22-reservas-y-consola-customers/_index]]` (decisiones 1 y reglas de la Bandeja) · `[[ADR-041-consola-lite-del-cliente-final]]` |
| **Qué se mide** | Nada nuevo. Ningún modelo ni herramienta de pago |

> La superficie es la que ya está abierta (`0`). El valor cabe entero en la
> consola del cliente y en su API, que comparte con la app.

## Origen

La consola del cliente (spec 030, «lite») lleva en producción desde el
2026-10-10. El 2026-10-22 llegó su rediseño, «Consola Customers», con cuatro
pantallas (Panel, Bandeja, Reservas, Consumo). Reservas va en su propia spec
(043). Esta recoge lo demás:

1. **Las mejoras visuales** del Panel, la Bandeja y el Consumo, hechas con los
   tokens de `@nexus/ui`, sin un solo color escrito a mano.
2. **La regla de la Bandeja**, acordada en el diseño: la Bandeja no es un espejo
   del WhatsApp del negocio. Hoy un número que el agente tiene silenciado (spec
   024, números permitidos) crea conversación, cuenta como no leído y aparece;
   también las conversaciones que abre un envío del sistema y que nadie contestó.
3. **La fase Beta a la vista**, como ya está en la consola de partners. Hoy la
   del cliente enseña «lite», una palabra interna.
4. **Los campos de API** que piden las mejoras y que la app (spec 044) también
   usa: el motivo y la espera de cada conversación que espera a una persona,
   «te alcanza hasta» del saldo, el horario del negocio y el silencio de avisos
   fuera de horario.

Medido en el código el 2026-10-22:

- `services/inbox_view.py` lista toda conversación del cliente salvo las del
  Playground. El despachador del worker crea o actualiza la conversación de un
  número silenciado y marca su mensaje `skipped_reason = 'not_admin'`; la
  Bandeja no mira esa marca.
- `last_inbound_at` sube también con un mensaje silenciado, y el «no leído» se
  calcula con él.
- El Panel cuenta «esperan» con una ventana de 7 días (`escalated_recent`); la
  Bandeja, sin ventana. Pueden dar dos números distintos para lo mismo.
- La fila de la Bandeja no trae el motivo ni desde cuándo espera; la app lo pide.
- El saldo trae `days_left`, no la fecha hasta la que alcanza ni cuántos días le
  quedan al mes.
- `/console/lite/me` no trae el horario del negocio, y el horario se guardaba en
  tres formas (arreglado en el bug `horario-del-negocio-en-tres-formas`).

## Clarifications

### Session 2026-10-22

Luis no está para aprobar pasos intermedios; las decisiones son de esta sesión,
con su razón, y se revisan al final.

- Q: ¿«Comprar saldo» y «Alertas de consumo» del diseño? → A: **No entran.**
  Decisión del owner: saldo de solo lectura (spec 030 C2 sigue en pie). Los
  avisos de saldo bajo siguen por correo y WhatsApp.
- Q: ¿Pestañas por canal (WhatsApp, Instagram, Messenger) y reparto del gasto
  por canal? → A: **No entran.** Solo se usa WhatsApp por Meta: una pestaña o un
  reparto de un solo canal no dice nada (constitución §V, la ausencia se diseña).
  La intro de la Bandeja nombra solo WhatsApp.
- Q: ¿Pasar una conversación a otro agente («Asignada a…»)? → A: **No entra**
  (spec 030: un número es de un agente; el traspaso es entre agente y persona).
- Q: ¿Chips combinables («No leídos» + «Necesita humano» + «Resueltos»)? → A:
  **Se mantiene un filtro único** (Todas · Sin leer · Esperan · Resueltas), el
  mismo que la app. Combinar dos filtros da listas que nadie pidió y dos
  semánticas distintas entre web y app.
- Q: ¿«customers» o «Beta» junto al logotipo? → A: **«Beta»**, el mismo
  componente y tono que la consola de partners, con su propia pista para el
  cliente. «lite» desaparece de la pantalla (era jerga interna). No caben dos
  píldoras en el lateral sin cortar el logotipo, y la que le dice algo al
  negocio es la fase.
- Q: ¿Qué es «una conversación que el agente atiende o atendió»? → A: la que
  tiene **al menos un mensaje del contacto que el agente pudo atender**: un
  mensaje entrante que la puerta de números permitidos no silenció. Se guarda en
  la conversación la primera vez (`attended_at`) y la última
  (`last_attended_inbound_at`). Lo que el sistema envía solo (un recordatorio,
  un envío masivo) no la hace visible hasta que el contacto contesta.
- Q: ¿«Desde que escriben»? → A: el hilo de la Bandeja empieza en `attended_at`:
  lo anterior (mensajes silenciados de cuando el número no estaba permitido,
  envíos del sistema que nadie contestó) no se enseña. Un mensaje silenciado
  **después** tampoco: no se enseña, no cuenta como no leído y no avisa.
- Q: ¿El «no leído» y el orden? → A: el no leído compara la lectura con
  `last_attended_inbound_at`, no con `last_inbound_at` (que sigue siendo la
  ventana de 24 h de WhatsApp, que Meta abre con cualquier mensaje).
- Q: ¿El «esperan» del Panel? → A: **el mismo número que la Bandeja**, de la
  misma función. Se quita la ventana de 7 días del Panel del cliente (el Inicio
  del partner no cambia).
- Q: ¿Las conversaciones que ya existen? → A: una migración rellena
  `attended_at` y `last_attended_inbound_at` desde los mensajes. Las que nunca
  tuvieron un entrante atendido quedan fuera de la Bandeja desde el despliegue.
- Q: ¿«Silenciar fuera del horario del negocio»? → A: un ajuste **por
  teléfono**, encendido por defecto. Fuera del horario del perfil del negocio no
  sale el push de los avisos que no son urgentes; «una conversación espera a una
  persona» sí sale siempre. Sin horario configurado, no se silencia nada (no se
  puede saber qué es fuera de horario).
- Q: ¿El horario del negocio en `/me`? → A: sí, la forma canónica del bug
  `horario-del-negocio-en-tres-formas`, más la zona horaria y una etiqueta ya
  escrita. Se edita en la web desde Reservas (spec 043); la app solo lo lee.
- Q: ¿«Cubre N de 26 días del mes»? → A: la API da `month_days_left` (días que
  quedan del mes, hoy incluido, en la zona del negocio) y `runs_out_on` (la fecha
  hasta la que alcanza el saldo al ritmo de los últimos 7 días). La pantalla
  compone la frase.
- Q: ¿El papel «Propietaria»? → A: **no entra** (spec 030: no hay papeles
  dentro del cliente).
- Q: ¿El detalle técnico de Consumo por canal × (mensajes, modelo,
  multimedia)? → A: **se agrupan los medidores en esas tres familias**, una
  sola fila de canal (WhatsApp), con el total; el CSV no cambia.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — La Bandeja solo enseña lo que atiende el agente (Prioridad: P1)

Valeria abre la Bandeja y ve las conversaciones que su agente atiende o
atendió. Si su agente solo responde a ciertos números, ve solo esos, y desde que
escribieron. Los contadores y los avisos del teléfono cuentan lo mismo que ve.

**Por qué esta prioridad**: hoy la Bandeja enseña chats que el agente nunca
tocó, cuenta no leídos que no lo son y puede avisar por ellos: rompe la promesa
de la pantalla.

**Prueba independiente**: con un agente en modo números permitidos, un mensaje
de un número no permitido no aparece, no cuenta y no avisa; uno de un número
permitido sí, con su hilo desde que escribió.

**Escenarios de aceptación**:

1. **Dado** un agente con números permitidos, **cuando** escribe un número que
   no lo está, **entonces** la Bandeja no lo lista, los contadores no cambian y
   no sale ningún aviso.
2. **Dado** un número permitido que antes escribió sin estarlo, **cuando**
   vuelve a escribir, **entonces** aparece y su hilo empieza en ese mensaje.
3. **Dado** un recordatorio enviado por el sistema a un contacto que nunca
   escribió, **entonces** esa conversación no aparece hasta que conteste.
4. **Dado** una conversación visible, **cuando** llega un mensaje silenciado,
   **entonces** no se enseña, no la marca como no leída y no avisa.

---

### Historia 2 — El Panel, la Bandeja y el Consumo del diseño (Prioridad: P1)

Valeria entra y lo primero que ve es su nombre, lo que necesita su atención y
las cifras del negocio, con el aspecto del diseño nuevo. En la Bandeja, las que
esperan dicen por qué y desde cuándo. En Consumo, el saldo responde primero
«hasta cuándo alcanza».

**Por qué esta prioridad**: es la cara del producto en Beta; las cifras ya
existen, falta que se lean de un vistazo.

**Prueba independiente**: con datos sembrados, cada pantalla enseña los cinco
estados (cargando, vacío, error, parcial, ideal) y las cifras del diseño.

**Escenarios de aceptación**:

1. **Dado** un saldo con ritmo de gasto, **cuando** abro el Panel o el Consumo,
   **entonces** veo «Cubre N de M días del mes» y la fecha hasta la que alcanza,
   con una barra cuyo tono avisa a menos de 14 días y alarma a menos de 7.
2. **Dado** una conversación que espera a una persona, **cuando** la veo en la
   lista, **entonces** la fila dice el motivo del agente y cuánto lleva
   esperando.
3. **Dado** que la API falla, **entonces** cada bloque dice que no se pudo leer;
   nunca enseña un cero que no es.

---

### Historia 3 — La fase Beta, a la vista (Prioridad: P2)

El negocio ve que la consola está en Beta, como lo ven los partners.

**Prueba independiente**: el lateral de una persona de cliente enseña «Beta»
con su pista; no enseña «lite».

**Escenarios de aceptación**:

1. **Dado** una persona de cliente, **cuando** entra, **entonces** ve «Beta»
   junto al logotipo, con la pista para el negocio.
2. **Dado** el lateral plegado, **entonces** la insignia se oculta igual que la
   del partner.

---

### Historia 4 — La app recibe lo que necesita (Prioridad: P2)

La app enseña el motivo y la espera, «te alcanza hasta», el horario del negocio
y silencia los avisos que no son urgentes fuera de horario.

**Prueba independiente**: contra el contrato de `contracts/lite-api.md`, con el
`openapi.json` exportado.

**Escenarios de aceptación**:

1. **Dado** el ajuste «silenciar fuera de horario» encendido, **cuando** llega
   un mensaje para la persona fuera de horario, **entonces** no sale el push; si
   la conversación espera a una persona, sí.

---

### Casos límite

- **Sin horario del negocio**: `/me` devuelve `business_hours: null`; el
  silencio no silencia nada y la app no enseña la pista.
- **Sin gasto en 7 días**: `runs_out_on: null` (no se puede proyectar);
  `month_days_left` sigue saliendo.
- **Saldo agotado**: `runs_out_on` es hoy; la barra va en tono de alarma.
- **Conversación en espera sin motivo** (escalado antiguo sin `reason`): la fila
  dice «Necesita a una persona» sin motivo; la espera sale igual.
- **El cliente no tiene Bandeja**: el Panel no enseña «esperan» (como hoy).
- **Lateral plegado**: la insignia Beta se oculta, como la del partner.

## Requisitos *(obligatorio)*

### Requisito 1 — Qué conversaciones existen para la Bandeja

**Historia de usuario:** Como persona del negocio, quiero ver solo las
conversaciones que mi agente atiende o atendió, para que la Bandeja diga la
verdad de mi trabajo.

#### Criterios de aceptación

1. WHEN llega un mensaje del contacto que la puerta de números permitidos no
   silencia THEN el sistema DEBE marcar la conversación como atendida
   (`attended_at` la primera vez) y anotar ese momento como el último entrante
   atendido.
2. IF un mensaje entrante queda silenciado (`skipped_reason = 'not_admin'`) THEN
   el sistema NO DEBE cambiar `attended_at` ni `last_attended_inbound_at`.
3. La Bandeja (lista, búsqueda, filtros, contadores y detalle) DEBE incluir solo
   conversaciones con `attended_at`; una conversación sin él DEBE responder 404
   como si fuera de otro cliente.
4. El hilo DEBE empezar en `attended_at` y NO DEBE incluir mensajes entrantes
   silenciados.
5. «Sin leer» DEBE compararse con `last_attended_inbound_at`.
6. La vista previa de la fila DEBE ser el último mensaje que el hilo enseña.
7. WHEN se despliega THEN una migración DEBE rellenar las dos columnas desde los
   mensajes existentes, y repetirla NO DEBE cambiar nada.

### Requisito 2 — Contadores y avisos con la misma regla

#### Criterios de aceptación

1. Los contadores de la Bandeja (`/inbox/counts` y los de la página) y la
   insignia del icono de la app DEBEN contar solo conversaciones visibles.
2. El «esperan» del Panel del cliente DEBE ser el mismo número que el de la
   Bandeja.
3. IF el mensaje está silenciado THEN el sistema NO DEBE encolar el aviso
   «mensaje nuevo donde respondes tú», ni la campana ni el push.
4. Antes de enviar un push de la Bandeja, el sistema DEBE comprobar que la
   conversación sigue siendo visible.

### Requisito 3 — Motivo y espera

#### Criterios de aceptación

1. WHERE la conversación espera a una persona, la fila de la lista DEBE traer
   `waiting.reason` (el motivo del último escalado, o `null`) y `waiting.since`
   (cuándo se escaló).
2. El detalle DEBE traer `waiting_since` junto a `waiting_reason`.

### Requisito 4 — El saldo responde «hasta cuándo»

#### Criterios de aceptación

1. El saldo de `/home` y de `/usage/summary` DEBE traer `month_days_left` (días
   del mes que quedan, hoy incluido, en la zona horaria del negocio).
2. El saldo DEBE traer `runs_out_on`: la fecha local en que se acaba al ritmo de
   los últimos 7 días, o `null` si no hay gasto o no hay saldo asignado.
3. La barra del saldo DEBE ir en tono de alarma con menos de 7 días, de aviso con
   menos de 14 y primario si no; con tokens, nunca colores escritos a mano.

### Requisito 5 — El horario del negocio y el silencio fuera de horario

#### Criterios de aceptación

1. `/console/lite/me` DEBE traer `business_hours` (forma canónica, o `null`),
   `business_hours_label` (la frase ya compuesta, o `null`) y `timezone`.
2. Los avisos del teléfono DEBEN aceptar `quiet_outside_hours` (por defecto
   `true`).
3. WHILE `quiet_outside_hours` está encendido y es fuera del horario del negocio,
   el sistema NO DEBE enviar el push de un aviso no urgente; DEBE marcar la
   entrega como `skipped` con motivo `quiet_hours`.
4. «Una conversación espera a una persona» DEBE salir siempre.
5. IF el negocio no tiene horario THEN el sistema NO DEBE silenciar nada.

### Requisito 6 — La pantalla del diseño

#### Criterios de aceptación

1. El Panel DEBE abrir con el nombre de la persona («Hola, Valeria»), la línea
   del negocio y lo que necesita su atención, y las cifras de conversaciones
   (tarjeta destacada con su curva), esperan y saldo, con la gráfica de
   conversaciones por día y su media.
2. La Bandeja DEBE nombrar solo WhatsApp, enseñar en la fila el motivo y la
   espera, y conservar todo lo de la spec 030 (tomar el control, devolver,
   resolver, etiquetas, notas, respuestas guardadas, adjuntos, tiempo real).
3. El Consumo DEBE empezar por el saldo y su «alcanza hasta», y agrupar el
   detalle técnico en mensajes, uso del modelo y multimedia.
4. NO DEBE haber «Comprar saldo», «Alertas de consumo», pestañas de canal, ni
   Instagram, Messenger o Reserve with Google en ninguna pantalla.
5. Cada bloque que lee datos DEBE pintar sus cinco estados: cargando (esqueleto
   con las medidas finales), vacío, error, parcial e ideal.
6. Todo color, espacio, radio y tipo DEBE salir de los tokens de `@nexus/ui`.

### Requisito 7 — Beta

#### Criterios de aceptación

1. WHERE la persona es de un cliente, el lateral DEBE enseñar la insignia «Beta»
   con el mismo componente y tono que la de partners y una pista propia.
2. El lateral NO DEBE enseñar «lite».

### Entidades clave

- **Conversación** (`conversations`, ya existe, RLS por `tenant_id`): gana
  `attended_at` y `last_attended_inbound_at`.
- **Teléfono del cliente** (`client_phones`, ya existe, RLS por `tenant_id`):
  gana `quiet_outside_hours`.

## Criterios de éxito *(obligatorio)*

- **CE-001**: ningún mensaje de un número no permitido aparece, cuenta o avisa
  (barrido en `tests/isolation/`).
- **CE-002**: el «esperan» del Panel, el de la Bandeja y la insignia de la app
  son el mismo número con los mismos datos.
- **CE-003**: las tres pantallas pasan axe (WCAG 2.2 AA) y no desbordan a 360 y
  1920 px, en claro y oscuro, en español e inglés.
- **CE-004**: ningún color escrito a mano en el código nuevo (lint de
  `@nexus/ui` en verde).

## Fuera de alcance

- Reservas en el Panel, la Bandeja y la campana — spec 043.
- Papeles dentro del cliente — spec 030 los descartó.
- Comprar saldo, alertas de consumo — decisión del owner.
- Canales que no son WhatsApp por Meta — no existen.
- El Inicio del partner — no cambia; su «esperan» sigue con su ventana.

## Supuestos

- La app (spec 044) consume estos campos desde `openapi.json`; el contrato se
  congela antes de implementar.
- `skipped_reason = 'not_admin'` es la única marca de silencio de la puerta de
  números permitidos (spec 024).
