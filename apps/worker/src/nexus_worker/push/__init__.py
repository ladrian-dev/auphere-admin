"""Avisos al teléfono de la app Auphere Customers — spec 031 (research D6, D8).

* :mod:`.apns` y :mod:`.fcm` — los dos proveedores, directos, sin el servicio
  de push de Expo.
* :mod:`.dispatcher` — la tarea ``push-dispatcher`` (familia egress): drena el
  outbox ``client_push_events`` con ``nexus_api.services.push_fanout``.
"""
