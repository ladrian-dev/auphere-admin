# Iteración 4 — coexistencia (2026-10-01, producción)

- Flor y Encanto, número `+34653321693` (WABA `1592517865994495`, cuenta de
  la app de WhatsApp Business en coexistencia). La consola pidió
  `GET /{waba}/product_catalogs` y Meta respondió 400
  `(#10) This operation can not be performed on SMB business type`; con un
  token de usuario del sistema con `catalog_management` y acceso a la cuenta
  y al catálogo, `POST /{waba}/product_catalogs` respondió lo mismo. No es
  un permiso: es el tipo de cuenta.
- La tarjeta decía «La conexión de WhatsApp no incluyó el permiso de
  catálogo» (estado `permission_missing` por el código 10). Corregido: el
  código 10 con ese mensaje pasa a estado `coexistence`, se aprende
  `config.mode = coexistence`, y en ese estado `PUT/DELETE …/catalog` no
  llaman a Meta: apuntan (o quitan) el catálogo elegido entre los del
  negocio, que es el que la app tiene conectado.
- Evidencia de que las tarjetas salen en coexistencia: Barber Supply (cuenta
  «App de WhatsApp Business» en Facelad) manda tarjetas de producto con el
  `catalog_id` apuntado por el camino de operador.
- Tests: `test_endpoint_console_catalog.py` (4 casos de coexistencia),
  `channel-card.test.tsx` (2 casos).
