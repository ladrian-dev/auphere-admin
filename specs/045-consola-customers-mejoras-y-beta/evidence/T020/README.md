# T020 — Panel, Bandeja y Consumo del diseño

Capturas del 2026-10-22 contra la consola local, con la persona de Peluquería
Cultor que siembra `apps/api/scripts/dev_seed_reservas_demo.py` (seis
conversaciones atendidas, una que espera a una persona; saldo y gasto del mes).
1440 × 900 en claro y oscuro; `panel-390` es un teléfono de 390 px. Se tomaron
en la rama que lleva también la 043, así que el lateral enseña «Reservas» y el
Panel su bloque: lo de la 045 es todo lo demás.

| Fichero | Qué enseña |
|---|---|
| `panel-*` | «Hola, Valeria» bajo el negocio, la tarjeta destacada de conversaciones, «Cubre N de M días del mes», la gráfica con su media, el bloque de Reservas (spec 043) y lo que necesita atención |
| `bandeja-*` | La Bandeja que nombra WhatsApp, con el motivo del agente y «Espera hace…» en la fila |
| `bandeja-espera-*` | La conversación que espera: aviso con el motivo, «Devolver al agente» / «Tomar el control», resumen y actividad |
| `consumo-*` | «Te alcanza hasta el …» primero, gasto del mes al ritmo actual, gasto por día y el detalle técnico agrupado |

## Gates de UI del workspace

- **Pase vivo (axe WCAG 2.2 AA + desbordes)**: `apps/console/e2e/lite.spec.ts`
  sobre `/`, `/inbox`, `/usage` y `/account/phones` (y Reservas, ver la T060
  de la 043), es/en × claro/oscuro, a 360 px con texto un 30 % más largo y a
  1920 px, más «la Bandeja abre una conversación»: **45/45** con esta persona.
- **Lo que destapó y se arregló en este cambio**:
  - el hilo de una conversación sin ningún enlace no se podía desplazar con el
    teclado (axe `scrollable-region-focusable`, serio) → el hilo toma el foco,
    con anillo visible;
  - con un solo agente, «Gasto del mes» ocupaba dos filas y quedaba vacía →
    sin desglose por agente es una tarjeta más de la primera fila y la gráfica
    ocupa el ancho (pruebas en `lite-panel.test.tsx`).
- **Cinco estados**: `lite-panel.test.tsx`, `lite-usage.test.tsx`,
  `design-045.test.tsx` y `loading.test.tsx` (esqueletos con las medidas
  finales en `/` y `/usage`).
- **Tokens**: sin hex, rgb ni paletas de Tailwind en lo tocado.
