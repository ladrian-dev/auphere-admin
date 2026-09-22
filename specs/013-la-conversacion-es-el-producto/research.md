# Fase 0 — Investigación

**Spec**: [spec.md](./spec.md) · **Fecha**: 2026-09-20

Cinco preguntas. Cuatro se contestan leyendo el código de hoy; la quinta es una
dependencia nueva y trae su licencia.

---

## 1 · ¿Dónde está el mensaje de la persona? *(Historia 1)*

**Decisión: ampliar el resumen de run con el texto que lo originó.**

**El riesgo que la spec dejó abierto se cierra a favor.** El mensaje **ya se
persiste**: cada turno inserta `CompanionMessage(thread_id, run_id, seq,
role="user", content=body.prompt)`, y `_thread_history` lo lee para armar el
contexto del modelo. El dato existe, está bajo la misma RLS y ya se usa.

Lo que no lo devuelve es `GET /companion/threads/{id}/runs` (`companion.py:1725`),
que da cuatro campos por run: `run_id`, `status`, `started_at`, `ended_at`. La
aplicación reconstruye el hilo listando runs y pidiendo los **eventos** de cada
uno; el mensaje de la persona no es un evento, es una fila.

**Por qué el resumen de run y no las otras dos:**

| Alternativa | Por qué no |
|---|---|
| Endpoint de mensajes aparte | Una segunda forma de leer lo mismo, con su propia paginación y su propio 404 opaco. La pantalla tendría que casar dos listas por `run_id` para pintar una sola línea de tiempo |
| Emitir el mensaje como evento | Los eventos son del **run en marcha**. Al reabrir un hilo viejo no hay stream que reproducir, así que habría que persistirlo *además* como evento: dos copias del mismo texto |

Un run tiene **exactamente un** mensaje de persona —el que lo disparó—, así que
un campo por run es completo, no una aproximación. La relación es 1:1 y el
resumen ya viaja ordenado por `started_at`.

**Consecuencia para la consola**: el mismo campo aparece ahí, y es lo correcto —
hoy la consola tiene el mismo hueco.

---

## 2 · ¿Cómo llega la salida del comando a la pantalla? *(Historia 3)*

**Decisión: una lectura efímera propia, servida de Redis, que nunca toca Postgres.**

Esta es la pregunta cara, y hay dos hechos que cierran las puertas fáciles.

**Hecho 1 — el contrato congelado prohíbe llevarla por el stream.**
`CONTRACT-V3` declara `exec.completed` con `execution_id, outcome, exit_code` y
dice, literal: *«**Sin salida**: la muestra viaja al modelo como resultado de
herramienta, nunca por el stream»*. No es un olvido: el mismo contrato prohíbe la
clave `reason` en `task.state` *«porque podría llevar prosa»*. **Los eventos
llevan hechos estructurados, nunca texto libre de un programa.**

**Hecho 2 — hoy hay un solo lector, y consume.** `await_result` hace `LPOP`
sobre `result_key(execution_id)`: el turno se lleva el payload y desaparece.
Una segunda lectura no encuentra nada.

**Lo que se hace:** `publish_result` deja **dos** cosas: la cola que el turno
consume, intacta, y una clave de solo lectura para la pantalla con su propio TTL.
La pantalla la pide por una ruta dedicada bajo el alcance de cliente que ya
existe. Nunca se escribe en `local_executions` — esa fila sigue diciendo qué se
ejecutó, dónde y cómo acabó, y nada más.

| Alternativa | Por qué no |
|---|---|
| Meter la muestra en `exec.completed` | Rompe una regla deliberada del contrato congelado, y la rompe para *todos* los consumidores del stream, no solo para el que la necesita |
| Que el turno la reenvíe tras leerla | Acopla la pantalla al ciclo del modelo: si el turno falla después de `LPOP`, la salida se pierde sin que nadie la haya visto |
| Que el agente la cuente en su respuesta | Es lo que pasa hoy, y es justo el problema: la persona tiene que creerse al agente |

