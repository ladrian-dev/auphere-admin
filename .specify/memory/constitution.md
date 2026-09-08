# Auphere Nexus — Constitución

Los principios que gobiernan cómo una especificación se convierte en código en
este repositorio. **Toda spec, todo plan y toda tarea se comprueban contra este
documento antes de pasar a la siguiente fase.** Un artefacto que viole un
principio no avanza: o se corrige, o se enmienda la constitución por el
procedimiento de §Gobernanza.

Ámbito: el repositorio `nexus` completo — plataforma, consola, companion y
**teammates**. No es un documento del producto teammates: es del repo.

---

## Principios

### I. El aislamiento entre tenants es la base, no una feature

Ningún cambio puede debilitar las 7 garantías de aislamiento de
`architecture/agent-isolation.md`. El `tenant_id` **nunca** llega del llamante:
se toma del contexto de petición (`SET LOCAL app.tenant_id`) y la RLS decide.
La lista blanca de herramientas es exhaustiva y por tenant: **no hay globales**.

Consecuencia obligatoria para toda spec: si abre, toca o roza una frontera de
tenant, la spec **declara** qué garantía toca y el plan **incluye** el test de
aislamiento correspondiente. Un test de aislamiento en rojo bloquea el merge.
Sin excepciones y sin "lo añadimos después".

### II. El corte es por superficie de confianza, no por feature

El coste de una pieza no lo fija la pieza: lo fija **qué frontera de confianza
abre**. Abrir una superficie nueva cuesta siempre lo mismo — un ADR, un test de
aislamiento, un medidor, un estado nuevo en la UI y una lectura de RGPD — aunque
la pieza sea pequeña.

Regla: **agotar todo el valor que quepa dentro de la superficie ya abierta antes
de abrir la siguiente, y abrir cada una por su mitad barata primero.**

Toda spec declara en su encabezado la superficie sobre la que trabaja:
`0` API de la consola · `1` navegador · `2` VM · `3a` ejecutar en la máquina del
partner · `3b` controlar el escritorio del partner.

### III. Lo que se lee es dato; nunca es instrucción

Contenido de una web, de un fichero, de un mensaje de cliente final o de la
salida de una herramienta **no puede** cambiar lo que el agente hace. Las
instrucciones de operador viajan como mensaje `{"role": "system"}` dentro de
`messages`, nunca mezcladas con el contenido leído.

**Restricción de orden, dura:** navegador y `shell_local` no se encienden a la
vez sin la contención de escrituras y sin esta regla probada. La fase que
encienda la segunda de las dos **paga las guardas de las dos**.

### IV. Una acción consecuente pasa por un humano, y queda dicho quién

Toda acción `mutates` pasa por confirmación. La aprobación es un **objeto de
dominio durable**, no un prompt: caduca (15 min, perezosa, con `state_hash`), es
idempotente (uuid5 determinista + UPSERT), y la auditoría nombra a la **persona**
que decidió (`decided_by`), no al agente que ejecutó.

Nunca son automáticas, y la lista es cerrada: borrar un cliente, rotar claves,
desactivar la revelación de IA. **Borrar no existe: se archiva.**

Avisar sin bloquear cuando no se pudo probar algo, y dejar rastro.

### V. La pantalla no miente

Estados honestos como requisito del runtime, no como copy:
`normal · cargando · vacío · error · reconectando · parcial · bloqueado`.

- `parcial` significa que el agente **acota el alcance de su propia respuesta**:
  *"leí 2 de los 3 canales; lo de arriba es cierto para los dos que contestaron"*.
- `bloqueado` es esperar a otro teammate, y no se pinta como ocioso.
- Si algo no está en el catálogo leído en este turno, **no existe**.
- Cuando una capacidad no está disponible, no hay botón apagado ni pantalla que
  explique lo que no tienes: **la ausencia se diseña**.

### VI. Por API, nunca por navegador, y nunca contra nosotros mismos

Un agente opera la plataforma llamando a las herramientas `console.*`. El
navegador de un agente es para lo que **no tiene API** — el portal de un
proveedor, una web pública. **Nunca para la consola de Auphere**: multiplica el
coste, se rompe con cualquier cambio de UI, y mete una sesión autenticada de la
consola dentro del ambiente del agente, que es justo lo que el aislamiento
prohíbe.

### VII. Test primero, y el test es el criterio de aceptación

Cada criterio de aceptación de una spec nace como test. El ciclo es
rojo → verde → refactor, y el rojo se ve antes de escribir la implementación.
Las suites que bloquean merge son las de `tests/isolation/`. La cobertura de un
camino de seguridad no se declara: se ejecuta — un test que hace `skip` puntúa
como aprobado y por tanto **no cubre nada**.

### VIII. Las licencias se leen enteras antes de instalar

