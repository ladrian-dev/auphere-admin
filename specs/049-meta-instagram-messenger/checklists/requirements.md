# Lista de calidad de la especificación: Instagram y Messenger como canales

**Propósito**: validar que la spec está completa antes de planificar
**Creada**: 2026-10-29
**Feature**: [spec.md](../spec.md)

## Calidad del contenido

- [x] Sin detalles de implementación (lenguajes, frameworks, APIs). Las referencias a RLS e identificadores de plataforma son del encabezado obligatorio de Auphere, no de diseño
- [x] Centrada en el valor para el negocio y el cliente final
- [x] Escrita para quien no es técnico
- [x] Todas las secciones obligatorias completas

## Completitud de requisitos

- [x] Sin marcas `[NEEDS CLARIFICATION]` (las decisiones quedan en Supuestos)
- [x] Requisitos comprobables y sin ambigüedad (formato EARS)
- [x] Criterios de éxito medibles
- [x] Criterios de éxito sin tecnología
- [x] Escenarios de aceptación definidos
- [x] Casos límite identificados
- [x] Alcance acotado (sección Fuera de alcance)
- [x] Dependencias y supuestos identificados

## Preparación de la feature

- [x] Cada requisito tiene criterios de aceptación
- [x] Los escenarios cubren los flujos principales
- [x] La feature cumple los resultados medibles
- [x] Sin fugas de implementación

## Puertas de la constitución

- [x] Superficie de confianza declarada (`0`)
- [x] Garantías de aislamiento declaradas (1, 4, 6, 8)
- [x] Medidor declarado (modelo)
- [x] Nota de KB citada: ADR-049 (Messenger) y enmienda 1 de ADR-030 (inicio de sesión unificado), aceptados por el owner el 2026-10-29

## Notas

- Decisiones tomadas por defecto y **confirmadas por el owner el 2026-10-29**: (1) publicar contenido y anuncios fuera de alcance; (2) primera conexión por el operador; (3) permisos de Instagram y Messenger en un envío de revisión aparte del de catálogo.
