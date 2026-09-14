# Fase 0 — investigación: la cuota cobra por carril

**Spec**: [spec.md](./spec.md) · **Fecha**: 2026-09-14

Cinco decisiones. Las tres primeras las pedía la spec; **la cuarta y la quinta
las destapó esta fase** y cambian el alcance del trabajo.

---

## D1 · Los tres pesos viven en `model_profiles`, como tres columnas más

**Decisión**: añadir `quota_weight_input`, `quota_weight_cache_read` y
`quota_weight_output` a `model_profiles`. `quota_weight` queda **deprecada, no
borrada**.

**Razón**: el catálogo ya es una fila por modelo con cinco tarifas y un peso; un
peso por carril es la misma clase de dato en la misma granularidad. Se lee por
el catálogo cacheado que ya existe (TTL 300 s), así que no añade ni una consulta
en el camino caliente.

Que `quota_weight` sobreviva a la migración es el patrón que la `0115` dejó
escrito para `companion_monthly_token_cap`: *«crear la sustituta y eliminar la
original en la misma migración deja un `downgrade()` incapaz de devolver los
datos»*. La elimina una migración posterior, cuando el despliegue lleve un ciclo
con las columnas nuevas.

**Alternativas consideradas**:

- **Tabla nueva `model_quota_weights` (modelo × carril)**. Rechazada: duplica la
  clave del catálogo y convierte una lectura de fila en un join, para representar
  tres números que no tienen ciclo de vida propio.
- **No persistir el peso y derivarlo del precio en cada llamada** —
  `peso = 2,2 × precio_carril ÷ 10`. Es tentador porque haría **imposible** la
  divergencia que el Requisito 6 vigila: lo que no se duplica no puede divergir.
  Rechazada por tres motivos:
  1. **Acopla dos cosas que son deliberadamente independientes.** La tarifa de
     proveedor es un hecho externo que cambia cuando el proveedor quiere; el peso
     es una decisión comercial nuestra. Derivar uno del otro significa que
     cualquier subida de tarifa se traslada al partner el mismo minuto, sin que
     nadie lo decida.
  2. **Pierde la puerta que la `0115` abrió a propósito.** Hoy `NULL` significa
     «este modelo no se sirve por el carril de cuota de LLM», y es lo que hace
     que un modelo del catálogo sin peso se **niegue** a servir en vez de cobrarse
     mal. Derivando, cualquier modelo con precio quedaría servible por el mero
     hecho de tener precio.
  3. **Un débito pasado deja de ser explicable.** Con el peso en una fila, se
     puede decir por qué se cobró lo que se cobró.

  Lo bueno de la alternativa se conserva sin adoptarla: **el Requisito 6 es
  exactamente esa derivación, ejecutada como comprobación en vez de como
  fórmula** — se recalcula el peso desde el precio y se compara con el guardado.

---

## D2 · La escala es `NUMERIC(12,6)`, la misma que las tarifas

**Decisión**: las tres columnas nuevas son `NUMERIC(12,6)`, no `NUMERIC(6,3)`.

**Razón**: el peso **es** una tarifa reescalada (`2,2 × precio ÷ 10`), y darle la
misma escala que `price_*_per_mtok` hace que la derivación no pierda nada en el
rango que importa. Con tres decimales, el carril de caché de
`openai/gpt-5.6-luna` vale 0,0044 y se guarda como 0,004 — 2,00x en vez de 2,20x.
Con seis decimales cabe exacto.

Qué queda sin resolver, y por qué es aceptable: seis decimales no garantizan
exactitud para *cualquier* tarifa futura, porque `0,22 × precio` no siempre es
múltiplo de 10⁻⁶. El error máximo es 5×10⁻⁷ absoluto, que sobre el peso más
pequeño del catálogo de hoy (0,0044) es un **0,011 %**. El suelo está a un 32 %
de distancia del objetivo. La comprobación del Requisito 2 se hace **sobre el
valor guardado** precisamente para que esto no haya que razonarlo otra vez:
si algún día una tarifa rara rompiera el suelo, el test lo dice.

**Alternativas consideradas**: `NUMERIC(6,3)` con el invariante comprobado tras
el redondeo (descartada en `/speckit-clarify`: deja viva la trampa para el
próximo modelo barato) · una escala mayor que la de las tarifas (rechazada:
resolución que ninguna tarifa puede alimentar).

---

## D3 · Un solo redondeo, en el borde, y el desglose no lo fija

**Decisión**: `quota_tokens()` suma los tres productos en `Decimal` y cuantiza
**una sola vez**. `billable_qty_for_meter()` sigue devolviendo el desglose por
fila nativa y sigue pudiendo diferir del total en menos de un token.

**Razón**: hoy hay **dos** redondeos encadenados — `quota_input_tokens()`
cuantiza el aporte de la caché y `quota_tokens()` vuelve a cuantizar el total
ponderado. Con un peso por carril, los tres productos son homogéneos y se pueden
sumar antes de cuantizar: menos deriva, no más. El `ROUND_HALF_UP` se mantiene;
`round()` de Python sigue prohibido aquí por ser banker's.

El desglose es **informativo**: quien fija el débito es `quota_tokens()`. Esa
asimetría ya existe hoy y se documenta en vez de eliminarse, porque eliminarla
obligaría a repartir el token de holgura entre carriles con una regla que nadie
podría defender.

---

