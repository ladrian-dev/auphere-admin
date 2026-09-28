# Iteración 1 · El alta cabe en tres pasos — evidencia

> **Estado: abierta.** Solo el prototipo (T008) está entregado, y está
> **esperando la aprobación del owner**. Hasta esa fecha no se escribe código.

## Prototipo (T008)

- Story: `packages/ui/src/stories/prototypes/new-client.stories.tsx`
  (`Prototipos/Alta de cliente`), once estados: elegir sin nada marcado ·
  buscando · la búsqueda no encuentra nada · el negocio con cuatro campos · con
  dos · **con catorce (la excepción)** · confirmar · creando · una etapa falla ·
  cupo lleno · móvil.
- Cómo verlo: Storybook sobre Node 24 →
  `http://localhost:6006/?path=/story/prototipos-alta-de-cliente--elegir-plantilla`.
- **Aprobación del owner: pendiente.**

### Lo que el prototipo somete a aprobación

**Tres pasos y cuatro campos**, contra cuatro pasos y veintitrés.

1. **A qué se dedica el negocio es la primera pregunta**, porque la plantilla
   decide el prompt, las herramientas y qué campos existen siquiera.
2. **Nada viene preseleccionado**, y no se puede continuar sin elegir.
3. **Cada tarjeta dice lo que cuesta**: para qué sirve, cuántas habilidades
   enciende y **cuántos datos te va a pedir**. Esa última línea es la que
   convierte trece nombres en una decisión.
4. **Solo se piden los campos que la plantilla no puede rellenar sola**, y la
   pantalla **dice que eso es todo**: «Esto es todo lo que “Barbería /
   Peluquería” necesita para empezar: 4 datos». Sin esa frase, cuatro campos se
   leen como «cuatro, de momento».
5. **La referencia se pliega** bajo opciones avanzadas, derivada del nombre.
6. **Publicar se decide junto al resumen**, con **las dos salidas escritas** en
   vez de una casilla que hay que interpretar.
7. **El paso «Canal» desaparece.**
8. **Una etapa fallida dice lo que ya quedó hecho** («El cliente ya existe y su
   agente está escrito») y ofrece reintentar solo lo que falló.

### La excepción se enseña, no se esconde

`aesthetic_clinic_v1` exige doce campos y no se puede evitar sin tocar su
semilla. **Tiene su propio estado en el prototipo**, con los catorce campos a la
vista. Si el prototipo solo mostrara el caso bonito, la aprobación valdría para
una pantalla que no existe.

### El hueco del Companion

La caja «Cuéntame del negocio» va **arriba del paso 1** y se prototipa en la
iteración 3. En este prototipo se deja marcada con un recuadro punteado: el
sitio queda decidido ahora, para que luego no aparezca donde quepa.

## Medido

| Qué | Resultado |
|---|---|
| Campos en el paso 2, plantilla normal | **4** (nombre, zona horaria, dirección, horario) |
| Campos en el paso 2, tres plantillas | **2** |
| Campos en el paso 2, la excepción | **14** |
| Desbordamiento a 360 px | ninguno — `scrollWidth` 360 sobre `clientWidth` 360 |
| lint · typecheck (`@nexus/ui`) | limpios |

## Suites

Pendientes: la iteración no ha escrito código todavía.

## Paridad

Pendiente. `parity.md` (T001) se cierra al entregar T014–T017.
