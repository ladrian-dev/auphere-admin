# Checklist de calidad de la especificación: la cuota cobra por carril

**Propósito**: validar que la spec está completa antes de planificar
**Creada**: 2026-09-14
**Feature**: [spec.md](../spec.md)

## Calidad del contenido

- [x] Sin detalle de implementación (lenguajes, frameworks, API)
- [x] Centrada en el valor y la necesidad de negocio
- [x] Legible por alguien que no programa
- [x] Todas las secciones obligatorias completas

> Nota sobre el primer ítem: la spec nombra tablas y puntos de cálculo del
> sistema (catálogo de modelos, los dos sitios que calculan cuota). La plantilla
> propia de este repo **lo exige** — el encabezado Auphere pide declarar por qué
> columna alcanza la RLS a cada entidad — y la spec 004 sienta el mismo
> precedente. No se nombra ningún lenguaje, framework ni firma de función.

## Completitud de los requisitos

- [x] **No quedan marcas `[NEEDS CLARIFICATION]`** — las dos se cerraron en
      `/speckit-clarify` el 2026-09-14, y una tercera decisión que la spec había
      dado por supuesta se cerró con ellas:
      - multiplicador objetivo → **2,2x** (54,5 %), enmendando a la baja el 65 %
        del ADR-037
      - R2.4 resolución de la columna del peso → **se amplía la escala**
      - R5.3 saldo comprado y bolsas en curso → **sólo consumo nuevo**
- [x] Requisitos comprobables e inequívocos (EARS, verbo normativo único)
- [x] Criterios de éxito medibles
- [x] Criterios de éxito sin tecnología dentro
- [x] Escenarios de aceptación definidos en las tres historias
- [x] Casos límite identificados (redondeo, modelo sin carril de cuota, carril
      con tarifa nula, ausencia diseñada)
- [x] Alcance acotado — «Fuera de alcance» separa explícitamente la decisión
      comercial de las bolsas, que **no** es parte de esta corrección
- [x] Dependencias y supuestos identificados

## Preparación de la feature

- [x] Cada requisito funcional tiene criterios de aceptación
- [x] Las historias cubren los flujos principales (margen, factura del partner,
      mantenimiento del catálogo)
- [x] La feature satisface los criterios de éxito declarados
- [x] No se filtra detalle de implementación a los criterios de éxito

## Puertas de la constitución que esta spec ya deja resueltas

- [x] **Superficie declarada** (§II) — `0`, y se explica por qué no abre ninguna
- [x] **Aislamiento** (§I) — se declara la garantía tocada y que
      `tests/isolation/test_pool_not_exposed_to_tenant.py` queda incompleto
- [x] **Medidor** — es el objeto entero de la spec
- [x] **Nota de KB** (§IX) — ADR-037, con las dos afirmaciones que se refutan
- [x] **Licencias** (§VIII) — confirmado en el plan: **ninguna dependencia
      nueva**. Nada que leer ni que citar
- [x] **Constitution Check completo** — las nueve filas rellenas en
      [plan.md](../plan.md), y re-evaluadas tras el diseño

## Notas

- La puerta «cero `[NEEDS CLARIFICATION]`» de la constitución **está abierta**:
  no queda ninguna. El paso siguiente es `/speckit-plan`.
- `/speckit-clarify` destapó que los márgenes que afirma el ADR-037 (62 % / 39 %)
  corresponden a un multiplicador de 2,857x — el 65 % que `billing/pricing.py`
  declara. La migración `0115` nunca lo implementó. La spec fija 2,2x a
  sabiendas y R7 obliga a corregir el ADR y el comentario en el mismo commit.
- Las cifras de la spec están verificadas contra las migraciones `0072`, `0076`,
  `0114`, `0115` y `0116` y contra `billing/pricing.py`, no contra el resumen que
  originó el encargo.
- **La Fase 0 amplió el alcance** (`research.md` D4): la cuota ponderada no sólo
  se calcula al debitar, también está **persistida** en `companion.runs` y se
  des-pondera con una constante que deja de serlo. Queda justificado en
  Complexity Tracking. La spec no lo predijo y no hace falta reabrirla: no cambia
  ningún requisito, cambia cuánto cuesta cumplirlos.
