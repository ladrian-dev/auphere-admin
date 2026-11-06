# Guía de validación: Correcciones de QA de la consola

## Preparación local

1. Levantar `api` y `console` con `preview_start`. Consola en `:3110`, API en `:8000`.
2. Aplicar la migración `0220`.
3. Entrar con el partner de pruebas `demo-audit`.

En local el correo no sale: queda en el registro de la API (`email.suppressed`), con su enlace.

## Escenarios

| # | Historia | Pasos | Resultado esperado |
|---|---|---|---|
| 1 | H3 | Negocio: guardar Horarios en un cliente sin horario | La marca del índice cambia sin recargar, y sigue igual al recargar |
| 2 | H4 | Nuevo agente: escribir y pulsar «Recepción y citas» dos veces | Los dos textos, sin repetir, y el nombre se conserva si ya estaba |
| 3 | H4 | Con la descripción casi llena, pulsar un ejemplo | El texto no cambia y se dice que no cabe |
| 4 | H5 | Políticas, en lectura y en edición, en los dos idiomas | «Señal o anticipo» con su ayuda |
| 5 | H2 | Crear un cliente, elegir USD en «Moneda de los precios» | El resumen del alta, Datos básicos y los dos modales de servicio dicen USD |
| 6 | H2 | Cambiar a CLP con tres servicios con precio, y cancelar | Avisa de tres, y no cambia nada |
| 7 | H2 | Repetir y confirmar | Los tres en CLP con el mismo número, y en la auditoría |
| 8 | H2 | Cliente sin moneda: poner un importe en un servicio | Pide elegir la moneda, y queda guardada para todo el negocio |
| 9 | H1 | Crear un partner desde el panel local | Queda registrada la invitación, y su enlace permite registrarse |
| 10 | H1 | Crear otro y, sin aceptar, pedir «Recuperar» con esa dirección | Misma pantalla de siempre. Se registra la invitación con un enlace nuevo, y el anterior ya no vale |
| 11 | H1 | Pedir «Recuperar» con una dirección sin nada | Misma pantalla, y no se registra ningún correo |
| 12 | H6 | Crear «corte» y «Corte» en dos servicios, y otro sin categoría | Un grupo «corte», y «Sin categoría» al final. Igual en Reservas |
| 13 | H6 | Probar el agente preguntando por un corte | Ofrece los de esa categoría |

## Pruebas automáticas

```bash
uv --directory apps/api run --extra dev pytest apps/api/tests/integration/business/test_055_qa_consola.py apps/api/tests/integration/test_055_recuperar_con_invitacion.py apps/api/tests/isolation/test_055_services_currency_category.py
```

```bash
NODE_OPTIONS=--experimental-require-module pnpm --dir apps/console test
```

```bash
NODE_OPTIONS=--experimental-require-module ./scripts/verify.sh
```

## Tras subir a `develop` (con autorización del owner)

- **C1**: crear en staging un partner de prueba con la dirección que dé el owner. El correo llega y se puede registrar.
- **C2**: contar, solo con lectura, los servicios en una moneda distinta a la de su negocio.
- **C4**: repasar lo que dependa del entorno real.
