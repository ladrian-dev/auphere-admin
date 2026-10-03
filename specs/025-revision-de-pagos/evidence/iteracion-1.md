# Iteración 1 — evidencia (2026-10-01)

## Local

| Suite | Resultado |
|---|---|
| `tests/unit/test_payment_reviews_resolve.py` | 12 en verde: aviso con botones y comprobante a dos revisores, revisor con ventana cerrada contado y no simulado, segundo comprobante sumado, pago por enlace pagado informado sin botones, primera pulsación resuelve y avisa a todos, pulsación tardía no cambia y dice quién, rechazo silencia al agente, cliente con ventana cerrada `customer_notified=false`, extraño no resuelve, foto de producto anterior no se reenvía |
| `tests/unit/test_webhook_payment_review_tap.py` | 3 en verde: la pulsación resuelve y no se encola, un extraño no resuelve ni llega al agente, otro botón sigue al agente |
| `tests/isolation/test_payment_reviews_scope.py` | B no ve ni resuelve la revisión de A con el mismo teléfono |
| `tests/unit/test_agent_payment_review.py` | 5 en verde |
| `tests/unit/test_endpoint_console_agent_settings_payment_review.py` | 3 en verde: borrador, publicar, resumen del borrador, 422 por número |
| `apps/mcp/tests/test_registry_unit.py` | registro 61 herramientas |
| consola (vitest) | 575 en verde; 4 casos nuevos de «Revisión de pagos» |
| migración `0137_payment_reviews` | sube, baja y vuelve a subir en local |

Consola local: Ajustes del agente de `panaderia-la-espiga` enseña «Revisión de
pagos» bajo «A quién responde»; guardar un revisor lo normaliza
(`+56991280655`) y lo deja en el borrador.

## Pendiente (staging con número real)

Ver `quickstart.md` · En staging. Necesita un número conectado, un revisor
que haya escrito al número en las últimas 24 horas y la habilidad «Pedir
revisión de un pago» encendida.
