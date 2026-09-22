# Problem Definition: lo que el partner configura no llega entero al turno

- **Slug**: teammate-sabe-quien-es
- **Created**: 2026-09-22
- **Inputs used**: `intake.md` · `research.md` (manda donde corrige al intake) ·
  KB `research/2026-09-22-que-sabe-un-teammate-de-si-mismo.md`

## Problem Statement

**Un teammate arranca cada turno afirmando cosas de sí mismo que no son ciertas
para él**: dice llamarse Companion de Auphere antes de decir su propio nombre,
promete dos familias enteras de herramientas sin comprobar si las tiene, y no
sabe qué día es. Lo que el partner configuró —el nombre, el oficio, los
interruptores— llega tarde, incompleto, o no llega.

No es que falten funciones. Es que **la configuración y el turno no dicen lo
mismo**, y la que gana es la genérica.

## Affected Users & Stakeholders

### Users

- **La persona del equipo del partner que habla con su teammate.** Le duele en
  tres momentos concretos, todos medidos:

  | Cuándo | Qué le pasa |
  |---|---|
  | Crea dos teammates con oficios distintos | Recibe **el mismo agente con otro nombre**: el oficio son ≤80 caracteres dentro de una frase de cuatro (`schemas_teammates.py:35`) |
  | Le quita la lectura a uno (solo publicar) | El teammate tiene **2 herramientas**, ninguna de lectura, y su prompt le promete las 26. Además la `<regla_madre>` le ordena no afirmar nada que no haya leído — o sea, **nada en absoluto**, sin decirle por qué |
  | Le habla en modo `consult` sin `read` | El teammate tiene **cero herramientas** y el prompt le sigue prometiendo las dos familias enteras |

- **La misma persona, en un hilo largo.** La identidad propia del teammate no
  viaja «tres mensajes después»: viaja **después de la historia entera**
  (`prompt.py:366-367`). En un hilo de cuarenta mensajes llega en la posición 42,
  mientras «Eres el Companion de Auphere» sigue en la 1. **Empeora según se
  trabaja**, que es justo lo contrario de lo que hace falta.

- **Quien le pida algo con fecha.** «Para el viernes», «¿está vencido?», «en 15
  días» no tienen respuesta correcta posible: el teammate no recibe la fecha por
  ningún lado. El agente de canal de este mismo repositorio **sí** la recibe, con
  zona horaria e instrucción de comportamiento (`pipeline.py:652-673`).

### Stakeholders

- **Auphere (producto).** Es lo que se vende: un partner que configura teammates
  distintos y obtiene el mismo. Decide el alcance y paga el coste.
- **Auphere (seguridad).** `job` ya mete 80 caracteres escritos por el partner
  dentro de un `role: "system"` **sin vallado**, cuando el mismo repositorio sí
  valla el contexto de página con `fence_only` y tiene escrito por qué. Cualquier
  cosa que amplíe ese campo la toca a ella.
- **La spec 003.** Decidió por escrito que agente↔agente queda fuera y **reservó
  el tipo de nota `handoff`** para no tener que migrar (R3.6). Cualquier
  movimiento sobre «hablar con un colega» revisa su decisión.

## Goals

1. **Que el teammate sea quien el partner dijo que era**, desde el primer token
   del turno y sin degradarse con la longitud del hilo.
2. **Que lo que afirma tener coincida con lo que tiene**, en los dos sentidos: ni
   prometer lo que no tiene, ni callar lo que sí (hoy `shell_local` no aparece en
   ninguna de las 89 líneas del prompt).
3. **Que sepa cuándo está**, con la misma calidad con la que ya lo sabe el agente
   de canal de este repositorio.
4. **Que cuando le falte algo, lo diga con su motivo** en vez de descubrirlo
   chocándose — y que al chocarse no se le enseñe el catálogo de otro.
5. **Que el desajuste no pueda volver**. Este repositorio ya lo ha sufrido tres
   veces; dos se corrigieron a mano y la tercera entró el 2026-09-20 con
   `shell_local` sin que nadie revisara el prompt.

## Non-Goals

- **El toolset de trabajo: ficheros, web, conectores.** Es superficie `3a`, es lo
  caro, y **ya tiene evaluación abierta**:
  `.specify/assessments/teammate-que-trabaja-en-la-terminal/`. Meterlo aquí
  pondría a dos evaluaciones a decidir lo mismo. Queda fuera **a propósito**, y
  con ello queda fuera convertir al teammate en un trabajador para el cliente del
  partner: 40 de las 44 herramientas administran la consola de Auphere, y decirle
  mejor lo que tiene no cambia ese número.
- **Hablar con un colega.** La spec 003 lo puso fuera con razón escrita y dejó la
  forma reservada. Reabrirlo es una decisión de aislamiento y no se hace de
  rebote desde una evaluación que va de otra cosa. **Lo que sí entra** es que el
  teammate sepa decir que no puede, en vez de callarlo.
