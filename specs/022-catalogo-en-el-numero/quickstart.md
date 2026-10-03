# Quickstart — comprobarlo a mano

En local Meta se simula (`build_meta_client`), así que CE-001, 003 y 005 se
recorren enteros; CE-002 y 004 necesitan **staging con número real** y, antes,
el permiso `catalog_management` en la configuración del Embedded Signup del
panel de Meta (research D5).

## CE-001 · enlazar desde la tarjeta (local, Meta simulado)

Con un número conectado en `panaderia-la-espiga`, en Canales → tarjeta →
«Conectar catálogo». **Pasa si**: la lista trae los catálogos del simulador
con nombre, elegir uno deja la tarjeta en «Catálogo: <nombre>», la auditoría
dice quién lo enlazó, y **Cambiar** pide confirmar nombrando el que sale y el
que entra.

## CE-003 · sin permiso, sin error (local)

Con el simulador contestando «permiso» a listar. **Pasa si** la tarjeta dice
que la conexión de WhatsApp no incluyó el permiso y que se concede volviendo a
conectar el número; sin botón de conectar; el número sigue «Activo».

## CE-005 · quien mira no toca; el otro tenant no ve (local)

Con un rol de solo lectura: el nombre del catálogo, sin controles. Con el
partner B: `GET …/catalogs` del canal de A es 404. Es el test de aislamiento,
también a mano.

## CE-002 · la tarjeta nativa (staging, número real)

Con el `+34653321693` y un catálogo de prueba en Commerce Manager con dos
productos: enlazar desde la tarjeta, y en el Playground pedir «¿qué tenéis?».
**Pasa si** la respuesta llega como tarjeta de producto (foto, nombre, precio)
al teléfono de prueba, y en Capacidades aparecen «Buscar en el catálogo» y
«Enviar productos del catálogo» encendidas.

## CE-004 · el alta lo ofrece (staging, número real)

Desvincular el número y volver a conectarlo. **Pasa si** al terminar el alta
la consola ofrece el catálogo; saltarlo deja el número conectado sin él, y la
tarjeta lo sigue ofreciendo.

## Lo que hay que hacer en el panel de Meta antes de CE-002 y CE-004 — **hecho el 2026-09-30** (ver research D5); falta reconectar el número

Añadir `catalog_management` a las dos configuraciones del Embedded Signup
(Cloud API y coexistencia) y **reconectar** el número: el token anterior no
trae el permiso. Sin este paso, staging solo puede probar CE-003.
