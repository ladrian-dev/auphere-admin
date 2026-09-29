# Implementation Plan: el alta deja de pesar

**Spec**: [spec.md](./spec.md) · **Rama**: `019-alta-deja-pesar` · **Creado**: 2026-09-28

## Resumen

El alta no necesita datos nuevos ni endpoints nuevos: necesita **preguntar
menos y en otro orden**. Todo lo que pide esta spec se resuelve con las
lecturas y escrituras que la consola ya hace.

La medición de la Fase 0 es la que da forma al trabajo: **diez de las trece
plantillas exigen exactamente dos campos** y tres no exigen ninguno, así que el
alta puede pasar de veintitrés campos a cuatro sin tocar una sola semilla.

## Contexto técnico

| | |
|---|---|
| Lenguaje · marco | TypeScript · Next.js 16 (App Router), React 19 |
| Sistema de diseño | `@nexus/ui` sobre Base UI + Tailwind v4, tokens OKLCH |
| Dónde vive | `apps/console/src/app/(console)/clients/new/` |
| Pruebas | vitest (unidad y componente), Playwright (a11y y recorrido) |
| Dependencias nuevas | **ninguna** |
| Endpoints nuevos | **ninguno** |
| Migraciones | **ninguna** |

## Puertas de la constitución

| § | Principio | ¿Pasa? | Cómo |
|---|---|---|---|
| I | El aislamiento es la base | ✅ | No se toca la ruta de creación: el `tenant_id` sigue saliendo del contexto. **La capa 2 del Companion se declara intacta** y T-ISO añade el test que lo prueba desde esta spec (R5.4). |
| II | Corte por superficie de confianza | ✅ | Superficie 0, la ya abierta. Cero endpoints nuevos. |
| III | Lo que se lee es dato, nunca instrucción | ✅ | La frase que el partner escribe para el Companion es **contenido**: viaja como dato del usuario, y lo que el Companion devuelve son **valores propuestos para campos**, nunca instrucciones que cambien lo que la consola hace. R5.6 acota qué se envía. |
| V | Estados honestos; la ausencia se diseña | ✅ | R5.5: sin Companion, la ayuda **no aparece** — ni apagada ni explicada. R6.2: una etapa fallida dice cuál y conserva lo hecho. |
| VII | Test primero | ✅ | Cada bloque de tareas empieza en rojo. |
| VIII | Licencias | ✅ | T-LIC: `pnpm-lock.yaml` y `uv.lock` no cambian en toda la spec. |
| IX | La KB se mantiene | ✅ | T-KB al cerrar: el mapa de la consola y el log de sesión. |

## Fase 0 · Investigación *(hecha)*

Tres cosas se comprobaron **ejecutando**, no leyendo, y las tres cambiaron el
plan.

### 1 · Qué exige de verdad cada plantilla

Se ejecutó `render_seed_template` contra las trece semillas con los campos
vacíos, añadiendo uno a uno los que iba exigiendo:

| Plantillas | Campos imprescindibles | Cuáles |
|---|---|---|
| 10 | **2** | `tenant.address`, `tenant.business_hours_label` |
| 3 (`cobranza_v1`, `inventario_v1`, `woocommerce_sales_v1`) | **0** | — |
| 1 (`aesthetic_clinic_v1`) | **12** | dirección, horario, sábados, titular y su credencial, hospital y teléfono de referencia, Instagram, recepción, precio de consulta, tabla de precios, formas de pago |

**Decisión**: el alta pide *exactamente* los imprescindibles de la plantilla
elegida, calculados de la plantilla y no de una lista escrita a mano. Diez
plantillas → 2 campos. `aesthetic_clinic_v1` conserva doce, anotado en paridad.

**Alternativa descartada**: dar valores por defecto a los doce de
`aesthetic_clinic_v1`. Es lo correcto a largo plazo y arreglaría el caso peor,
pero se hace en la semilla de la API y en la KB, no en la consola: entra en su
propia tarea, fuera de esta spec.

### 2 · Un campo sin valor no degrada: rompe

`render_seed_template` levanta `SeedTemplatePlaceholderMissing` cuando un
`{a.b.c}` no tiene valor ni defecto. Eso convierte «¿el agente sale coherente?»
—un juicio— en «¿renderiza?» —una comprobación—. **La frontera es dura y
automática**, y por eso el número de arriba es fiable.

### 3 · El Companion no puede escribir, y eso no se negocia

