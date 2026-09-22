# Bug Fix: lo que el partner elige para su teammate llega al turno

- **Slug**: lo-que-el-partner-elige-no-llega-al-teammate
- **Fixed**: 2026-09-22
- **Tests primero**: sí, los dos en rojo antes de tocar código

## El cerebro

`apps/api/src/nexus_api/api/console/companion.py`

1. Al leer el catálogo y la identidad del teammate se lee también su modelo.
2. `_make_driver` lo acepta como `teammate_model` y lo pasa a la compilación.
3. `_get_companion_graph(toolbelt, *, model=None)` compila con
   `model or settings.llm_companion_model` — sin teammate, nada cambia.
4. **La caché solo guarda el grafo genérico**: `if toolbelt is None and model is
   None`. Un grafo compilado con el modelo de un teammate concreto no puede
   quedarse para el siguiente.

El punto 4 es el que tiene trampa. Sin él, el primer teammate que pidiera turno
dejaría su modelo cacheado y los demás correrían con el suyo — un fallo que no
aparece en desarrollo, porque hace falta más de un teammate y carga a la vez.
Tiene test propio.

`apps/api/tests/unit/test_teammate_model_is_used.py`, tres casos: el cerebro del
teammate es el que corre, sin teammate sigue el del Companion, y un grafo
compilado para uno no se cachea para el siguiente.

## Aplicar

`apps/api/src/nexus_api/services/teammate_catalog.py`

`console.apply` sale de `_WRITE_NAMES` y pasa a `_APPLY_NAMES`, que se concede
cuando el teammate tiene **cualquiera** de los cuatro interruptores que proponen
(`write`, `publish`, `spend`, `contact`).

Un teammate de solo lectura sigue sin ella: no es que sea peligrosa —exige una
acción confirmada por una persona, y él no puede crear ninguna—, es que publicar
una herramienta que nunca tendrá nada que hacer solo sirve para que el modelo la
intente.

`apps/api/tests/isolation/test_33_teammate_catalog_is_subset.py`, dos casos: los
cuatro interruptores que proponen pueden aplicar, y solo lectura no.

## Verde

2541 tests de API (aislamiento, teammates, unidad), `verify.sh lint` con
`ruff` y `mypy --strict`.

## Lo que este arreglo NO toca, y hay que decirlo

El teammate sigue sin saber **qué día es**, sigue leyendo en su prompt estable
que tiene capacidades que su catálogo puede no darle, y sigue sin instrucciones
propias: dos teammates con los mismos permisos son el mismo agente con distinto
nombre. Eso es la spec 015, no un defecto contra lo prometido.
