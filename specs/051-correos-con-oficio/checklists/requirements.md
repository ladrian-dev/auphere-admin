# Lista de calidad de la spec: Correos con oficio

**Propósito**: validar que la spec está completa y es de calidad antes de planificar
**Creada**: 2026-10-30
**Spec**: [spec.md](../spec.md)

## Calidad del contenido

- [x] Sin detalles de implementación (lenguajes, frameworks, APIs). Resend aparece como decisión del owner y como proveedor ya existente, no como elección técnica de la spec
- [x] Centrada en el valor para quien recibe el correo y para el equipo
- [x] Legible por alguien que no programa
- [x] Todas las secciones obligatorias completas, más el encabezado Auphere

## Completitud de los requisitos

- [x] No quedan marcas `[NEEDS CLARIFICATION]`: las cuatro decisiones abiertas las tomó el owner el 2026-10-30
- [x] Los requisitos se pueden probar y no son ambiguos (EARS)
- [x] Los criterios de éxito se pueden medir
- [x] Los criterios de éxito no dependen de la tecnología
- [x] Todos los escenarios de aceptación están definidos
- [x] Los casos límite están identificados
- [x] El alcance está acotado (sección «Fuera de alcance»)
- [x] Dependencias y supuestos identificados

## Preparación

- [x] Cada requisito funcional tiene su criterio de aceptación
- [x] Los escenarios cubren los flujos principales
- [x] La funcionalidad cumple los resultados medibles de los criterios de éxito
- [x] No se cuelan detalles de implementación en la spec

## Notas

- **Decisión propia, para revisar al final**: el remitente de los correos que no son de cobro pasa de `no-reply@auphere.com` a una dirección de notificaciones (R5.2). Un «no responder» contradice el `reply_to` a soporte que pidió el owner. Enmienda la regla «es un no-reply explícito» de la spec 006 (R1.1): se conserva lo que protegía, que el alta no salga de facturación.
- **Decisión del owner que enmienda la spec 011**: la spec 011 (§6 de `docs/recuperar-la-contrasena.md`) descartó escribir el enlace de restablecimiento en los registros. Con D2, staging lo escribe. La guardia que lo hace aceptable es R1.3: producción no arranca en modo registro, así que el enlace nunca llega a los registros de producción.
