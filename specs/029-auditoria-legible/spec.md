# Especificación: Auditoría que se lee

**Rama**: `develop` (decisión del owner) · **Creada**: 2026-10-03 · **Estado**: Aprobada (propuesta aceptada por el owner)

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`. Solo lectura de un rastro que ya existe |
| **Garantías de aislamiento tocadas** | Ninguna nueva. Los filtros (clientes, equipo, categorías) se leen bajo el partner de la sesión, y un cliente ajeno sigue dando 404 |
| **Nota de KB** | Heurísticas de Nielsen aplicadas a Auditoría (owner, 2026-10-03) · spec 017 R11.5 (filtrar por categoría) |
| **Qué se mide** | Nada nuevo |

## Origen

En la Auditoría de un partner real, 37 de las primeras 50 filas decían «?» («cambió la capacidad ? de Lola Mento: ?.»): las plantillas del vocabulario usan marcadores que el servidor nunca rellenaba. El resto mezclaba referencias técnicas («de panaderia-la-espiga a test»), códigos («a active») y, a la derecha de cada fila, la plantilla cruda («{actor} movió {amount} de {from} a {to}»). El filtro de acción listaba esas mismas plantillas, la persona se escribía de memoria, no había filtro de cliente, los filtros pedían «OK» y «Cargar más» sustituía la lista sin vuelta atrás. La spec 017 pedía filtrar por categoría con nombres de negocio y nunca llegó a la pantalla.

## Escenarios *(obligatorio)*

1. **Frases completas** (P1): cada fila es una frase entera en el idioma del partner, con nombres de clientes, capacidades, modelos, conectores y planes, y estados y roles traducidos. Nunca «?», nunca un código.
2. **Filtros que se eligen** (P1): cliente, persona (el equipo, el Companion y Auphere) y categoría, de listas; periodo de 7, 30 o 90 días o fechas. Se aplican al cambiar, sin botón. «Limpiar filtros» solo cuando hay alguno.
3. **Tabla densa** (P2, owner 2026-10-03: «va a manejar muchos datos»): columnas Fecha («Hoy, 09:12», «Ayer», «1 oct» en la zona horaria de quien mira), Persona (iniciales, o un icono si fue el Companion, Auphere, una clave de API o una máquina), Qué pasó, Cliente (enlace a su ficha) y Categoría (en rojo si no se puede deshacer: borrar un cliente, revocar una clave, quitar a alguien del equipo). Un «⋯» por fila con «Ver solo este cliente», «Ver solo esta persona», «Ver solo esta categoría» y «Abrir la ficha del cliente». En el móvil, persona, cliente y categoría se pliegan dentro de «Qué pasó»: una tabla de 950 px desplazada de lado no se lee.
4. **Repeticiones plegadas** (P2): filas seguidas de la misma persona, acción y cliente en el mismo día se pliegan en una con «N más como esta», que se despliega.
5. **Ver anteriores** (P3): suma la página siguiente debajo de la actual.

## Requisitos *(obligatorio)*

1. Toda plantilla del vocabulario DEBE usar solo marcadores que el servidor rellena. Un test lo comprueba contra la tabla.
2. La API DEBE devolver por fila la categoría, la severidad y qué tipo de autor la escribió, y DEBE aceptar `category` como filtro en la lista y en el CSV.
3. `GET /console/audit/filters` DEBE dar los clientes, las personas y las categorías del partner de la sesión, con nombres de negocio.
4. El CSV DEBE llevar las mismas frases que la pantalla.
5. El filtro por acción concreta deja la pantalla (lo sustituye la categoría), pero `action` sigue en la API para el Companion.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Ninguna fila de la Auditoría muestra «?», una referencia técnica o una plantilla.
- **CE-002**: Filtrar por cliente, persona, categoría o periodo es un solo gesto, sin escribir nada.
- **CE-003**: Una ráfaga de cambios iguales ocupa una fila, no una pantalla.

## Fuera de alcance

- El detalle antes/después de cada cambio: los datos crudos siguen dentro.
- Las filas de tickets y teammates que se escriben fuera del ámbito del partner.
