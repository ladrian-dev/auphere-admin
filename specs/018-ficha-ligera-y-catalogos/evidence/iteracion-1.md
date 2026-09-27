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
Node del entorno (22.11) y Storybook pide 20.19+ o 22.12+. Salió al quitar la
ruta absoluta de `.claude/launch.json` para poder compartirlo, pero lo que
destapó es que **el repo no decía con qué Node se trabaja**: `engines` ponía
`>=22`, que admite una versión con la que una de sus herramientas no arranca,
y CI pasaba por suerte —`"22"` resuelve a la última 22.x—.

**Decisión del owner (2026-09-27): Node 24 en todo.** `.nvmrc` con 24.14.0,
`engines` a `>=24`, y CI y el flujo de escritorio a `"24"`. Comprobado antes
de commitear sobre Node 24.14: admin 123 tests, escritorio 949, consola 446.
Dos cosas quedan fuera del repo por naturaleza: el defecto de nvm de cada
máquina (`nvm alias default`) y la versión del panel de Vercel.

## Suites (2026-09-27, rama `develop`, Node 24.14)

| Suite | Resultado |
|---|---|
| `apps/console` (vitest) | 77 ficheros, **446 tests** en verde |
| `e2e/record.spec.ts` | **12** en verde (2 saltados: sin credenciales de builder/analyst) |
| `e2e/a11y.spec.ts` | **24** en verde |
| lint · typecheck (consola) | limpios |

**Accesibilidad**: cero violaciones serias o críticas de axe en la ficha
rehecha y en «Agente» fundido, sin scroll horizontal a 360 px ni a 1920 px,
con el texto inflado al 130 %, en español y en inglés.

**Comprobado por mutación**: poner las cuatro lecturas del Resumen en serie
pone rojo su test, con el mensaje que lo explica («¿están en serie?»). Un
test que no sabe fallar no es evidencia.

## Defectos encontrados al implementar

Ninguno estaba en la lista de tareas.

| Qué | Cómo salía | Corregido |
|---|---|---|
| La barra de borrador mandaba a «Ajustes» | Una pestaña que ya no existe | `draft.screen.settings` dice «Agente» |
| El punto de la navegación, igual | `DRAFT_SCREEN_TAB` apuntaba a la pestaña retirada: se habría quedado sin dueño, en silencio | apunta a `agent`, con test |
| Editar el nombre no refrescaba la cabecera | `revalidatePath` sin `"layout"`, y el nombre se pinta en la cabecera y en la miga de pan | revalida la ficha entera, con test |
| «Todavía no tiene nada conectado» | Se callaba que había cuatro conectores esperando, que es lo único accionable del bloque | lo dice |

## Paridad

`parity.md` §Iteración 1, **filas 1–37 cerradas**. Ninguna acción de las que
existían desapareció: las filas 22–23 y 26–35 dicen adónde fue cada una, y
las dos URLs siguen vivas como redirección permanente.

## Lo que queda fuera, a propósito

- Iteraciones 2 (catálogos navegables) y 3 (las palabras), que siguen su
  curso.
- El estado de `/usage`, que es la iteración 3 de la spec 017.
