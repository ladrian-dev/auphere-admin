> **⚠️ SUPERADO por [`007/contracts/quota-unit-v2.md`](../../007-pesos-de-cuota-por-carril/contracts/quota-unit-v2.md)
> (2026-09-14).** El peso único por modelo que describe este documento se
> sustituyó por **tres pesos, uno por carril**. Lo que aquí se afirma sobre el
> factor `0,1` de `cache_read` y sobre la invarianza del pool **ya no es
> cierto**: la invarianza sólo se cumplía en el punto de calibración de la
> migración `0115`. Se conserva como historia de por qué se decidió lo que se
> decidió; **para el código, la verdad es el v2**.

# Contrato — la unidad de cuota, con factor por modelo

`metering/quota.py` define **la única unidad** en la que se mide el consumo de
modelo en toda la plataforma. La consumen tres llamantes y un libro. Cambiarla
sin que los tres cambien a la vez es cómo se vuelve a tener dos contadores.

## La fórmula

**Antes** (política C3):

```
quota = uncached_input + 0,1 × cache_read + output
uncached_input = max(0, prompt_tokens − cache_read)
```

**Después**:

```
quota = (uncached_input + 0,1 × cache_read + output) × model_weight
```

El factor se aplica **al total y antes del redondeo final**, una sola vez. La
función ya redondea con `ROUND_HALF_UP` —no con el `round()` de Python, que es
banquero— y ese redondeo sigue siendo el último paso.

`cache_write` sigue **fuera** de la cuota, como hasta ahora: no se inventa un
quinto multiplicador, y los proveedores del catálogo cerrado no lo cobran.

## La firma

```
quota_tokens(*, prompt_tokens, cache_read, output_tokens, cache_write,
             model_weight: Decimal) -> int
```

`model_weight` es **obligatorio y explícito**. No tiene valor por defecto: un
defecto de `1` convertiría el olvido de pasarlo en un cobro silencioso a la baja,
que es el modo de fallo que R3.4 rechaza.

**La función sigue siendo pura**: sin base de datos, sin red, sin reloj. Quien
llama resuelve el factor; la función lo aplica. Es lo que permite que su suite
corra en milisegundos sin Postgres.

## De dónde sale el factor

De `model_profiles.quota_weight`, servido por el catálogo cacheado
(`nexus_worker.metering.pricing.get_catalog()`, TTL 300 s), que ya se lee en el
camino del turno para valorar el coste. **Cero consultas nuevas por llamada.**

`ModelPrice` gana el campo `quota_weight: Decimal | None`.

## Qué pasa cuando no hay factor

| Situación | Comportamiento |
|---|---|
| El modelo tiene `quota_weight` | Se aplica |
| El modelo está en catálogo con `quota_weight` NULL | **Se rechaza la llamada** con error legible que nombra el modelo y dice que le falta el factor (R3.4) |
| El modelo no está en catálogo | Ya se rechaza hoy — no es un modo de fallo nuevo |
| El medidor **no pasa por cuota de LLM** (`voice.minutes`, `media.*`) | **No le aplica.** `openai/whisper-1` tiene `quota_weight` NULL **y sigue funcionando**: se mide por minutos, no por tokens |

La última fila es la que hay que escribir en el código, no solo aquí: es
exactamente el tipo de cosa que alguien "arregla" dentro de seis meses poniéndole
un `1.0` a whisper y rompiendo la invarianza sin que salte un test.

## La invarianza que este contrato promete

**Agotar un pool de tamaño P cuesta lo mismo en dólares sea cual sea el modelo.**

Comprobado sobre los seis modelos del catálogo con los factores a tres decimales:
agotar 1 M de pool cuesta entre **3,5144 $ y 3,5154 $** — 0,03 % de desviación.

Es la razón de ser del cambio, y va como test de propiedad, no como un caso
suelto: se recorre el catálogo entero y se comprueba la banda.

## Los tres llamantes

Los tres tienen que pasar el mismo factor para el mismo modelo. Si uno lo
olvidara, su consumo entraría al libro con otra unidad y el total dejaría de
cuadrar — el defecto que esta spec elimina en el camino de lectura, reaparecido
en el de escritura.

| Llamante | Dónde | Qué gasta |
|---|---|---|
| Companion y teammates | `api/console/companion.py` | Incluido primero, comprado después |
| Canal de clientes finales | `nexus_worker/metering/consumer.py` | **Comprado solamente** (R5.2) |
| Ejecución en la máquina | `services/local_workstation_metering.py` | Incluido primero, comprado después |

**Se prueba estructuralmente**: un test recorre los llamantes de `quota_tokens`
y falla si alguno no pasa `model_weight`. Es más barato que descubrirlo cuadrando
una factura.

## Lo que NO cambia

- **La idempotencia.** `usage_ledger.idempotency_key` sigue siendo UNIQUE y el
  reparto entre cubos sigue sufijando la clave (`:included` / `:purchased`).
- **El asiento es un hecho.** Cambiar un factor **no** revalúa lo ya debitado
  (R3.5). El factor nuevo aplica a lo que venga.
- **Cuota ≠ coste.** La valoración en dólares sigue usando las cantidades
  **nativas** contra `model_profiles`, sin pasar por el factor. El factor dice
  «cuánto pool come»; la tarifa dice «cuánto nos cuesta». Confundirlos es cómo se
  acaba cobrando dos veces el mismo descuento de caché.
- **Sin importe en dólares en la fila de un turno** (decisión 14 de la KB).
