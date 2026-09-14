# Contrato: la unidad de cuota, versión 2

**Sustituye** a [`004/contracts/quota-unit.md`](../../004-medidor-y-pool-semanal/contracts/quota-unit.md),
que queda marcado como superado. **Este contrato es la verdad para el código.**

## La fórmula

```
cuota = redondeo( entrada_no_cacheada × w_in
                + lectura_de_caché    × w_cache
                + salida              × w_out )

entrada_no_cacheada = max(0, prompt_tokens − cache_read)
```

- **Un solo redondeo**, al final, `ROUND_HALF_UP` sobre `Decimal`. `round()` de
  Python es banker's y sigue prohibido aquí.
- **`cache_write` no entra.** No gana un cuarto peso.
- **Los pesos son del modelo de esa llamada.** Una tarea que encadena llamadas a
  cerebros distintos se pondera llamada a llamada, nunca turno a turno.
- **No hay valor por defecto para los pesos**, por el mismo motivo que la 004 no
  lo dio para el peso único: un defecto convierte cada olvido en un cobro
  silencioso a la baja. Que falten es un error en la primera ejecución.

### Qué desaparece

El factor `0,1` global sobre `cache_read` **deja de existir como constante**. Era
la aproximación de un carril con un número; ahora el carril tiene su peso, que en
Anthropic y en la familia GPT-5.6 resulta ser una décima parte del de entrada y
en `gpt-4o` resulta ser el 50 %. Lo que antes era una coincidencia afortunada
—y la migración `0114` la dejó escrita como tal— ahora es un dato.

## La derivación de los pesos

```
w_carril = OBJETIVO × price_carril_per_mtok ÷ CREDIT_USD_PER_MILLION
OBJETIVO = 2,2            (margen 54,5 %)
SUELO    = 1,50           (nunca, en ningún carril, en ningún modelo)
```

El **objetivo** es lo que se cobra. El **suelo** es lo que no se puede cruzar.
Son dos números distintos a propósito: el objetivo puede moverse por decisión
comercial; el suelo es la regla que hace que esa decisión no pueda ser un
descuido.

## El desglose por medidor

`billable_qty` por fila nativa, **informativo**, no fija el débito:

| medidor | `billable_qty` |
|---|---|
| `llm.input_tokens` | entrada no cacheada × `w_in` |
| `llm.cache_read` | nativo × `w_cache` |
| `llm.output_tokens` | nativo × `w_out` |
| `llm.cache_write` | `0` |
| resto | la cantidad medida |

La suma del desglose puede diferir del débito en **menos de un token**, porque el
débito se cuantiza una vez y el desglose una vez por fila. Esa asimetría ya
existe hoy y se declara en vez de repartirse con una regla arbitraria.

## Las dos propiedades que este contrato compra

1. **El margen no depende de la mezcla.** Cobrado ÷ coste = 2,2x en cualquier
   combinación de entrada, caché y salida. Antes sólo se cumplía en el punto de
   calibración de la `0115`.
2. **Agotar una bolsa cuesta lo mismo con cualquier cerebro.** Se conserva la
   propiedad de la 004 y se amplía: antes era cierta para la mezcla de referencia
   (0,03 % de desviación) y falsa fuera de ella (78 % con trabajo de teammate);
   ahora es cierta por construcción para toda mezcla.

## Los tests de la 004 que este contrato retira

Dos ficheros afirmaban la fórmula vieja y **no se podían adaptar**, porque lo
que comprobaban es justo lo que deja de ser cierto. Se retiran, y aquí queda
dónde vive ahora cada caso, para que nadie los reescriba creyendo que falta
cobertura:

| Caso retirado (spec 004) | Dónde vive ahora |
|---|---|
| `test_quota_tokens.py::…cache_read_counts_one_tenth…` | `test_quota_lanes.py::…the_flat_cache_discount_is_gone` — y con `gpt-4o`, donde los dos caminos divergen |
| `…prompt_bruto_plus_cache_read_is_not_the_quota` | `test_quota_lanes.py::…each_lane_is_charged_with_its_own_weight` |
| `…cache_write_is_out_of_the_cap` | `test_quota_lanes.py::…cache_write_never_costs_quota` |
| `…rounding_is_half_away_not_bankers` | `test_quota_lanes.py::…exactly_one_rounding…` |
| `…input_billable_plus_cache_quantity_is_not_the_quota` | `test_usage_quota_consumer.py::…summing_input_billable…` |
| `…companion_and_channel_debit_the_same_call_once` | `test_turn_quota_lanes.py::…worker_and_api_agree…`, ahora **entre servicios** y con pesos reales |
| `test_quota_weight.py` entero (propiedad del pool) | `test_quota_pool_invariance.py`, ampliado a **toda mezcla** en vez de sólo la de referencia |

## Modelo sin pesos

Se **rechaza al servir** y se **omite al asentar**, exactamente como la 004
decidió para el peso único y por la misma razón: negarse a asentar consumo que ya
ocurrió no impide nada y sólo deja de cobrarlo en silencio. Se registra el
motivo, nombrando el modelo, y la fila queda medida.

Un modelo que no pasa por el carril de cuota de LLM (`openai/whisper-1`, medido
por minutos) **no necesita pesos y sigue funcionando**.
