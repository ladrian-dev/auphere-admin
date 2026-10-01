# Plantillas de Meta — spec 025 (iteración 2)

Tres plantillas de **utilidad**, en español, en la cuenta de WhatsApp del
negocio. Hacen falta cuando la ventana de 24 horas está cerrada: el aviso al
revisor, y la respuesta al cliente que ya no escribe. Variables con nombre
(`{{nombre}}`), que es lo que la plataforma usa al enviar. Se crean en
Canales → Plantillas de mensaje → Nueva plantilla, con un ejemplo por
variable (la consola lo pide desde el 2026-10-01).

## `revision_pago` — al revisor

- Categoría: Utilidad · Idioma: `es`
- Cabecera: `Pago por revisar`
- Cuerpo:

```
Hay un pago por revisar en {{negocio}}.

Cliente: {{cliente}}
Pedido: {{pedido}}
Entrega: {{entrega}}
Total: {{total}} · {{forma_pago}}

Revisa el comprobante y confirma o rechaza el pago.
```

- Botones, respuesta rápida: `Confirmar pago` · `Rechazar pago` · `Ver comprobante`
- Ejemplos: negocio `Flor y Encanto` · cliente `Camila, +56 9 1234 5678` ·
  pedido `Ramo de 12 rosas rojas` · entrega `Envío a Ñuñoa, viernes 3 de
  octubre, 13:00 a 17:00` · total `$34.990` · forma_pago `Transferencia`

Al enviarla, cada botón lleva su `payload` (`prv:<token>:ok`,
`prv:<token>:no`, `prv:<token>:ver`). «Ver comprobante» abre la ventana del
revisor, y entonces sale el comprobante con los botones normales.

## `pago_confirmado` — al cliente

- Categoría: Utilidad · Idioma: `es`
- Cuerpo:

```
Hola {{nombre}}, tu pago está verificado. Tu pedido queda en preparación para el {{entrega}}. Gracias por comprar en {{negocio}} 🌷
```

- Ejemplos: nombre `Camila` · entrega `viernes 3 de octubre, entre 13:00 y
  17:00` · negocio `Flor y Encanto`

## `pago_no_verificado` — al cliente

- Categoría: Utilidad · Idioma: `es`
- Cuerpo:

```
Hola {{nombre}}, no pudimos verificar tu transferencia. Una persona del equipo de {{negocio}} te escribirá por este chat para revisarlo contigo.
```

- Ejemplos: nombre `Camila` · negocio `Flor y Encanto`

## Lo que no hacen todavía

Meta tarda de minutos a un día en aprobarlas. Mientras la iteración 2 no
esté construida (tipo `button` en el adaptador, envío por plantilla con la
ventana cerrada, «Ver comprobante»), quedan aprobadas y sin usar.
