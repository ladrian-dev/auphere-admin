# Iteración 2 · Los catálogos se navegan — evidencia

> **Estado: abierta.** El prototipo (T017) está entregado y **aprobado el
> 2026-09-28**; el componente y las tres pantallas están en marcha.

## Prototipo (T017)

- Story: `packages/ui/src/stories/prototypes/catalog.stories.tsx`
  (`Prototipos/Catálogo`), nueve estados: Lleno · Buscando · Filtrado por
  categoría · Solo lo activo · Filtro sin resultados · Catálogo vacío · Solo
  lectura · Los tres comparados · Móvil.
- Cómo verlo: Storybook sobre Node 24 →
  `http://localhost:6006/?path=/story/prototipos-catálogo--lleno`.
- **Aprobación del owner: 2026-09-28**, sin cambios pedidos.

### Lo que el prototipo somete a aprobación

**Tres gestos, siempre en el mismo sitio y en este orden**: buscar ·
Activos/Todo · pastillas de categoría. Hoy Habilidades tiene buscador y
grupos, Conectores tiene una rejilla ordenada por urgencia, y Canales no
tiene ninguna de las dos cosas: tres pantallas que hacen lo mismo de tres
maneras distintas.

Lo demás que fija:

1. **El patrón navega; no actúa.** Encender una habilidad, pegar unas
   credenciales y conectar un canal son tres acciones distintas con tres
   diálogos distintos. Cada pantalla se queda con su tarjeta; el patrón solo
   decide cómo se llega hasta ella. Sin esta frontera, el componente acabaría
   sabiendo qué es una habilidad, y entonces ya no sirve para las otras dos.
2. **Las pastillas llevan su cuenta.** Además de filtrar, son el mapa de lo
   que hay dentro sin tener que bajar a mirarlo. Con una sola categoría no
   filtran nada, así que no se pintan.
3. **Vacío por filtro ≠ catálogo vacío.** No se arreglan igual —uno quitando
   el filtro, el otro no se arregla desde aquí—, así que no pueden enseñar el
   mismo cartel. El del filtro **nombra el filtro** y ofrece quitarlo.
4. **Lo que no tiene categoría va a un grupo con nombre propio** («Otras»).
   Inventarle una categoría sería mentir sobre lo que es (R4.5).
5. **Lo que no se puede conectar no está en la lista** (constitución §V).
   Canales enseña WhatsApp; Messenger, Instagram y Telegram no aparecen
   apagados ni prometidos.
6. **Quien no puede escribir busca y filtra igual.** Mirar no es escribir: el
   rol quita los controles, no la navegación.

### La decisión de comportamiento que va con ella

R4.4 pide que el estado viaje en la dirección de la página y que «atrás» haga
lo que el partner espera. Las dos cosas no se consiguen con el mismo
mecanismo, así que el patrón las separa:

| Gesto | Cómo viaja | Por qué |
|---|---|---|
| Pestaña (Activos / Todo) | **enlace** | Es una navegación: compartir el enlace lleva a lo mismo y «atrás» deshace el filtro |
| Pastilla de categoría | **enlace** | Ídem |
| Buscador | escribe en la dirección **sin apilar historia** | Con historia, «atrás» deshace una letra, que no es lo que nadie espera |

Consecuencia para el componente: `CatalogBrowser` recibe la búsqueda
controlada y una función que construye las direcciones; **no importa
`next/navigation`**, que no tiene sitio en `packages/ui`. Quien cablea la URL
es la pantalla.

### Lo revisado con el addon de accesibilidad

| Story | Violaciones |
|---|---|
| Lleno | **0** (26 comprobaciones pasadas) |
| Móvil | **0** |
| Los tres, comparados | **1** moderada, `landmark-unique` |

La única violación es **del montaje de la story, no del patrón**: apilar los
tres catálogos en una página deja dos regiones llamadas «Citas» —Habilidades
tiene un grupo de Citas y Conectores también—, y dos landmarks con el mismo
nombre no son distinguibles. En la aplicación cada catálogo es su propia
pantalla, así que no ocurre. Queda anotado porque **sí ocurriría** si algún
día dos catálogos compartieran página.

