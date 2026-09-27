# Fase 1 · Modelo de datos

**Esta spec no crea ni migra ninguna tabla.** No hay `alembic` en el plan. Lo
que sigue es el **modelo de lectura**: qué junta cada pantalla, de dónde sale y
por qué columna lo alcanza la RLS.

Se escribe igualmente porque el riesgo de una pantalla que junta lecturas no es
el esquema: es **enseñar de un cliente algo que su ficha no enseñaba**, o
enseñar de uno lo de otro.

---

## Resumen del cliente (lectura compuesta)

Cuatro bloques, cuatro fuentes, ningún dato nuevo.

| Bloque | Campos que enseña | Fuente | Acotado por |
|---|---|---|---|
| **¿Atiende?** | estado del cliente, salud (agente publicado · canal activo · tenant activo), pasos de puesta en marcha, siguiente paso | ficha del cliente | `partner_tenants` del partner → `tenant_id` |
| **¿Cuánto consume?** | créditos restantes y tope, unidades del mes, proyección de fin de mes, días de base | informe de consumo acotado a un cliente | `tenant_id = ANY(tenants del partner)` |
| **¿Cómo va la conversación?** | conversaciones, escaladas, mensajes fallidos (30 días) | estadísticas de conversación del cliente | `ClientScope` → `tenant_id` |
| **¿Qué tiene conectado?** | canales activos y conectores con su estado | canales + conectores del cliente | `ClientScope` → `tenant_id` |

**Datos editables desde el Resumen** (Requisito 2): nombre del cliente y zona
horaria. Son campos del **tenant**, no del agente, y por eso su edición no toca
el borrador.

### Invariantes que el Resumen no puede romper

1. **Nada nuevo se enseña.** Cada cifra del Resumen existe hoy en alguna
   pantalla de la ficha o en `/usage` filtrado por ese cliente. El Resumen
   cambia el número de clics, no el permiso.
2. **Cada bloque respeta el permiso de su fuente.** Quien no puede leer
   consumo no ve el bloque de consumo; no ve un bloque vacío ni un error.
3. **Un cliente ajeno es un 404 opaco**, igual en el Resumen que en cualquiera
   de sus fuentes, y ninguno de los cuatro bloques puede delatar por su forma
   ni por su tiempo que ese cliente existe.

---

## Elemento de catálogo (forma común)

Habilidades, Conectores y Canales son tres listas distintas que se recorren
igual. El patrón no inventa una entidad: define **la forma mínima que las tres
comparten** para poder navegarse.

| Campo | Qué es | Habilidades | Conectores | Canales |
|---|---|---|---|---|
| `id` | identificador estable dentro de su catálogo | clave de la capacidad | slug del conector | tipo de canal |
| `nombre` | cómo lo llama el negocio | nombre de negocio | nombre visible | nombre visible |
| `descripción` | una línea | descripción de negocio | qué hace | qué hace |
| `categoría` | por dónde se agrupa y se filtra | función (Citas, Pedidos…) | categoría del conector | — (uno solo hoy) |
| `activo` | si **este cliente** lo tiene | encendida en el borrador | conectado | conectado |
| `estado` | matiz del activo | en la versión activa · le falta su conector · aún no disponible | conectado · pausado · error · sin conectar | ídem |

**Lo que el patrón NO define**: qué se hace al pulsarlo. Encender una habilidad,
pegar una URL de agenda y conectar un canal son tres acciones distintas con tres
diálogos distintos, y cada pantalla se queda con la suya. El patrón navega; no
actúa.

**Regla de la ausencia (constitución §V)**: un canal o conector que todavía no
existe **no es un elemento del catálogo**. No se enseña apagado ni «próximamente».
Si no se puede conectar, no está en la lista.

---

## Lo que NO cambia

- Ninguna tabla, ninguna columna, ninguna migración.
- Ninguna política de RLS.
- Ningún registro del medidor: el Resumen lee `usage_records`, nunca escribe.
- Ningún permiso: los roles siguen pudiendo exactamente lo mismo, desde sitios
  distintos.
