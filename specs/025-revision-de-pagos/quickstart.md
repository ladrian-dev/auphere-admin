# Quickstart — spec 025

## La suite

```bash
uv run --directory apps/api pytest \
  tests/unit/test_agent_payment_review.py \
  tests/unit/test_payment_reviews_resolve.py \
  tests/unit/test_webhook_payment_review_tap.py \
  tests/unit/test_endpoint_console_agent_settings_payment_review.py \
  tests/isolation/test_payment_reviews_scope.py -q
uv run --directory apps/mcp pytest tests/test_payments_request_review.py tests/test_registry_unit.py -q
cd apps/console && pnpm exec vitest run src/components/agent-tools
```

| Test | Criterio |
|---|---|
| `test_agent_payment_review` | revisores ↔ policies: normaliza, deduplica, rechaza números inútiles, máx. 10 |
| `test_payments_request_review` | sin revisores → error que nombra el escalado; con dos, ventana abierta: dos avisos con botones y el comprobante; uno con ventana cerrada → `undelivered`; segundo comprobante con una pendiente → se suma y no avisa otra vez; `link` pagado → `informed`, sin botones |
| `test_payment_reviews_resolve` | primera pulsación resuelve y encola tres textos; la segunda no cambia nada y dice quién; rechazo → `agent_active=false`; cliente con ventana cerrada → `customer_notified=false` |
| `test_webhook_payment_review_tap` | una pulsación `prv:` no se encola al agente; un remitente no avisado no resuelve |
| `test_payment_reviews_scope` (aislamiento) | un token de A no existe en B; avisos y revisiones con RLS |
| consola | la sección guarda revisores y enseña el número que falla |

## En staging — con número real

1. En un cliente con número conectado, poner como revisor el número del
   owner y publicar. Escribir «hola» desde ese número al del negocio (abre
   la ventana de 24 horas del revisor).
2. Desde otro número, pedir un producto, elegir transferencia y mandar una
   foto como comprobante. El revisor recibe la foto y el mensaje con los dos
   botones. El cliente recibe «estamos verificando».
3. Pulsar **Confirmar pago**: el cliente recibe que está verificado, con
   fecha y rango. Pulsar otra vez: «ya lo confirmó …».
4. Repetir con **Rechazar pago**: el cliente recibe el texto de rechazo y el
   agente deja de responder en esa conversación.
5. Capturas en `evidence/`.
