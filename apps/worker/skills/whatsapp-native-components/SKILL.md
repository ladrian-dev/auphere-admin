---
name: whatsapp-native-components
description: Choose the right WhatsApp native component (reply buttons, list, CTA URL, reactions) vs plain text for outbound messages on the WhatsApp channel. Surface this skill on any intent that produces a customer-facing reply on WhatsApp so the agent picks the format that fits the message instead of defaulting to plain text. The agent calls `response.send_interactive` to emit a structured component; this skill explains which one and when.
version: 1
---

# WhatsApp — componentes nativos vs texto plano

Esta skill es el manual de criterio del agente para decidir QUÉ formato
usar en cada respuesta saliente por WhatsApp. WhatsApp Business API
soporta varios componentes interactivos nativos (botones de respuesta,
listas, CTA URL, reactions). Bien usados aceleran al cliente y reducen
errores; mal usados saturan, generan respuestas absurdas o rompen el
límite de caracteres y Meta los rechaza.

La tool que materializa cada componente es `response.send_interactive`.
Esta skill NO ejecuta — explica el criterio. El runtime se encarga de
serializar al payload de Meta y de degradar a texto plano cuando el
canal no es WhatsApp (p. ej. el chat web del admin).

## Regla maestra

**El componente sigue al mensaje, no al revés.** Primero piensa la
respuesta. Luego decide:

- ¿La decisión del cliente es **binaria/trinaria y cerrada**? → botones.
- ¿La decisión es entre **4–10 opciones discretas**? → list.
- ¿La acción es **abrir un link externo** (checkout, calendario, mapa)? → CTA URL.
- ¿Es un **acuse no crítico** ("vi tu mensaje")? → reaction.
- **Todo lo demás** → texto plano.

Si dudas → texto plano. Un componente forzado se siente peor que un
texto bien escrito.

## Cuándo usar cada componente

### Reply buttons — máximo 3 botones

Úsalo cuando la respuesta correcta del cliente es **una de 2 o 3
opciones cerradas** que ya identificaste por contexto.

Casos típicos:

- Confirmar/cancelar/modificar una reserva ("¿Confirmas?", botones
  `Sí, confirmo` / `Cambiar hora` / `Cancelar`).
