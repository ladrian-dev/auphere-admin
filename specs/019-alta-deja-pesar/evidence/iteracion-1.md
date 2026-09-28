# Iteración 1 · El alta cabe en tres pasos — evidencia

> **Estado: abierta.** El prototipo (T008) está **aprobado el 2026-09-28**
> («ahora sí lo veo perfecto») tras siete rondas de correcciones. Empieza el
> código.

## Prototipo (T008)

- Story: `packages/ui/src/stories/prototypes/new-client.stories.tsx`
  (`Prototipos/Alta de cliente`), once estados: elegir sin nada marcado ·
  buscando · la búsqueda no encuentra nada · el negocio con cuatro campos · con
  dos · **con catorce (la excepción)** · confirmar · creando · una etapa falla ·
  cupo lleno · móvil.
- Cómo verlo: Storybook sobre Node 24 →
  `http://localhost:6006/?path=/story/prototipos-alta-de-cliente--elegir-plantilla`.
- **Aprobación del owner: 2026-09-28.**

### Las siete rondas, y qué cambió cada una

El prototipo llegó a la aprobación **muy distinto** de como salió. Lo que
cambió, en orden, porque cada una enseña algo:

| # | Lo que dijo el owner | Qué cambió |
|---|---|---|
| 1 | Lo básico aquí, lo avanzado en los ajustes del agente | **Deshizo la excepción**: `aesthetic_clinic_v1` dejó de pedir doce campos y las trece plantillas pasaron a pedir lo mismo. La tarea de los valores por defecto de la semilla entró en alcance |
| 2 | El horario con selector, ¿para qué el campo «Sábados»? | El selector **mató el campo**: existía solo porque el horario era texto libre |
| 3 | Las opciones una al lado de la otra | Dos caminos que se comparan, no una lista que se recorre |
| 4 | Sin inglés, iconos por rubro, horario día a día, «X» en vez de «Abre» | «wellness» y «medspa» salían de las semillas. El horario resumido **mentía por omisión** |
| 5 | Confirmar es insípido, publicar no sirve, cero créditos | **Retiró la historia 4 entera**: elegir publicar no tenía consecuencia |
| 6 | Organiza ese texto | No eran cuatro cosas, eran dos: lo que se crea y lo que faltará. Y esos tres pendientes **son los tres pasos de la ficha** |
| 7 | Cupo lleno debería dejar subir de plan → *me equivoqué, no hay límite* | El estado desapareció entero. Y salió a la luz que el límite **sí existe en el código** |

**Lo que esto dice del prototipo como puerta**: ninguna de las siete se habría
visto leyendo una spec. Se vieron mirando una pantalla.

### Lo que el prototipo fija

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

## Lo que la implementación cambió respecto al prototipo

Tres cosas se midieron al implementar y cambiaron lo escrito:

- **El crédito cero llega más lejos de lo que decía la spec.** El defecto vive
  en `partner_default_client_allocation_tokens`, que lee una sola función
  —`provision_partner_client`— compartida por la consola y por
  `POST /v1/partners/clients`. No había forma de que el cero valiera «solo en
  el alta de la consola» sin duplicar el camino. El owner lo decidió el
  2026-09-28: **en todas partes**, también para los clientes que Amacrux o
  Barber Supply creen por integración. Eso revierte la spec 004 R6, y sus dos
  tests se reescribieron: un cliente nace **con fila y sin crédito**, y
  asignarle crédito basta para que el canal abra — que es la diferencia con el
  corte del 31-ago, donde no había fila que subir.
- **T036 no bloqueaba nada.** Se midió el renderizador contra las trece
  plantillas con solo sus campos obligatorios: **las trece renderizan**. El
  riesgo real es otro y es peor — los opcionales traen defectos concretos
  (24 h de cancelación gratis, 30 % de depósito de cirugía, 100 % de no-show),
  así que un agente recién creado afirma como política de la clínica unas
  condiciones comerciales que nadie le dijo. Queda anotado en T036 para el
  owner.
- **El límite de clientes se retiró como producto, no como guarda.** Migración
  0130: el techo sube a 10 000 y pasa a llamarse guarda. De la consola
  desaparecen el contador «{used} de {max}», el aviso del alta y el estado de
  cupo lleno, y `/clients` deja de llamar a `/console/me` — era lo único que
  leía de ahí.

## Suites

| Suite | Resultado |
|---|---|
| `@nexus/ui` | 168 ✅ |
| consola (vitest) | 505 ✅ |
| consola lint · typecheck | limpios |
| API · `test_client_is_born_with_quota` | 3 ✅ (reescritos) |
| API · `test_seed_templates` | 17 ✅ (uno nuevo: ningún nombre mezcla idiomas) |
| API · ruff | limpio en lo tocado |

## Paridad

Pendiente. `parity.md` (T001) se cierra al entregar T014–T017.
