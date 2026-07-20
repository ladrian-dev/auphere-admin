# New Air Climatización — plantillas de WhatsApp

Las cuatro plantillas que sustituyen a los textos libres que hoy envía el
workflow de n8n vía UltraMsg.

## Antes de subirlas

**Variables nombradas, no posicionales.** El servicio de envío rechaza
`{{1}}` / `{{2}}` (ver `services/broadcasts.py`, `_POSITIONAL_VAR_RE`).
Meta soporta ambas; nosotros solo las nombradas. Si se suben
posicionales hay que rehacerlas y volver a esperar la aprobación.

**Categoría: MARKETING.** Aunque el mensaje se lea como un aviso de
servicio, promueve la contratación de una mantención. Declararlo como
UTILITY para pagar menos es motivo de rechazo o de recategorización
silenciosa por parte de Meta. Implica coste por conversación de
marketing y que aplica el opt-out de marketing.

**Idioma: `es`.** No `es_CL` — Meta no lo tiene; `es` cubre Chile.

Las cuatro son solo `BODY`: sin header, sin media, sin footer. Las dos
variables son las mismas en todas.

| Variable | Origen en la hoja | Ejemplo |
|---|---|---|
| `{{nombre}}` | `Nombre del cliente` / `Nombre del Cliente` | `Juan Pérez` |
| `{{fecha}}` | `Fecha` | `15/01/2026` |

Ojo con la capitalización de la columna: la hoja de instalaciones usa
`Nombre del cliente` y la de mantenciones `Nombre del Cliente`. El
workflow ya lo distingue; conviene no "arreglarlo" en un solo sitio.

---

## 1. `newair_instalacion_recordatorio`

A los 5 meses y 15 días de la instalación.

```
Hola {{nombre}}, ¿cómo estás?

Te escribimos desde New Air Climatización 👋

Queremos recordarte que el día {{fecha}} realizamos la instalación de tu equipo, por lo que en aproximadamente 15 días se cumplirán 6 meses desde esa fecha.

Para mantener su correcto funcionamiento, es recomendable programar la mantención preventiva con anticipación.

¿Te gustaría que coordinemos una fecha desde ya?
```

## 2. `newair_instalacion_vencida`

A los 6 meses de la instalación.

```
Hola {{nombre}}, ¿cómo estás?

Te escribimos desde New Air Climatización 👋

El día {{fecha}} realizamos la instalación de tu equipo, y ya se han cumplido 6 meses desde entonces.

Es muy importante realizar la mantención preventiva para evitar fallas, mantener la eficiencia y prolongar la vida útil del sistema.

¿Te ayudamos a agendar la mantención lo antes posible?
```

## 3. `newair_mantencion_recordatorio`

A los 5 meses y 15 días de la última mantención.

```
Hola {{nombre}}, ¿cómo estás?

Te escribimos desde New Air Climatización 👋

Queremos recordarte que el día {{fecha}} realizamos la mantención de tu equipo, por lo que en aproximadamente 15 días se cumplirán 6 meses desde esa fecha.

Para mantener su correcto funcionamiento, es recomendable programar la próxima mantención preventiva con anticipación.

¿Te gustaría que coordinemos una fecha desde ya?
```

## 4. `newair_mantencion_vencida`

A los 6 meses de la última mantención.

```
Hola {{nombre}}, ¿cómo estás?

Te escribimos desde New Air Climatización 👋

El día {{fecha}} realizamos la última mantención de tu equipo, y ya se han cumplido 6 meses desde entonces.

Es muy importante realizar una nueva mantención preventiva para evitar fallas, mantener la eficiencia y prolongar la vida útil del sistema.

¿Te ayudamos a agendar la mantención lo antes posible?
```

---

## Recomendación: añadir un botón de respuesta rápida

Las cuatro terminan en pregunta y hoy el cliente tiene que escribir a
mano. Un botón de tipo *Quick Reply* con el texto **"Sí, quiero
agendar"** sube la conversión y, al responder, abre la ventana de 24
horas — dentro de la cual las respuestas ya no cuestan por plantilla.

No añade trabajo de nuestro lado: el envío no cambia, el botón es parte
de la plantilla. Sí conviene decidirlo **antes** de mandarlas a
aprobación, porque añadirlo después es volver a esperar el ciclo.

Si se añade, alguien tiene que atender las respuestas — hoy este número
no tiene agente conectado. Opciones: que lleguen a la bandeja del panel,
o conectar un agente más adelante.

## Textos congelados

Una vez aprobadas, el texto **no se puede editar**. Cambiarlo es crear
una plantilla nueva y volver a pasar por aprobación. Los nodos Code de
n8n dejarán de construir el texto (solo eligen qué plantilla toca), así
que el contenido vive aquí y en Meta, en ningún otro sitio.