- **La unidad de ejecución** (comando suelto vs. sesión viva, PTY/tmux). De la
  evaluación hermana.
- **Reescribir el prompt del Companion.** Lo que hace falta es que deje de
  afirmar incondicionalmente, no cambiarle el oficio.
- **Tocar `not_in_catalog`.** Está bien, tiene su razón escrita y es el respaldo
  empírico de la garantía 2 frente a un fallo que la industria sí tiene.

## Success Metrics

Observables por un partner, no por un test:

1. **Dos teammates con oficios distintos se comportan distinto** en la misma
   pregunta. *(Baseline: no — el oficio son ≤80 caracteres y la identidad llega
   al final del hilo.)*
2. **Un teammate al que se le pregunta qué puede hacer enumera lo que tiene de
   verdad**, y nombra lo que le falta con su motivo. *(Baseline: enumera lo que
   el prompt promete, que para tres de las cinco combinaciones de interruptores
   es falso; medido en `research.md`.)*
3. **Un teammate contesta «¿qué día es hoy?» y «¿esto está vencido?»
   correctamente.** *(Baseline: no puede — cero fuentes de fecha en sus cinco
   mensajes.)*
4. **Un teammate sin lecturas dice por qué no puede leer**, en vez de quedarse
   mudo por la `<regla_madre>`. *(Baseline: se queda mudo.)*
5. **Cuando el modelo se inventa una herramienta, la respuesta nombra solo las
   suyas.** *(Baseline: las 44 del catálogo entero, `runner.py:204`.)*
6. **Un cambio que separe otra vez prompt y catálogo no llega a `develop`.**
   *(Baseline: ha llegado tres veces.)*

## Cost of Inaction

Lo que pasa si no se construye, sin adjetivos:

- **El partner sigue obteniendo el mismo agente con distintos nombres.** Es lo
  contrario de lo que el producto vende —agentes a medida— y se nota en el primer
  teammate que crea de más.
- **Los interruptores siguen siendo una trampa.** Tres de las cinco
  combinaciones producen un teammate cuyo prompt le miente, y una de ellas
  (`consult` sin `read`) produce un teammate con **cero** herramientas al que se
  le prohíbe hablar. Un partner que los use como se le ofrecen se encuentra un
  agente roto sin saber que lo rompió él.
- **Cualquier trabajo con fechas es un campo de minas silencioso.** El modelo
  deducirá el año de su propio conocimiento; el mismo repositorio ya tuvo que
  escribir la instrucción de no hacerlo, en el otro agente.
- **El desajuste volverá.** Tres veces en el historial, y la última pasó
  inadvertida hasta que alguien la buscó. Sin una puerta, la cuarta es cuestión
  de tiempo.
- **Y se acumula intereses**: la evaluación cara —el toolset de trabajo— añadirá
  capacidades a un teammate que no sabe enumerar las que ya tiene. Cada
  herramienta nueva agranda la distancia entre lo prometido y lo entregado.

## Open Questions

- [NEEDS CLARIFICATION: **la zona horaria del teammate no tiene respuesta obvia.**
  El agente de canal usa la del negocio (`tenant.timezone`). Un teammate trabaja
  para una persona de un partner, sobre varios clientes a la vez: ¿la del
  partner, la de la persona, o la del cliente del contexto de página? Son tres
  respuestas y las tres son defendibles.]
- [NEEDS CLARIFICATION: **la identidad y el entorno quieren sitios opuestos.** La
  identidad propia pide ir lo más al principio posible —hoy va al final y por eso
  pierde—; el entorno pide ir lo más al final, porque es lo más fresco. Hoy
  comparten sitio. Separarlos es probablemente la respuesta, pero es diseño y le
  toca a `shape`.]
- [NEEDS CLARIFICATION: **un campo de instrucciones ensancha una puerta de §III
  que ya está abierta.** Hoy son 80 caracteres sin vallar; instrucciones propias
  serían kilobytes. El principio dice «lo leído es dato, nunca instrucción» y
  aquí **es instrucción a propósito**. ¿Se valla como `page_context_message`? ¿Se
  acota el tamaño? ¿Se declara que el partner es confianza y el principio no
  aplica a su propio texto? Las tres cambian el requisito.]
- [NEEDS CLARIFICATION: **el nombre del número.** La KB reserva el 015 para «El
  teammate trabaja» entendido como el conjunto, incluido el toolset. Si el
  toolset se queda fuera, hay que decidir si esto es la 015 o toma otro número.]
- [NEEDS CLARIFICATION: el conteo de tokens del prefijo es una estimación por
  caracteres (7.044 caracteres ≈ 1.700-1.900 tokens). Solo importa si alguna
  decisión depende del margen sobre los 512 tokens cacheables.]