**Y una corrección a la spec que el plan tiene que pedir.** R3.2 dice *«NO DEBE
persistir la salida en ningún sitio del que se pueda volver a leer»*. Leído
literal, prohíbe también la clave efímera. Lo que la constitución §III pide —y lo
que R3.3 y CE-005 miden— es que **no sea durable**: que la auditoría no la
contenga y que al reabrir un hilo antiguo ya no esté. La redacción tiene que
decir *«de forma durable»*, y el TTL tiene que ser un número declarado.
**`/speckit-tasks` no debe arrancar con R3.2 como está.**

**Dónde se pinta**: no en la tarjeta de aprobación. Su comentario dice *«nunca la
salida: la salida es del turno siguiente, no de la decisión»* y **sigue siendo
verdad** — esa tarjeta es para decidir. Lo que falta es un elemento de
**resultado**, hermano suyo, que aparece cuando la máquina contesta.

---

## 3 · ¿Varias conversaciones necesitan migración? *(Historia 4)*

**Decisión: no. Ni migración ni API nueva. Es la aplicación.**

`companion.threads` ya tiene `title`, `teammate_id`, `archived_at`, `updated_at`
y `last_run_at`, con RLS por `principal_id` (migración 0090). Y la API ya sirve:

- `GET /companion/threads?teammate_id=…` lista, con `include_archived` y `limit`;
- `POST /companion/threads` crea.

Lo que fuerza el hilo único es **una línea de la aplicación**:
`app:thread.open` (`app-surface.ts:139`) lista, coge `listed.data.find(t =>
!t.archived_at)` y, si no hay, crea. La base de datos lleva soportando varias
conversaciones desde la 003; nadie las pidió.

Queda un detalle que sí es trabajo: los hilos se crean con el título literal
`"Hilo"`, así que varias conversaciones serían varias «Hilo». R4.4 pide poder
distinguirlas sin abrirlas. El título se resuelve en la aplicación a partir de lo
primero que se escribió; **no se le pide al modelo que titule**, que sería un
turno de más y un gasto por una etiqueta.

---

## 4 · ¿Qué va en el paquete compartido y qué en la aplicación?

**Decisión: el timeline y el mensaje, compartidos. La navegación, de la aplicación.**

`packages/companion-ui` lo usan la aplicación **y la consola**, y la regla de la
003 es que hay una sola implementación de la pantalla.

| Requisito | Dónde | Por qué |
|---|---|---|
| R2 (Markdown) | `packages/companion-ui` | Es cómo se pinta un mensaje. La consola tiene el mismo hueco |
| R3 (salida visible) | `packages/companion-ui` + API | La tarjeta de resultado es del timeline; la ruta, de la API |
| R5 (copiar/editar/reintentar) | `packages/companion-ui` | Acciones sobre un mensaje |
| R1 (el hilo recuerda) | API + las dos pantallas | Un campo en el resumen de run |
| R4 (varias conversaciones) | `apps/desktop` | La consola no tiene pantalla de teammates (R14.3 de la 003) |
| R6 (al abrir se puede escribir) | `apps/desktop` | La consola no abre en un chat |
| R7 (buscar) | `apps/desktop` + API | ⌘K es de la aplicación |

**Consecuencia de verificación, y es la que este repo olvida**: tocar
`packages/companion-ui` obliga a `./scripts/verify.sh js` entero —consola,
panel, el paquete compartido y el `next build`—, no solo la suite de escritorio.

---

## 5 · El renderizador de Markdown

**Decisión: `react-markdown` + `remark-gfm` (MIT) + `remend` (Apache-2.0), y
explícitamente SIN `rehype-raw`.**

### El argumento que decide, y no es el peso

R2.3 dice que no se carga nada de fuera y no se ejecuta nada que venga dentro de
un mensaje. Ese mensaje puede ser **texto de un desconocido por WhatsApp**.

