# Bug Assessment: lo que el partner elige para su teammate no llegaba al turno

- **Slug**: lo-que-el-partner-elige-no-llega-al-teammate
- **Created**: 2026-09-22
- **Source**: auditoría del 2026-09-19 (informe 02, dos P1), re-verificada hoy contra
  el código al investigar «¿qué sabe un teammate de sí mismo?»
- **Verdict**: valid
- **Severity**: high — no hay datos en riesgo, pero **dos de las cuatro decisiones
  del alta no hacían nada**, y una de ellas dejaba al teammate sin poder terminar
  su trabajo

## Symptom

El formulario de alta de un teammate declara en su propia cabecera: «Cuatro
decisiones y ninguna más: cómo se llama, de qué trabaja, **con qué cerebro** y
**qué se le deja hacer**». Dos de esas cuatro no llegaban al turno.

### 1 · El cerebro era decorativo

El partner elige un modelo de la lista de su partner, con su etiqueta de coste
relativa. La API lo valida (`teammates.py:_check_model`), lo guarda, y el cambio
se anota en el hilo de cada persona —`CHANGED_FIELDS` incluye `model`, así que
la interfaz dice «cambió el cerebro»—.

El run compilaba el grafo con `settings.llm_companion_model`. **Siempre, para
todos.** Elegir un modelo mejor para el teammate de investigación no cambiaba
nada, y la interfaz afirmaba que sí.

### 2 · Tres de los cinco interruptores entregaban un teammate que no puede terminar

`console.apply` vivía dentro del conjunto de `write`. Pero **proponer** se
reparte en cuatro interruptores:

| Interruptor | Propuestas que da | ¿Podía aplicar? |
|---|---|---|
| `write` | 11 | sí |
| `publish` | `console.propose_publish` | **no** |
| `spend` | cupo y modelo del cliente | **no** |
| `contact` | invitar, y los dos de soporte | **no** |

Un teammate con «publicar» y sin «escribir» proponía publicar, la persona
confirmaba, y la confirmación moría con `not_in_catalog`. El recorrido completo
del producto —proponer, confirmar, aplicar— quedaba cortado en el último paso
para tres de los cinco interruptores.

## Root cause

**Los dos defectos son la misma forma de error**: lo que el partner configura se
valida y se guarda con cuidado, y luego el turno no lo lee.

- **El cerebro**: `_get_companion_graph()` no recibía ningún modelo; leía el de
  los ajustes globales. El `teammate.model` se leía junto al catálogo y la
  identidad (`companion.py:~986`) y no se pasaba al driver.
- **Aplicar**: `_WRITE_NAMES` se construyó como «todo lo que propone, menos lo
  de los otros tres interruptores», y `APPLY_TOOLS` entró en ese «todo lo que
  propone». Aplicar no es una propuesta: es **la puerta de confirmación**, y
  restarla de los otros tres se la quitaba a quien sí la necesitaba.

## Reproduction

1. Crear un teammate con un modelo distinto al de `llm_companion_model` y pedirle
   un turno. El grafo se compila con el de los ajustes.
2. Crear un teammate con `read: true, publish: true` y el resto en falso. Pedirle
   que publique una versión. Propone; al confirmar, `not_in_catalog`.

## Scope

- **No toca ninguna frontera de tenant ni de persona.** Ninguna de las ocho
  garantías de aislamiento queda rozada: el catálogo sigue siendo un subconjunto
  de `ALL_TOOLS` y lo vigila `test_33`.
- **Amplía lo que un teammate puede hacer**, y por eso conviene decir por qué no
  es una escalada: `console.apply` no decide nada por sí sola — exige una acción
  que **una persona ya confirmó**. Dársela a quien puede proponer no le da
  ninguna capacidad nueva; le deja terminar la que ya tenía. Un teammate de solo
  lectura sigue sin ella, porque no tendría nada que aplicar.
- El cerebro por teammate **no** se cachea: un grafo compilado para uno no vale
  para el siguiente. Tiene test propio, porque ese fallo solo se vería en
  producción, con varios teammates y bajo carga.

## Por qué entra por el flujo de bug y no por spec

Los dos son defectos **contra lo que la spec 003 ya prometía**: su Requisito 2
declara el modelo y los permisos como decisiones del partner que cambian lo que
el teammate hace. No hay comportamiento nuevo que especificar — hay una promesa
que no se cumplía.

Lo que sí es spec, y no entra aquí: **instrucciones propias por teammate**,
toolset de trabajo, fecha y hora, paridad entre el prompt y el catálogo real. Eso
es la 015, y el informe 02 de la auditoría ya lo pedía por escrito.
