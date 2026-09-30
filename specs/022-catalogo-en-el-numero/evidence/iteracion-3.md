# Iteración 3 — el alta lo ofrece (Historia 2)

**Cerrada en local el 2026-09-30.** El recorrido con el alta real (CE-004)
espera al permiso `catalog_management` en el panel de Meta.

## Lo que cambió el diseño al escribirlo

- **La decisión de abrir se toma con la lista ya pedida**, y esa lista se le
  pasa al selector (`preloaded`): una sola llamada a Meta, no dos.
- **Un permiso que falta no rompe el alta**: el toast de «conectado» sale
  igual, no se abre nada, y la tarjeta contará lo del permiso después.
- **La oferta tiene su propio título** («Tu negocio tiene catálogo en Meta»)
  y el botón de cerrar dice «Ahora no»: es una oferta, no una tarea.

## Medido

| Caso | Resultado |
|---|---|
| ≥ 1 catálogo | se abre la oferta con la lista |
| 0 catálogos | no se abre nada; el alta termina como hoy |
| permiso que falta / Meta caído | no se abre nada; el «conectado» sigue |
| `business_id` | el alta lo guarda en `config` (lo necesita listar) |

## Suites

| Suite | Resultado |
|---|---|
| Consola · canales + i18n | 85 ✅ · lint y `tsc` limpios |
| API · `test_endpoint_console_whatsapp` | ✅ |
