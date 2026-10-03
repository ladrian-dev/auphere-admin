# Fase 0 · Investigación

Seis decisiones. Ninguna se toma por gusto: todas salen de mirar lo que ya
existe en el repo, porque esta spec mueve cosas de sitio y lo caro sería
construir de nuevo algo que ya está.

---

## 1. El Resumen no necesita un endpoint nuevo

**Decisión**: el Resumen se arma en el BFF de la consola con **cuatro lecturas
que ya existen**, pedidas en paralelo, cada una con su propio fallo.

**Por qué**: se comprobó contra la API antes de escribir la spec.

| Bloque | Lectura que ya existe | Qué trae |
|---|---|---|
| ¿Atiende? | `GET /console/clients/{ref}` | estado, salud, `setup`, `quota` (spec 017) |
| ¿Cuánto consume? | `GET /console/usage?client={ref}` | `month` (unidades, tope, porcentaje, proyección, días) y totales por medidor |
| ¿Cómo va la conversación? | `GET /console/clients/{ref}/conversations/stats` | conversaciones, escaladas, mensajes fallidos |
| ¿Qué tiene conectado? | `GET …/channels` + `GET …/integrations` | estado de instalación por cliente |

**Alternativas descartadas**:

- **Un endpoint `GET /console/clients/{ref}/summary` que lo junte todo.** Sería
  una capa nueva sobre datos que ya se leen, y tendría un defecto de diseño:
  un fallo en cualquiera de las cuatro fuentes tumbaría el Resumen entero. La
  spec pide justo lo contrario (R1.6). Pidiéndolas por separado, **el
  aislamiento de fallos sale gratis** en vez de haber que programarlo.
- **Pedirlas en serie.** Multiplicaría por cuatro la espera sin ganar nada:
  ninguna depende del resultado de otra.

**Consecuencia para R1.8**: son cuatro lecturas **por ficha**, no por fila ni
por cliente del partner. La lista de clientes no las hace.

---

## 2. El patrón de catálogo es un componente del sistema de diseño

**Decisión**: se construye **un** componente en `packages/ui` que resuelve
buscar, separar lo activo de lo disponible, filtrar por categoría y agrupar; y
las tres pantallas (Habilidades, Conectores, Canales) le pasan sus elementos y
sus categorías.

**Por qué**: la spec pide explícitamente que los tres se recorran con el mismo
gesto (R4.6). Con tres copias, la tercera ya no se parece a la primera —es lo
que pasó con Herramientas y Habilidades antes de la spec 017—. Y el sistema de
diseño ya aloja piezas con forma de producto (`draft-bar`, `checklist`,
`stepper`), así que no es un cuerpo extraño.

**Lo que ya está hecho y se reutiliza**: la pantalla de Capacidades ya tiene
buscador, contador con `aria-live`, agrupación por secciones y vacíos
distinguidos. El componente nace de extraer eso, no de inventarlo. Lo que le
falta al patrón de hoy son **las pestañas** (activo / todo) y **el filtro por
categoría**.

**Alternativas descartadas**:

- **Un componente por pantalla.** Barato hoy, caro en la tercera.
- **Una tabla con filtros genérica** (`data-table` ya existe): es para filas y
  columnas. Un catálogo se lee como tarjetas agrupadas, no como una tabla.

---

## 3. Se renombra lo que se ve, no las direcciones

**Decisión**: «Capacidades» → **Habilidades** e «Integraciones» → **Conectores**
en el texto visible, en los dos idiomas. Las rutas siguen siendo
`/clients/{ref}/capabilities` y `/clients/{ref}/integrations`, y las claves de
copy siguen siendo `cap.*` e `int.*`.

**Por qué**: el renombrado es un cambio de vocabulario para el partner, no de
arquitectura. Cambiar las rutas obligaría a otra ronda de redirecciones —la
spec 017 acaba de dejar `/tools` y `/skills` redirigiendo a `/capabilities`— y
la única ganancia sería estética, en una cadena que nadie escribe a mano.

**Detalle que ayuda**: con el nombre nuevo, la redirección `/skills →
/capabilities` **gana sentido** en vez de perderlo: quien escriba «skills»
aterriza en la pantalla que ahora se llama Habilidades.

**Alternativas descartadas**:

- **Renombrar rutas y añadir redirecciones**: dos redirecciones encadenadas
  (`/tools → /capabilities → /skills`) por una palabra.
- **Renombrar también las claves de i18n**: cientos de líneas de diff que no
  cambian ni un píxel.

---

## 4. Fundir pestañas: adónde va cada dirección

**Decisión**:

| Hoy | Después | Cómo |
|---|---|---|
| `/clients/{ref}/settings` (datos del cliente) | Bloque editable dentro del Resumen | Redirección permanente a la ficha |
| `/clients/{ref}/agent/settings` (ajustes del agente) | Dentro de `/clients/{ref}/agent` | Redirección permanente a `/agent` |

**Por qué el punto de borrador sigue apuntando bien**: hoy la marca distingue
`settings` (ajustes del agente) de `client` (datos del cliente) porque eran dos
pestañas. Al fundirse, los cambios de ajustes del agente marcan **«Agente»**,
que es donde ahora viven. Y editar el nombre del cliente **no** entra en el
borrador —nunca lo hizo—, así que el Resumen no gana una marca que no le toca
(R2.4).

**Riesgo identificado y cómo se cierra**: la iteración 1 de la spec 017 separó
estas dos pantallas a propósito, porque compartir una hacía que el punto
señalara la pantalla que no había cambiado. Esto **no lo deshace**: aquella
separación era entre *datos del cliente* y *ajustes del agente*; esta fusión es
entre *dos mitades del agente*. La distinción que importaba sigue en pie.

---

## 5. La tarjeta de puesta en marcha se parte en dos ideas

**Decisión**: separar **«qué falta»** (el recorrido de cuatro pasos y el
siguiente, con su acción) de **«cuánto crédito hay»**, que es un bloque del
Resumen y no un paso de configuración.

**Por qué**: hoy la tarjeta mezcla tres cosas —un recorrido, una instrucción y
una cifra de consumo— y pide tres lecturas distintas en un solo bloque. El
crédito no es un paso: es un estado que sigue importando cuando la puesta en
marcha ha terminado, y por eso sobrevive en el Resumen cuando la tarjeta
desaparece (R6.2).

---

## 6. Nada nuevo que instalar, nada nuevo que medir

**Dependencias nuevas**: ninguna. El componente de catálogo se construye con lo
que el sistema de diseño ya tiene (`tabs`, `select`, `section`, `empty-state`,
`input`). La puerta de licencias (§VIII) se cierra con «ninguna».

**Medidor**: nada. El Resumen **lee** unidades que el medidor de la spec 004 ya
registra. No se añade un medidor, no se cambia una tarifa, no se escribe un
`UsageRecord`.

**Aislamiento**: ninguna garantía nueva. Las cuatro lecturas del Resumen ya
están acotadas por tenant dentro del partner y ya tienen su barrida en
`tests/isolation/test_console_scope.py`. Lo que esta spec añade es una pantalla
que las junta, así que la garantía que hay que comprobar es que **juntarlas no
abre una puerta**: el Resumen de un cliente ajeno tiene que seguir siendo un
404 opaco, y ninguno de sus bloques puede filtrar la existencia del cliente.
