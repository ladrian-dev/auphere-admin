# Quickstart — comprobarlo a mano

Los criterios 1, 2, 3 y 6 se comprueban en local (dos partners de prueba, sin
Meta). Los 4 y 5 necesitan **staging y un número real**: en local no hay Meta.

## CE-001 · el número cambia de cliente (local)

1. Con el partner `demo-audit`, en `panaderia-la-espiga`, desvincula el
   número de prueba.
2. Con otro cliente —o con el partner de la segunda cuenta local—, conéctalo.

**Pasa si**: el segundo lo conecta y atiende; el primero sigue viendo su tarjeta
como desvinculada, con su historial.

## CE-002 · reconectar recupera la misma ficha (local)

Desvincula y vuelve a conectar en el **mismo** cliente. **Pasa si** el canal
tiene el mismo id que antes y las conversaciones anteriores siguen colgando de
él.

## CE-003 · un número vivo en otro sitio se dice con palabras (local)

Con el número **activo** en A, intenta conectarlo en B. **Pasa si** B lee «este
número está en uso» y A no cambia. Y **nada** en la pantalla de B dice de quién
es.

## CE-004 · Meta ya no lo tiene bajo nuestra app (staging)

Desvincula el `+34653321693` y consulta en Meta —`GET /{phone_number_id}`
con el token de la app— que el número ya no está registrado bajo nosotros.
**Pasa si** Meta lo confirma y `unlink_pending` vuelve vacío.

## CE-005 · el hermano sigue vivo (staging, dos números en una WABA)

Con dos números bajo la misma cuenta de WhatsApp Business, desvincula uno.
**Pasa si** el otro sigue recibiendo y respondiendo, y la app sigue suscrita.

## CE-006 · Meta caído (local, con el cliente de Meta simulado fallando)

Desvincula con la llamada a Meta forzada a fallar. **Pasa si**: la tarjeta
dice desvinculado, el agente no atiende, `unlink_pending` lista lo que faltó,
y pulsar reintentar con Meta ya bien lo deja vacío.