Las 41 herramientas del catálogo son de lectura, con un test que lo recorre y
lo exige (capa 2 del aislamiento). El papel del Companion en el alta es
**redactar**: leer `console.list_templates`, proponer plantilla y valores. La
escritura la hace el partner.

**Consecuencia de diseño**: la propuesta llega al formulario como **valores
sugeridos y marcados como tales**, no como un alta hecha. El partner ve qué
propuso la máquina, lo cambia o lo tira, y el clic que crea sigue siendo suyo.

## Fase 1 · Diseño

### Estructura

```
apps/console/src/app/(console)/clients/new/
├── page.tsx                  # sin cambios de contrato: sigue trayendo cupo y plantillas
├── wizard.tsx                # 4 pasos → 3; el paso «canal» desaparece
├── wizard-state.ts           # + requiredPlaceholders(); − ChannelChoice
└── __tests__/
apps/console/src/components/clients/
├── new/template-picker.tsx   # catálogo buscable, nada preseleccionado
├── new/business-brief.tsx    # la caja del Companion: una frase → propuesta
└── client-setup.tsx          # + un paso: «Datos del negocio»
```

### Los tres pasos

| # | Paso | Qué pide | Por qué aquí |
|---|---|---|---|
| 1 | **A qué se dedica** | La plantilla, sin nada marcado. Arriba, la caja del Companion. | Decide el prompt, las herramientas y qué campos existen: decidirla primero estrecha todo lo demás |
| 2 | **El negocio** | Nombre, zona horaria y **solo los imprescindibles** de esa plantilla. La referencia, plegada. | Lo mínimo para que exista y renderice |
| 3 | **Confirmar** | Resumen, publicar o no, y la ejecución por etapas | Publicar se elige aquí **junto a lo que lo hace entendible**, no perdido tras un resumen |

### Lo que se retira, y a dónde va

| Hoy | Después | Dónde queda |
|---|---|---|
| Paso «Canal» | — | Se borra: su respuesta no viajaba a ningún sitio |
| 11 campos opcionales de la plantilla marcada | — | Tarjeta «Pasos para activar tu agente», paso nuevo |
| «Referencia» como segundo campo | Plegada | Bajo «opciones avanzadas», derivada del nombre |
| «Publicar ahora» en el paso 4 | Paso 3, junto al resumen | — |

### La caja del Companion

Una sola entrada de texto arriba del paso 1: «Cuéntame del negocio». Al
enviarla, la consola pide al Companion una propuesta y la aplica al formulario
**marcando cada valor como propuesto**. El partner acepta, cambia o descarta,
uno a uno o todos.

Sin Companion disponible, **la caja no se pinta** (§V). El alta se recorre
entera sin ella.

## Fase 2 · Iteraciones

| # | Historias | Qué entrega |
|---|---|---|
| **1** | H1 + H2 + H4 | El alta de tres pasos: plantilla primero y sin preseleccionar, solo los campos imprescindibles, publicar junto al resumen. **Es el MVP y se puede parar aquí.** |
| **2** | H1 (cola) | El paso «Datos del negocio» en la tarjeta de la ficha, que recoge lo que el alta dejó de pedir |
| **3** | H3 | La caja del Companion |

La iteración 1 ya lleva el alta de 23 campos a 4. La 2 cierra el círculo —lo
que se dejó de pedir se pide en su sitio— y la 3 lo hace cómodo.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| **El paso nuevo de la tarjeta la vuelve a engordar** — es justo lo que la spec 018 adelgazó | El paso solo aparece **mientras falte algo**, como los otros tres, y desaparece entero al completarse. La tarjeta no crece para siempre |
| **`aesthetic_clinic_v1` sigue pidiendo doce** y alguien lee la spec como «ya no se piden campos» | El número está en CE-001 y en paridad. La tarea de darle defectos queda abierta y nombrada, fuera de alcance |
| **La propuesta del Companion se confunde con lo escrito por el partner** | R5.2 lo exige en pantalla y tiene test propio: si no se distingue, está roto |
| **Quitar el paso «Canal» deja al partner sin saber que hay que conectarlo** | R3.2: al terminar se le lleva a donde se conecta. La tarjeta de pasos ya lo pide |

## Fuera de alcance del plan

- Dar valores por defecto a los doce campos de `aesthetic_clinic_v1` — es la
  semilla, no la consola.
- Escritura para el Companion — ADR propio.
- Importación en lote.