`marked` y `markdown-it` devuelven **una cadena de HTML**. Pintarla en React
obliga a `dangerouslySetInnerHTML`, y entonces R2.3 depende de acertar con un
sanitizador — una lista negra, y las listas negras se escapan.

`react-markdown` construye **elementos de React**. No hay HTML que inyectar, así
que el requisito se cumple **por construcción y no por vigilancia**. Sin
`rehype-raw`, el HTML que venga dentro del mensaje se descarta.

### Lo verificado, y por quién

| Paquete | Versión | Licencia | Comprobado |
|---|---|---|---|
| `react-markdown` | 10.1.0 | **MIT** | `registry.npmjs.org/react-markdown/latest` + el fichero `license` del repositorio, leídos en esta sesión |
| `remark-gfm` | 4.0.1 | **MIT** | `registry.npmjs.org/remark-gfm/latest` |
| `remend` | 1.3.1 | **Apache-2.0** | `registry.npmjs.org/remend/latest` + el `LICENSE` de `vercel/streamdown` |

Los párrafos, citados como pide §VIII:

> **The MIT License (MIT)** — Copyright (c) Espen Hovlandsdal. Permission is
> hereby granted, free of charge, to any person obtaining a copy of this
> software and associated documentation files (the "Software"), to deal in the
> Software without restriction, including without limitation the rights to use,
> copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
> the Software…

> Copyright 2023 Vercel, Inc. **Licensed under the Apache License, Version 2.0**
> (the "License"); you may not use this file except in compliance with the
> License. You may obtain a copy of the License at
> http://www.apache.org/licenses/LICENSE-2.0

Apache-2.0 es la de verdad, no una «Apache modificada»: el texto es el estándar
y §VIII lo admite sin lectura adicional.

### Por qué `remend` y no `streamdown`, del mismo autor

`streamdown` resuelve el streaming mejor que nadie, pero **sus valores por
defecto son más permisivos que nuestra superficie de amenaza**: trae `rehypeRaw`,
`allowedImagePrefixes: ["*"]` y `allowDataImages: true`. Habría que desactivar
tres cosas para volver al punto de partida, y son 144 kB con 15 dependencias
frente a 4,3 kB y ninguna.

`remend` es el mismo motor de autocierre que `streamdown` lleva dentro,
publicado aparte. Se lleva la parte que resuelve R2.4 —cierra énfasis y código
inline a medias mientras el texto llega— sin traerse la parte que hay que apagar.

### Lo que no arregla, y hay que decirlo

- **Un bloque de código abierto no se cierra**, y está bien: CommonMark dice que
  un cercado sin cerrar llega al final del documento. No rompe nada.
- **Las tablas a medias sí parpadean**: GFM exige la fila delimitadora, así que
  una cabecera se ve como párrafo y salta a tabla al completarse. Se mitiga
  pintando por bloques y no repintando los ya cerrados. **Es trabajo de la
  implementación, no de la librería**, y la tarea tiene que existir.
- **Sin resaltado de sintaxis en la v1.** Monoespaciado y copiar. Añadirlo son
  63 kB (`shiki`, MIT) y un problema de CSP —emite `style=` en línea— que no se
  ha probado contra la política de esta aplicación. R2.2 pide copiar el código,
  no colorearlo.

### Lo que se descartó

| Alternativa | Por qué no |
|---|---|
| `marked`, `markdown-it` | Devuelven cadena de HTML → `dangerouslySetInnerHTML` |
| `streaming-markdown` | Excelente y MIT, pero escribe en el DOM: no es React |
| **Escribir un subconjunto propio** | El énfasis de CommonMark y las tablas GFM son el 80 % del coste y el 100 % de los fallos; la suite del estándar tiene ~650 casos. Y seguiría habiendo que filtrar `javascript:` a mano. 37 kB no justifican mantener un parser |

### No verificado

Peso exacto en gzip de `remark-gfm` (el servicio que lo mide falló); su licencia
sí. Y el comportamiento de un resaltador bajo la CSP concreta de esta
aplicación, que es de la v2.
