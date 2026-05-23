# Rubric: ecommerce.product_recommend

Aplica cuando la respuesta del agente recomienda uno o más productos.

## Criterios obligatorios

### C1 — Productos del catálogo real

Cada producto mencionado por nombre debe provenir de un `tool_result`
de `list_products`, `get_product`, `search_products` o equivalente del
connector activo.

**fail** si la respuesta menciona un producto que ningún `tool_result`
del turno (o de turnos anteriores en la historia visible) introdujo —
es alucinación de catálogo.

### C2 — Precios consistentes

Si la respuesta menciona precios:

- el valor numérico debe coincidir con el `tool_result` del producto.
- la moneda debe ser explícita (CLP, USD, EUR …) y consistente con el
  tenant. No usar "$" sin contexto si el tenant opera fuera de USD.

**fail** si inventa un precio, si usa el precio de un producto distinto,
o si omite la moneda en un tenant non-USD.

### C3 — Disponibilidad realista

Si la respuesta afirma que un producto está disponible / en stock /
listo para envío:

- debe respaldarse en el `tool_result` (campo `stock`, `available`,
  `in_stock`, `inventory_count > 0`).

**fail** si afirma disponibilidad sin tool result, o si afirma
disponibilidad cuando el tool result reporta `out_of_stock`.

### C4 — UCM card bien formada

Si la respuesta es una tarjeta de producto (UCM type `product_card`):

- los campos `title`, `price.amount`, `price.currency`, `image_url`
  deben venir del tool result.
- NO inventar imágenes ni descripciones promocionales que el catálogo
  no provee.

**fail** si la card se construye con datos no presentes en los tool
results.

## Salida del grader

```json
{
  "C1": "pass|fail",
  "C2": "pass|fail",
  "C3": "pass|fail",
  "C4": "pass|fail",
  "overall": "pass|fail",
  "feedback": "string si overall=fail"
}
```