Medido además a 360 px: `scrollWidth` 360 sobre `clientWidth` 360 — sin
scroll horizontal.

## Lo entregado (T018–T025)

| Tarea | Qué |
|---|---|
| T018–T019 | Tests en rojo primero: 13 del componente, 10 del cableado a la dirección |
| T020 | `packages/ui/src/components/catalog-browser.tsx` |
| T021 | Habilidades pasa a usarlo, con el filtro por sector conservado |
| T022 | Conectores, con el orden por urgencia **dentro de cada grupo** |
| T023 | Canales, sin enseñar lo que todavía no se puede conectar |
| T024 | `same-in-three.test.tsx`: las tres pantallas montadas y comparadas |
| T025 | axe sobre los tres **con filtro puesto**, y el recorrido de compartir el enlace |

### Dos decisiones que no estaban en el prototipo

1. **Una categoría que la consola no sabe nombrar cae en «El resto».** Los
   conectores traen su categoría del catálogo de Composio, que puede añadir
   una cualquiera. Enseñar su clave interna sería colar jerga en la pantalla;
   juntarlas bajo un nombre honesto dice la verdad sin inventarles una
   categoría (R4.5).
2. **Sin nada que recorrer, la barra no se pinta.** Un buscador y dos
   pestañas sobre una lista vacía son tres controles que no pueden hacer
   nada. Es la misma regla que ya se había aprobado para las pastillas
   —«con una sola categoría no se pintan»— llevada a su conclusión. Se ve en
   Canales de un cliente sin canal: solo el cartel y su botón.

## Suites (2026-09-28, rama `develop`, Node 24.14)

| Suite | Resultado |
|---|---|
| `apps/console` (vitest) | 79 ficheros, **463 tests** en verde |
| `@nexus/ui` (vitest) | 13 ficheros, **162 tests** en verde |
| `e2e/a11y.spec.ts` | **25** en verde, incluida la auditoría nueva de los tres catálogos con filtro |
| `e2e/record.spec.ts` | **13** en verde, incluido «buscar → filtrar → compartir el enlace» |
| lint · typecheck (consola y DS) | limpios |

**Accesibilidad**: cero violaciones serias o críticas en los tres catálogos
con filtro puesto, y sin desbordamiento a 360 px, que es donde la barra de
tres gestos tiene que envolver.

**Comprobado por mutación**, porque un test que no sabe fallar no es
evidencia:

| Mutación | Qué se puso rojo |
|---|---|
| El componente nombra una habilidad en un comentario | «no sabe qué es una habilidad, un conector ni un canal» |
| `catalogHref` reconstruye la dirección desde cero | 3 casos, incluido el del filtro por sector |
| Conectores pone su propia etiqueta de buscador | «el buscador se llama igual en los tres» |

**Una caída en la corrida completa, y no es del cambio**: `client view
/knowledge` agotó los 120 s del `goto` dentro del barrido entero, y vuelve a
pasar sola en 6,6 s. Es el servidor de desarrollo compilando esa ruta en
frío —sus respuestas se ven en 15-20 s en el registro—, no una regresión:
esta iteración no toca Conocimiento.

## Paridad

Filas 38–60 de `parity.md` cerradas. Tres cambian de «se conserva» a «se
mueve», y quedan dichas en su fila:

- **39 y 47 · los contadores.** Pasan a ser el del patrón, igual en los tres.
  Dice **más** que el de antes: cuántos hay en total, que es lo que «1 de 3
  encendidas» se callaba cuando el filtro escondía veinte.
- **41 · el filtro por sector.** Se conserva, dentro del patrón y no al lado:
  ensancha el catálogo en vez de estrecharlo, así que no es una pastilla.
  `catalogHref` tiene un test dedicado a que no lo borre al teclear.

## Lo que queda fuera a propósito

- **Renombrar «Capacidades» → «Habilidades» e «Integraciones» → «Conectores»**
  es la iteración 3. El prototipo ya usa las palabras nuevas porque es copy de
  demostración, pero el renombrado de verdad va después, o el copy se toca dos
  veces.