- Elegir entre 2-3 servicios del catálogo del tenant ("¿Cuál te
  interesa?", botones `Corte` / `Corte + barba` / `Color`).
- Confirmar consentimiento ("¿Quieres recibir promos?", botones
  `Sí` / `No, gracias`).
- Reanudar / pausar una conversación pausada por el operador.

Reglas técnicas (Meta):

| Restricción | Valor |
|---|---|
| Cantidad de botones | 1–3 |
| Título por botón | ≤ 20 caracteres |
| Texto del body (la pregunta) | ≤ 1024 caracteres |
| Header opcional | ≤ 60 caracteres |
| Footer opcional | ≤ 60 caracteres |
| ID interno por botón | ≤ 256 caracteres |

Cuando llames la tool:

```
response.send_interactive(
  body="Confirmás la reserva del viernes 16:00 con corte fade?",
  buttons=[
    {"id": "confirm", "title": "Sí, confirmo"},
    {"id": "change",  "title": "Cambiar hora"},
    {"id": "cancel",  "title": "Cancelar"},
  ],
)
```

### List — entre 4 y 10 opciones discretas

Úsalo cuando hay **una lista enumerable** que el cliente debe escanear y
elegir UNA. Si son ≤3 opciones → mejor botones. Si son >10 → divide en
categorías o pide al cliente que refine antes.

Casos típicos:

- Horarios disponibles para reservar ("Estas son las horas libres del
  viernes", 6 items con la hora como título).
- Productos del catálogo filtrado por la consulta del cliente
  ("Encontré 8 que matchean tu búsqueda").
- Sucursales / direcciones del tenant.
- Categorías de servicios cuando el agente todavía no sabe qué busca el
  cliente.

Reglas técnicas (Meta):

| Restricción | Valor |
|---|---|
| Cantidad de items | 1–10 (recomendado 3–10 para que valga la pena la lista) |
| Secciones | 1–10 |
| Título por item | ≤ 24 caracteres |
| Descripción por item | ≤ 72 caracteres |
| Body | ≤ 1024 caracteres |
| Botón que abre la lista | ≤ 20 caracteres |

Cuando llames la tool:

```
response.send_interactive(
  body="Estos productos matchean 'sábanas algodón':",
  list={
    "button": "Ver opciones",
    "items": [
      {"id": "p_001", "title": "Sábanas 200 hilos beige", "description": "Queen — $29.990"},
      {"id": "p_002", "title": "Sábanas lino arena",      "description": "King — $54.990"},
      ...
    ],
  },
)
```

Si tienes >10 resultados, NO los truncas en silencio: enseña los 9
mejores + un texto "Tengo más opciones, ¿quieres que te muestre por
color o por tamaño?".

### CTA URL — para abrir un link externo

Úsalo cuando la siguiente acción del cliente requiere salir de
WhatsApp: checkout, agendamiento en plataforma externa, ubicación en
mapas, ver un producto en la web del tenant, descargar una factura.

Casos típicos:

- "Acá puedes pagar tu reserva" + botón `Ir al checkout`.
- "Reserva tu cita en el calendario" + botón `Abrir calendario`.
- "Acá la dirección" + botón `Ver en mapa`.
- "Detalles del producto" + botón `Ver en la web`.

Reglas técnicas (Meta):

| Restricción | Valor |
|---|---|
| Texto del botón | ≤ 20 caracteres |
| URL | https obligatorio, dominio del tenant o whitelisted |
| Body | ≤ 1024 caracteres |

```
response.send_interactive(
  body="Listo, tu pedido quedó armado. Pagas con tarjeta o transferencia:",
  cta_url={"text": "Pagar pedido", "url": "https://vedhome.cl/checkout/abc123"},
)
```

NUNCA inventes una URL. Si no la tienes en un tool_result reciente,
usa texto plano y di que vas a enviarla en cuanto la tengas.

### Reactions — acuses no críticos

Úsalo SOLO como confirmación silenciosa cuando el cliente ya cerró la
conversación y no espera más texto.

Casos típicos:

- Cliente: "Perfecto, te aviso si necesito algo más." → 👍
- Cliente: "Gracias!" → ❤️
- Cliente confirma su asistencia tras un recordatorio → ✅

NO uses reaction como respuesta a una pregunta abierta ni como
sustituto de una explicación. Una reaction sin texto NO cuenta como
respuesta a una consulta — el cliente queda esperando.

## Cuándo NO usar componentes — texto plano gana

Texto plano es la opción por defecto. Componentes son la excepción. NO
uses componentes cuando:

1. **El cliente hizo una pregunta abierta** ("¿qué me recomiendas?",
   "cuéntame más"). La respuesta es texto explicativo. Forzar botones
   ahí se siente robótico.
2. **El cliente está en flujo emocional** (queja, frustración,
   agradecimiento). Texto cálido > botones.
3. **La respuesta cabe en una oración** ("Sí, abrimos hasta las 20h."
   no necesita botón).
4. **Estás escalando a un humano** (escalation-policy aplica). La
   transición debe ser texto cálido, sin "Aceptar/Rechazar".
5. **Pedís información libre** ("¿qué color buscas?", "¿para cuántas
   personas?"). El cliente debe poder escribir libre.
6. **El componente fuerza una decisión que el cliente no está listo
   para tomar**. Mejor explicar primero, decidir después.

## Combinando texto + componente en el mismo turn

El runtime permite que un turn emita texto Y luego una llamada a
`response.send_interactive`. Cuando combinas:

- El texto va PRIMERO como contexto / explicación.
- El componente cierra con la acción esperada del cliente.
- El "body" del componente NO debe repetir literal el texto previo —
  sé conciso ("¿Te lo confirmo así?").

Ejemplo combinado:

```
[texto]   "Encontré 3 cortes que matchean 'fade clásico'. Los dos
           primeros están a $12.000 y el último a $15.000."
[component] response.send_interactive(
              body="¿Cuál te agendo?",
              buttons=[
                {"id":"a","title":"Fade básico"},
                {"id":"b","title":"Fade medio"},
                {"id":"c","title":"Fade premium"},
              ],
            )
```

Si el texto solo ya cierra el turn (el cliente no necesita decidir
nada) → NO añadas componente.

## Degradación a otros canales

El runtime degrada automáticamente cuando el canal NO es WhatsApp:

| Canal | Render del componente |
|---|---|
| `whatsapp` | Componente nativo de Meta. |
| `web` (chat admin / QA Playground) | Renderiza la UI rica desde el UCM. |
| `instagram` (futuro) | Quick replies cuando aplique, texto plano si no. |
| Cualquier otro | Texto plano: el body + lista enumerada de opciones. |

Esto significa que el agente puede emitir el mismo `response.send_interactive`
sin pensar en el canal — el formatter resuelve. La regla del agente
sigue siendo: USA componentes cuando el contenido lo merece, no por la
estética del canal.

## Anti-patterns

### ❌ Botón forzado a una pregunta abierta

> Cliente: "¿Qué me recomiendas para regalar?"
> Agente (mal): botones `Para mujer` / `Para hombre` / `Sorpréndeme`.

El cliente esperaba que el agente PIENSE y explique. La selección
adelantada infantiliza.

### ❌ Lista demasiado larga o cortada en silencio

Si hay 47 productos, NO mandes una lista de 10 y digas "estos son los
disponibles". Pide al cliente que refine ("¿qué color?", "¿qué
tamaño?") y luego responde con la lista corta.

### ❌ CTA URL sin URL real

> Agente: "Acá tu checkout" + `cta_url={"url": "https://example.com"}`

URL inventada. NUNCA. Si no hay URL en un tool_result, usa texto y
explica que la envías cuando esté lista.

### ❌ Reaction como respuesta a pregunta

> Cliente: "¿Me confirmas si tienes la sábana tamaño king?"
> Agente: ❤️ (sin texto)

El cliente queda sin respuesta. Una reaction no responde una pregunta.

### ✅ Componente cuando el cliente lo agradece

> Cliente: "Quiero corte el viernes a las 4."
> Agente (tool: `booking.check_availability`) → libre.
> Agente: "El viernes 16:00 está libre. ¿Te lo confirmo?"
>         + buttons `Sí, confirma` / `Cambiar hora` / `Cancelar`.

La pregunta es cerrada, hay 3 caminos claros, el cliente decide en 1
tap. Ahorra escribir.

## Verificación interna del agente

Antes de emitir la respuesta final, el agente verifica:

1. ¿Es la pregunta del cliente abierta o cerrada?
2. Si cerrada con ≤3 opciones → buttons. Con 4–10 → list. Con >10 →
   pedir refinamiento en texto.
3. ¿La acción del cliente es abrir un link externo y tengo la URL
   real? → CTA URL.
4. ¿Es solo un "vi tu mensaje" sin requerir respuesta? → reaction.
5. Si la respuesta cabe en una oración y no requiere decisión → texto
   plano.
6. ¿Algún límite técnico de Meta se viola (chars, count)? Trunca o
   convierte a list/texto antes de enviar.

Si pasa estas 6 → emite la tool `response.send_interactive` con el
payload que corresponde. Si no — texto plano.
