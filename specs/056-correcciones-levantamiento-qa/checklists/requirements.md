# Checklist de calidad de la spec: Correcciones del levantamiento QA de la consola del cliente

**Propósito**: comprobar que la spec está completa y bien hecha antes de `/speckit-plan`
**Creada**: 2026-11-07
**Spec**: [spec.md](../spec.md)

## Calidad del contenido

- [x] Sin detalles de implementación (lenguajes, frameworks, APIs)
- [x] Centrada en el valor para el usuario y el negocio
- [x] Escrita para alguien que no programa
- [x] Todas las secciones obligatorias completas

## Requisitos completos

- [x] No queda ninguna marca [NEEDS CLARIFICATION]
- [x] Los requisitos se pueden probar y no son ambiguos
- [x] Los criterios de éxito se pueden medir
- [x] Los criterios de éxito no nombran tecnología
- [x] Todos los escenarios de aceptación están definidos
- [x] Los casos límite están identificados
- [x] El alcance está acotado
- [x] Dependencias y supuestos identificados

## Lista para planificar

- [x] Cada requisito funcional tiene criterios de aceptación claros
- [x] Las historias cubren los recorridos principales
- [x] La feature cumple los resultados medibles de los criterios de éxito
- [x] No se cuelan detalles de implementación en la spec

## Notas

- **Detalles técnicos a propósito.** Como la spec 055, el «Origen» y el encabezado nombran commits, rutas y la regla C8 para que se puedan comprobar. Los requisitos describen comportamiento: dicen qué ve y qué puede hacer cada persona, no cómo se construye. Las rutas que aparecen en ellos (`/agentes`, `/negocio`) son las que ve la persona en la barra de direcciones.
- **Decisiones pendientes del owner.** Ninguna marca abierta: D1 a D10 llevan una propuesta. La spec no pasa a `/speckit-plan` hasta que el owner las apruebe o las cambie. **D3** (la Bandeja pasa por Auphere) es la que decide si C8 se enmienda.
- **Puertas de la constitución.** Superficie declarada (`0`). Garantías tocadas declaradas (1, C8 y la 8 rozada), con su prueba pedida en los Requisitos 3.10, 4.6 y 2.5. Medidor declarado (Requisito 1.6). Sin dependencias nuevas.
- **Dependencia externa.** La regla del calendario compartido viene de la rama `reservas-fuente-unica-631d6d`, que tiene que estar fusionada antes de cerrar esta spec.
- **Pendiente antes de `/speckit-plan`.** La nota de KB con la enmienda de ADR-041 y de la spec 047 (R50), por la constitución §IX.
