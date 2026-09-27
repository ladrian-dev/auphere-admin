# Iteración 1 · El Resumen contesta — evidencia

## Prototipo (T007)

- Story: `packages/ui/src/stories/prototypes/client-summary.stories.tsx`
  (`Prototipos/Resumen del cliente`), siete estados: Atendiendo · A medio
  configurar · Sin actividad · Una lectura caída · Sin crédito · Analista ·
  Móvil.
- Cómo verlo: Storybook con Node ≥ 22.12 →
  `http://localhost:6006/?path=/story/prototipos-resumen-del-cliente--atendiendo`.
- **Aprobación del owner: 2026-09-27.**

### Lo que el prototipo fija

1. **«Resumen completo» son cuatro preguntas**, no todos los datos. ¿Atiende?
   · ¿Cuánto consume y cuánto le queda? · ¿Cómo va la conversación? · ¿Qué
   tiene conectado? La cifra en el bloque, el detalle a un clic.
2. **El crédito deja de compartir fila con la puesta en marcha** —ese
   emparejamiento es lo que la hacía pesada— y pasa a ser bloque del Resumen,
   porque le sobrevive: cuando los cuatro pasos están hechos, la puesta en
   marcha desaparece y el crédito sigue importando.
3. **Nombre y zona horaria se editan donde se leen**, y la tarjeta dice en voz
   alta que cambiarlos no crea un borrador.
4. **Sin actividad no es cero**: un cliente recién creado dice que todavía no
   hay datos.
5. **Una lectura caída no tumba la pantalla**: lo dice en su bloque, ofrece
   reintentar, y las otras tres siguen.
6. **El analista lee las mismas cifras** y no ve un control que le
   respondería que no tiene permiso.

### Defectos que el prototipo cazó

- **La pantalla se contradecía en dos líneas**: en «a medio configurar» la
  cabecera decía «falta conectar un canal» y la línea de debajo «WhatsApp
  conectado». Corregido.
- **Un diagnóstico equivocado, anotado porque costó**: una rejilla que no
  aplicaba y un botón que no dejaba de estirarse parecían Tailwind no
  generando clases usadas solo en stories, y esa explicación llegó a
  escribirse en el código. Era falsa: el Storybook llevaba abierto desde el
  día anterior y su escaneo estaba rancio. Reiniciarlo arregló las dos cosas.
  El comentario del fichero ahora lo dice, para que el siguiente mire el
  servidor antes que el código.

### Consecuencia operativa detectada

`preview_start storybook` dejó de funcionar al arrancarlo de nuevo: usa el
Node del entorno (22.11) y Storybook pide 20.19+ o 22.12+. Es consecuencia de
haber quitado la ruta absoluta de `.claude/launch.json` (2026-09-27) para
poder compartirlo. **Pendiente de decisión del owner**: fijar el Node del
equipo en `.nvmrc` y `engines`.

## Suites

_(se rellena al cerrar la iteración)_

## Paridad

_(se rellena al cerrar la iteración: filas 1–37 de `parity.md`)_
