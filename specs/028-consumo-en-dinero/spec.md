# Especificación: Consumo, una pantalla para el dinero

**Rama**: `develop` (decisión del owner) · **Creada**: 2026-10-03 · **Estado**: Aprobada (propuesta visual aceptada por el owner)

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`. Lecturas y acciones que ya existen, reordenadas |
| **Garantías de aislamiento tocadas** | Ninguna nueva. El gasto por día y por cliente se lee del libro bajo el partner de la sesión |
| **Nota de KB** | Spec 027 (el partner ve dinero) · heurísticas de Nielsen aplicadas a Consumo (owner, 2026-10-03) |
| **Qué se mide** | Nada nuevo |

## Origen

Consumo mezclaba dos trabajos —gestionar el dinero y leer el consumo técnico— en una docena de bloques: tres cifras de saldo, un formulario de compra siempre abierto, una tabla con un campo editable por fila, dos formularios sueltos para asignar y mover, filtros, cifras de mensajes, dos gráficas en unidades, tarjetas con nombres internos (`LLM.INPUT_TOKENS`) y una tabla técnica larga. Arriba dólares, abajo «unidades facturables». Falta lo esencial: quién gasta, cuánto y a qué ritmo, en dinero.

## Escenarios *(obligatorio)*

1. **Saldo de un vistazo** (P1): tres tarjetas — saldo disponible (incluido y comprado), asignado a clientes con lo que queda sin asignar, gasto del mes con su proyección. Una sola acción principal: «Comprar saldo», en un diálogo.
2. **Saldo por cliente** (P1): una fila por cliente con tope, gastado este mes y lo que le queda (barra y días si se acaba antes de fin de mes). Sin campos editables en la tabla: las acciones viven en «⋯» — cambiar tope, mover saldo a otro cliente, ver su consumo, abrir la ficha — y abren diálogos. «Asignar saldo a un cliente» para los que no tienen tope.
3. **Gasto por día en dólares** (P2): barras por día del periodo (7, 30 o 90 días), filtro por cliente, media diaria y, al pasar el ratón, el día con sus clientes que más gastaron.
4. **Detalle técnico plegado** (P3): mensajes, uso del modelo y multimedia, con la descarga CSV, dentro de un bloque plegado por defecto y con nombres legibles.

## Requisitos *(obligatorio)*

1. La API DEBE dar, en céntimos y bajo el partner de la sesión: la serie diaria de gasto del periodo (total y por cliente), el gasto del mes por cliente y la proyección del mes.
2. Ninguna fila de la tabla de saldo DEBE tener un campo editable a la vista; cambiar y mover se hacen en diálogos con el importe en dólares.
3. La pantalla DEBE tener una sola acción principal visible (Comprar saldo).
4. Ningún texto de la parte de dinero DEBE decir créditos, cupo, unidades o tokens (regla de la spec 027).
5. El detalle técnico NO se borra: se pliega y se rotula con nombres legibles.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Sin desplazar la página, el partner ve su saldo, cuánto ha asignado, cuánto lleva gastado este mes y quién gasta más.
- **CE-002**: Cambiar el tope de un cliente son tres pasos: «⋯», «Cambiar tope», guardar.
- **CE-003**: Ninguna cifra de la parte de dinero está en otra unidad que no sea US$.

## Fuera de alcance

- Pasar el detalle técnico por medidor a dinero.
- Cambiar las alertas de mensajes del mes.
