# Validación: el enlace para que el cliente conecte Instagram y Messenger

## En local

1. La API, con base propia (ver `docs/` y la memoria «Una suite de pytest a la vez»):
   - las pruebas de la 085: `tests/integration/test_085_owner_link_meta_social.py` y `tests/isolation/test_085_owner_link_meta_social_scope.py`;
   - las que ya existen del enlace y de la conexión: `tests/integration/test_channel_signup_links.py`, `tests/integration/channels/test_owner_link.py`, `tests/unit/test_endpoint_console_meta_social.py`, `tests/isolation/test_meta_social_channel_isolation.py` y `tests/isolation/test_console_scope.py`;
   - el paquete de canales: las pruebas de `apps/channels` sobre `meta_social/connect.py`.
2. La consola: vitest de `app/connect`, `components/channels` y `components/builder`, y `src/__tests__/proxy-public-routes.test.ts`.
3. `./scripts/verify.sh lint` y `./scripts/verify.sh js`.

## En staging (con una cuenta real de Instagram y una Página)

1. Como partner, en Canales de un cliente sin Instagram: «Enviar enlace al cliente» en la tarjeta de Instagram. Se crea el enlace, se copia y muestra su caducidad. No pregunta «¿Cómo lo conecta?».
2. Abrir el enlace en otro navegador, sin sesión:
   - aparece «Conecta el Instagram de {negocio}» con «¿Cómo entras a Meta?»;
   - con «Con Facebook y tu Página», la ventana de Meta pide la Página;
   - al volver: si hay una sola cuenta, «¡Listo!»; si hay varias, el diálogo de elegir.
3. En la consola, el canal aparece en el cliente y llega el aviso. Un DM a la cuenta recibe respuesta del agente.
4. Lo mismo con Messenger: entrar con Facebook, elegir la Página y «¡Listo!».
5. **Estados:**
   - volver a abrir el enlace usado: «Este enlace ya se usó»;
   - un enlace anulado desde la consola: «Este enlace ya no es válido»;
   - cancelar el diálogo de elegir: no se conecta nada y el enlace sigue valiendo.
6. **Convivencia:** un enlace de WhatsApp pendiente sigue vivo después de crear uno de Instagram para el mismo cliente.
7. **Desde un agente:** el enlace de Instagram creado en el agente deja el canal en ese agente.
