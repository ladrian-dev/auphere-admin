# Checklist de calidad de la especificación: el registro de partners

**Propósito**: validar que la spec está completa y es de calidad antes de pasar a planificación
**Creado**: 2026-09-13
**Feature**: [spec.md](../spec.md)

## Calidad del contenido

- [x] Sin detalles de implementación (lenguajes, frameworks, APIs)
- [x] Centrada en el valor de usuario y la necesidad de negocio
- [x] Escrita para interlocutores no técnicos
- [x] Todas las secciones obligatorias completadas

## Completitud de los requisitos

- [x] **No quedan marcas `[NEEDS CLARIFICATION]`** — las 6 cerradas el 2026-09-13. Ver Notas
- [x] Los requisitos son comprobables y no ambiguos
- [x] Los criterios de éxito son medibles
- [x] Los criterios de éxito son agnósticos de tecnología
- [x] Todos los escenarios de aceptación están definidos
- [x] Los casos límite están identificados
- [x] El alcance está acotado (§Fuera de alcance, con la razón de cada exclusión)
- [x] Dependencias y supuestos identificados (§Supuestos y §«Lo que ya existe»)

## Encabezado Auphere (puertas de la constitución)

- [x] **Superficie de confianza declarada** — `0`, con la frase que explica qué
      modo nuevo abre dentro de ella (escritura anónima que crea una fila raíz)
- [x] **Garantías de aislamiento tocadas declaradas** — 1, 4 y 6, cada una con lo
      que la toca
- [x] **Nota de KB que la justifica** — `ADR-038-registro-autonomo-de-partners`
      escrito el 2026-09-13 en la KB y enlazado desde `decisions/_index.md`
- [x] **Qué se mide declarado** — nada nuevo en el medidor; el envío de correo se
      contiene por ritmo, y se dice por qué

## Preparación de la feature

- [x] Todos los requisitos funcionales tienen criterios de aceptación claros
- [x] Los escenarios cubren los recorridos principales
- [x] Los criterios de éxito cubren lo que la feature promete
- [x] Ningún detalle de implementación se cuela en la spec

## Notas

**Las marcas abiertas son intencionadas y el encargo las pidió así.** Cuatro
salen literalmente de `docs/pendientes-tras-el-go-live.md` §1 y la instrucción
fue no suponerlas. La quinta la abre el propio encargo del inicio de sesión con
Google. La sexta es de proceso, no de producto.

| # | Dónde | Qué decide |
|---|---|---|
| 1 | R1.6 | ¿Registro abierto o por invitación / lista de espera? |
| 2 | R2.4 | ¿Verificar el correo basta, o hace falta comprobación humana? |
| 3 | H2 esc. 3 | ¿Se dan de alta clientes finales antes o después de contratar? |
| 4 | R6.3 y caso límite | ¿Qué pasa con un registro que nunca paga? |
| 5 | H3 esc. 5 | ¿Proveedor de identidad de terceros o Google directo? |
| 6 | Encabezado | El ADR de KB que la constitución §IX exige — escrito como ADR-038 |

**Cerradas todas el 2026-09-13.** Las cinco de producto en `/speckit-clarify`
(ver §Clarificaciones de la spec); la sexta escribiendo
`ADR-038-registro-autonomo-de-partners` en la KB, que es donde la constitución
§IX quiere el porqué. La spec pasa la puerta de «cero marcas antes de planificar».

> Desviación consciente de la guía genérica de `/speckit-specify`, que limita a
> 3 las marcas: aquí gana la instrucción explícita del encargo y la puerta real
> del repo, que es «cero marcas antes de planificar», no «como mucho tres».