Esto es software propietario ofrecido como servicio. **AGPL es un no** (alcanza
el uso en red). MIT y Apache-2.0 son un sí. Cualquier "Apache modificada",
Elastic License, BSL o Sustainable Use se lee **completa** antes de instalar:
varias prohíben exactamente el uso multi-tenant o el alojamiento como servicio.

Toda dependencia nueva que entre por una spec declara su licencia en el plan,
con la cita del párrafo que la permite.

### IX. La KB es dueña del porqué; el repo, del cómo

`/Users/lmatos/Work/Auphere/` es la fuente única de verdad de la investigación,
las decisiones, los ADRs y el roadmap. El repo guarda lo que el código lee o
contra lo que se compila: contratos congelados, `capabilities.yaml`, y los
artefactos de spec (`specs/NNN-*/`).

**El puente es obligatorio en las dos direcciones:** toda spec cita en su
frontmatter la nota de KB que la justifica; toda decisión de KB que se
implemente enlaza a su carpeta de spec.

---

## Restricciones adicionales

- **Español para documentación, inglés para código.** Commits en inglés,
  Conventional Commits, sin firma ni atribución de herramientas.
- **La consola de partner nunca guarda una credencial de backend.** Acuña tokens
  EdDSA de 60 segundos por llamada; la API revalida la pertenencia en
  `partner_memberships`. CI hace grep de `NEXUS_ADMIN_TOKEN` en esa app y falla
  si aparece.
- **Bespoke por cliente.** Los verticales son plantillas semilla, no runtime. La
  verdad en runtime es `agent_configs.system_prompt_rendered` por tenant.
- **Ninguna credencial de cliente final entra nunca en el ambiente de un agente.**
- **El hilo de un teammate no transcribe texto de cliente final**: referencia y
  cita. Es la condición que legitima persistirlo (migración 0090). Si algún día
  se permite lo contrario, ese hilo pasa a necesitar retención, borrado por
  cliente y el tratamiento completo de una conversación.
- **Todo lo que gasta, se mide.** Toda spec que consuma modelo, reloj de máquina
  o herramienta de pago declara dónde entra en el medidor que ve el partner.

---

## Flujo de trabajo

El método es **Spec-Driven Development** y está descrito en
[`docs/spec-driven-development.md`](../../docs/spec-driven-development.md). En
corto, y por orden:

1. `/speckit-constitution` — este documento. Se toca poco y por enmienda.
2. `/speckit-specify` — el **qué** y el **porqué**. Sin stack, sin API, sin código.
   Ambigüedad marcada como `[NEEDS CLARIFICATION: pregunta concreta]`.
3. `/speckit-clarify` — cerrar las marcas. **Ninguna spec pasa a plan con marcas
   abiertas.**
4. `/speckit-plan` — el **cómo**: arquitectura, contratos, modelo de datos,
   licencias de lo que se instale, y la comprobación contra cada principio.
5. `/speckit-tasks` — tareas ejecutables, cada una con su `_Requisitos: n.m_`.
6. `/speckit-analyze` — consistencia entre spec, plan y tareas antes de tocar código.
7. `/speckit-implement` — ejecutar.

Para una idea que todavía no se sabe si se construye, se usa antes el flujo de
evaluación (`intake → research → define → shape → decide`) de la extensión
`assess`. Un veredicto *go* entrega a `/speckit-specify`; un *kill* cierra el
asunto con su razón escrita.

**Puertas que no se saltan:**

| Puerta | Antes de | Qué comprueba |
|---|---|---|
| Cero `[NEEDS CLARIFICATION]` | `/speckit-plan` | No queda ninguna suposición sin decidir |
| Superficie declarada | `/speckit-plan` | La spec dice qué frontera de confianza toca (§II) |
| Aislamiento | `/speckit-tasks` | Hay test de aislamiento para cada garantía tocada (§I) |
| Licencias | `/speckit-tasks` | Toda dependencia nueva trae su licencia leída y citada (§VIII) |
| Medidor | `/speckit-tasks` | Todo lo que gasta declara dónde se mide |
| `/speckit-analyze` en verde | `/speckit-implement` | Spec, plan y tareas dicen lo mismo |

---

## Gobernanza

Esta constitución **prevalece** sobre cualquier otra práctica del repo. Cuando
un principio choca con la comodidad de una tarea, gana el principio y el
conflicto se escribe.

Se enmienda por pull request, con: el texto nuevo, la razón, qué specs vivas
quedan afectadas y qué hay que migrar. Una enmienda que debilite §I, §III o §IV
exige además el test que demuestre que la garantía sigue en pie con la redacción
nueva.

La versión sigue `MAYOR.MENOR.PARCHE`: mayor si se retira o se redefine un
principio, menor si se añade uno o se amplía materialmente, parche para
redacción.

**Version**: 1.0.0 | **Ratified**: 2026-09-08 | **Last Amended**: 2026-09-08