## D4 · Medir es nativo; ponderar ocurre una vez, en el borde

> **Esto no estaba en la spec.** Lo encontró esta fase y es la mitad cara del
> trabajo.

**El hallazgo.** La cuota ponderada **ya viaja por el sistema y ya está
persistida**, no sólo se calcula al debitar:

| Dónde | Qué guarda hoy |
|---|---|
| `runtime/companion/graph.py` (`_billable_input`) | acumula `total_input_tokens` **ya ponderado**, con la constante global 0,1, sin saber de qué modelo se trata |
| `companion.runs.input_tokens` (migración `0093`) | **la cuota**, no el nativo: *«`input_tokens` del run es la CUOTA (uncached + 0.1 × cache_read, C3)»* |
| `api/console/companion.py` | **des-hace** la ponderación restando `0,1 × cache_read` para recuperar el uncached, y la vuelve a aplicar para debitar y para valorar en USD |

Ese round-trip sólo funciona porque el factor es **una constante única y global**.
Con un peso por carril y por modelo, `total_input_tokens` deja de ser invertible:
para des-ponderarlo haría falta conocer el modelo en el punto de acumulación, que
es justo lo que el grafo no tiene.

**Decisión**: el grafo acumula **nativos** (entrada no cacheada y lectura de
caché por separado); la ponderación ocurre **una sola vez**, en el borde donde se
debita. Se añade una columna para el nativo y `runs.input_tokens` queda
**deprecada con su significado viejo intacto**, igual que D1 hace con
`quota_weight`.

**Razón**: medir y tarifar son dos cosas, y mezclarlas es lo que ha hecho que un
cambio de tarifa sea un cambio en cuatro módulos. Un nativo no caduca cuando
cambia un precio; una cuota ponderada sí. Además arregla algo que hoy ya es
frágil: la reconstrucción `uncached = input_tokens − 0,1 × cache_read` es una
resta que depende de que dos módulos en dos procesos distintos usen la misma
constante, y nada lo comprueba.

**Alternativas consideradas**:

- **Que el grafo pondere con el peso del modelo.** Rechazada: mete el catálogo
  de precios dentro del bucle del agente y deja la ponderación en dos sitios
  otra vez, que es el defecto que se está corrigiendo.
- **Reescribir el significado de `runs.input_tokens` en sitio.** Rechazada: deja
  filas históricas cuya interpretación depende de la fecha, y un `downgrade()`
  que no puede devolver los datos.

**Consecuencia para el alcance**: los sitios que tocan la fórmula **no son dos**
—como decía el encargo— sino **cuatro**: `metering/quota.py`,
`worker/metering/consumer.py`, `api/console/companion.py` y
`runtime/companion/graph.py`.

**Y no son cinco**, que era el riesgo. Comprobado: `api/console/playground.py` y
`api/qa.py` acumulan por el evento `cost.updated` de `qa_streaming`, cuyo
`_extract_usage` devuelve `usage_metadata.input_tokens` — el **nativo bruto del
proveedor**, sin ponderar. Y ninguno de los dos llama a `debit_wallet`: los
únicos dos puntos que debitan son `api/console/companion.py` y
`worker/metering/consumer.py`. Quedan fuera del cambio.

> **Observación fuera de alcance, anotada porque cuesta una línea y encontrarla
> otra vez cuesta una tarde:** `qa.runs.input_tokens` guarda **nativo bruto** y
> `companion.runs.input_tokens` guarda **cuota ponderada**. Mismo nombre de
> columna, dos significados, y ninguna spec lo dice. No se toca aquí — no cambia
> ningún importe — pero el nombre nuevo que introduce D4 debe elegirse sabiendo
> que esa ambigüedad ya existe.

---

## D5 · Nada se revalora, y por eso no hace falta reprecificar nada

**Decisión** (de `/speckit-clarify`): los pesos nuevos se aplican al consumo
posterior al despliegue. Ni el libro asentado, ni el saldo comprado, ni las
bolsas en curso se tocan.

**Razón**: la unidad de cuota no cambia de definición — sigue siendo «lo que come
el tope» — sino de **tasa de conversión** desde los tokens nativos. Un saldo de
un millón de unidades sigue siendo un millón de unidades; lo que cambia es cuánto
trabajo compra. No hay nada que migrar, y por tanto no hay una migración de datos
que pueda salir mal sobre tres clientes con tráfico.

Esto hace que el despliegue sea **reversible por revert**: volver a los pesos
viejos restaura el comportamiento sin dejar filas con dos interpretaciones.

**Alternativas consideradas**: congelar lo comprado a la tarifa vieja (rechazada
en `/speckit-clarify`: obliga a dos tarifas vivas en el mismo libro) · revalorar
el saldo (rechazada: regala margen el día que se corrige un defecto de margen).

---

## Licencias (§VIII)

**Ninguna dependencia nueva.** Todo ocurre con `Decimal` de la biblioteca
estándar, SQLAlchemy y Alembic, que ya están. No hay nada que leer ni que citar.

## Lo que esta fase deja sin decidir a propósito

- **El tamaño de las bolsas de cada plan** — fuera de alcance por la spec; es una
  decisión comercial.
- **Cuándo se borran `quota_weight` y `runs.input_tokens`** — una migración
  posterior, cuando el despliegue lleve un ciclo con las columnas nuevas. Ponerlo
  aquí rompería el `downgrade()`.
