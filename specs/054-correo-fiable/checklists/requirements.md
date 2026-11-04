# Lista de calidad de la especificación: Correo fiable

**Propósito**: validar que la spec está completa antes de pasar a planificar
**Creada**: 2026-11-03
**Spec**: [spec.md](../spec.md)

## Calidad del contenido

- [x] Sin detalles de implementación (lenguajes, frameworks, APIs)
- [x] Centrada en el valor para el usuario y el negocio
- [x] Escrita para personas no técnicas
- [x] Todas las secciones obligatorias completas

## Completitud de los requisitos

- [x] No quedan marcas `[NEEDS CLARIFICATION]`
- [x] Los requisitos se pueden probar y no son ambiguos
- [x] Los criterios de éxito se pueden medir
- [x] Los criterios de éxito no nombran tecnología
- [x] Todos los escenarios de aceptación están definidos
- [x] Los casos límite están identificados
- [x] El alcance está delimitado
- [x] Las dependencias y los supuestos están identificados

## Preparación

- [x] Todos los requisitos funcionales tienen criterios de aceptación claros
- [x] Los escenarios cubren los flujos principales
- [x] La feature cumple los resultados de los criterios de éxito
- [x] No se cuelan detalles de implementación en la spec

## Notas

- **Nombres técnicos.** La spec nombra eventos y cabeceras del proveedor, códigos de respuesta, eventos de registro y nombres de alarma porque son el contrato que se pide cumplir, como hacen las specs 049 a 052. El Requisito 4.1 describe el cálculo de la firma porque la verificación es el requisito. Las tablas, las columnas, las rutas internas y dónde corre la cola quedan para `/speckit-plan`.
- **Decisiones por aprobar.** Todas las de la tabla, de D1 a D16, son propuestas de esta spec, y aprobarla es aprobarlas. Las que más pesan: D2 (los automáticos pasan a una cola, y un `True` de `send_template` pasa a significar «aceptado o en cola»), D11 (hasta fusionar, las alarmas no avisan a nadie) y D13 (el plan).
- **Comprobado.** Contra el código de `develop` (`09d579ef`): que `emit` envía dentro de la transacción, qué sitios usan el resultado y qué registra cada camino de fallo. Contra AWS, solo lectura: los eventos, los filtros de métrica, las alarmas de staging y las suscripciones de los dos topics. Contra Resend, solo lectura: uso, webhooks, supresiones, dominios, claves, métricas y dos páginas del listado de envíos. Contra el DNS público, con `dig`.
- **No comprobado.** Qué clave usa cada entorno. Si una clave `Sending access` puede enviar por plantilla. La forma real de un evento. Que el `Authentication-Results` de un correo real diga `dmarc=pass`. Si `support@auphere.com` existe.
- **No ejecutado**: es una spec. Nada se ha probado contra un entorno, ni se ha creado o enviado nada en Resend.
