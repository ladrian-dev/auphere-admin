# Idea Intake: un teammate de Auphere que enseña a fabricar el agente del cliente

- **Slug**: teammate-guia-de-auphere
- **Created**: 2026-09-20
- **Source**: sesión del 2026-09-20. Luis: «el objetivo de nuestros clientes es crear
  agentes para sus clientes de una forma eficiente y efectiva (quizás considerar que
  por defecto haya un Teammate definido que sea especialista en Auphere y lo guíe y
  ayude a configurar los agentes de su cliente de forma efectiva, haciendo las
  preguntas adecuadas en los momentos adecuados, **no haciendo agentes genéricos**)»
  · punteros: `apps/api/src/nexus_api/companion/tools/catalog.py`,
  `services/templating/seeds/`, `apps/console/src/app/(console)/clients/new/` ·
  auditorías: KB `research/2026-09-19-auditoria-clase-mundial/03-fabrica-de-agentes`
  y `06-referentes-externos` §B
- **Type**: feature (y la que más cerca está del negocio: es el producto, no una
  comodidad)

## El problema, medido

Un partner no técnico crea un cliente y publica un agente razonable en unos dos
minutos: el asistente de alta y las trece plantillas verticales son buenos, con
prompts reales de entre 1.500 y 15.700 caracteres. **Pero se queda solo justo
después**, y lo que le queda delante es esto:

- el «prompt» es un textarea monoespaciado con el system prompt entero;
- «mejorar prompt», la biblioteca de patrones y los evals **existen y funcionan**,
  pero solo en el panel de operador de Auphere, no en su consola;
- no puede probar un borrador: el playground carga la versión activa;
- después de publicar ve metadatos de conversaciones, nunca el texto, así que no hay
  forma de decir «esto lo contestó mal, arréglalo».

Traducido: **el partner publica a ciegas un prompt que no sabe editar, y no se entera
de si funciona.** El resultado son agentes genéricos — que es exactamente lo que Luis
quiere evitar.

*(Estos cuatro puntos vienen de la auditoría del 2026-09-19; verifiqué el tercero y
el primero.)*

## Lo que ya existe y nadie usa

El Companion —el asistente de la consola— **ya sabe fabricar un agente por
conversación**: `propose_client`, `propose_prompt`, `propose_policy`, `propose_tools`,
`propose_knowledge` y `propose_publish`, todas con confirmación humana, registro
durable y reanudación. Está **apagado por partner** (`companion_enabled`, falso por
defecto) y, según la auditoría, ningún endpoint lo enciende: hace falta SQL.

O sea que la pieza cara está construida. Lo que falta no es el motor: es **el oficio**
—qué preguntar, cuándo, y qué hacer con la respuesta— y una forma de encenderlo.

## Lo que hacen los que ya lo resolvieron

De la investigación del 2026-09-19, el patrón dominante del sector es **un agente
construye el agente**, y ninguno enseña el prompt crudo:

- **Sierra Ghostwriter** parte de procedimientos, transcripciones o una descripción
  del negocio, y genera el agente **con sus tests**.
- **Intercom Fin** redacta el procedimiento desde un esquema, los contenidos y las
  conversaciones reales; el comportamiento se escribe en **lenguaje natural**, «just
  like you would when training a teammate», con pasos deterministas solo donde hay
  reglas duras.
- **Las conversaciones reales corregidas pasan a ser casos de regresión**, así que el
  agente «never makes the same mistake twice».
- Se publica por **versiones inmutables** con vuelta atrás, y hay un informe periódico
  de huecos de conocimiento con la conversación de origen.

## La idea

Que el partner, al entrar, **ya tenga un teammate esperándole** cuyo oficio es
Auphere: sabe cómo se monta un agente aquí, conoce las trece plantillas, sabe qué
distingue a una clínica dental de una barbería, y **entrevista**.

No «te genero un prompt». Más bien: qué servicios das, cuánto duran, qué precios,
quién atiende, qué haces cuando alguien pide hora fuera de horario, qué es una
urgencia y a quién se avisa, qué **no** debe contestar nunca el agente. Y de ahí sale
un borrador, se prueba, se corrige y se publica.

## Lo que hay que decidir, no dar por hecho

- **Si es un teammate o es el asistente de alta.** Un teammate vive en la app de
  escritorio; el alta de un cliente ocurre en la consola. Hoy son dos superficies
  distintas y la frase que ordena el producto dice «la consola configura, la app
  opera». Un teammate cuyo trabajo es configurar **choca con esa frase**, y hay que
  resolverlo a propósito, no por descuido.
- **Qué preguntas, y quién las escribe.** Es el corazón, y no lo escribe un modelo:
  es el oficio de Auphere puesto por escrito. ¿Un guion por vertical? ¿Uno general
  con ramas? Existe ya material que reutilizar en `prompt_library` (8 patrones) y en
  los seeds.
- **Si puede publicar o solo proponer.** Hoy `propose_publish` pasa por confirmación
  humana, y esa es la respuesta correcta; conviene no perderla por comodidad.
- **Qué pasa con `companion_enabled`.** ¿Se enciende para todos? ¿Deja de existir la
  bandera? Si el teammate viene por defecto, la bandera ya no protege nada.
- **Cómo sabe si el agente que fabricó es bueno.** Sin esto vuelve a ser un
  generador de prompts. Hay 8 datasets de eval por vertical y un runner que sabe
  evaluar un borrador: es la pieza que cierra el círculo.
- **Si el partner puede editar a este teammate.** Un teammate al que le cambian las
  instrucciones deja de ser el especialista de Auphere.

## Por qué esta es probablemente la más valiosa de las tres

Las otras dos evaluaciones abiertas hoy hacen que el partner trabaje mejor. Esta hace
que **sus clientes tengan mejores agentes**, que es el producto que se vende. Y es la
más barata: superficie 0, sin frontera nueva, sobre un motor ya construido y probado.

## Superficie de confianza

`0`. Sin frontera nueva: lee y propone sobre la API de la consola, con las
aprobaciones y el medidor que ya existen. El riesgo no es de aislamiento, es de
calidad — un guion malo produce agentes malos a escala.

## Fuera de alcance

Recuperar el texto de las conversaciones para corregir al agente desde una
conversación real. Es lo siguiente que hace falta, pero **choca con un test de
aislamiento** que hoy fija que las conversaciones son solo metadatos: se decide
aparte, no de rebote.
