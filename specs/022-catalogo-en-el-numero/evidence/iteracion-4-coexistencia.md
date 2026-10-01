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

## 2026-10-01 · apuntar el catálogo a mano cuando Meta no lo lista

Con el `+56991919125` de Flor y Encanto conectado en coexistencia, «Conectar
catálogo» decía «la conexión no incluyó el permiso de catálogo». Causa, vista
en el panel de Meta: `catalog_management` está en **acceso estándar**
(«Listo para la prueba», 0 llamadas) y Meta solo lo concede a personas con
rol en la app, nunca al negocio de un cliente, aunque la configuración de
coexistencia lo pida (lo pide). El acceso avanzado exige revisión de la app.

Cambio: en coexistencia la declaración no depende de la lista. La API
intenta leerla para traer el nombre; si Meta no la da, apunta el
identificador y el nombre que escribió el partner (`catalog_name` en el
PUT, `meta.unverified`). El selector enseña un formulario con el
identificador y el nombre, solo en coexistencia y solo cuando no hay lista.
Fuera de coexistencia nada cambia: sin permiso, 409 con el motivo.

Tests: `test_a_coexistence_number_declares_the_catalog_even_when_meta_will_not_list`
(API) y «Apuntar el catálogo a mano en coexistencia» (consola, 3 casos).
