# PLAN-CO-UI-OLA2 · La interfaz de la Ola 2 del Companion

> Agente F. Extiende CO-03 (`32a9f0d`) contra
> [`CONTRACT-V2.md`](CONTRACT-V2.md), que manda sobre
> [`CONTRACT-V1.md`](CONTRACT-V1.md) v1.1 en lo que toca.
>
> **Nada de esto tiene backend todavía.** Los agentes D y E lo construyen en
> paralelo y no puedo verlos. Todo se escribe contra el contrato y se prueba
> con dobles; la integración real la valida la Fase 2, como en la Ola 1.

---

## 0. Aviso de arranque — el worktree venía de la rama equivocada

El worktree se creó desde `main` (`402ad75`), no desde `develop` (`32a9f0d`)
como decía el encargo. Consecuencia: **no tenía nada de la Ola 1** — ni CO-03,
ni CO-04, ni CO-07. Comprobado con `git merge-base --is-ancestor 32a9f0d HEAD`
(falso) y con `git branch --contains 32a9f0d`, que sí lista `develop` y los
worktrees de otros dos agentes.

Corregido con `git reset --hard 32a9f0d` sobre mi propia rama desechable. No
toca nada compartido y `main` sigue en su sitio. Es un arreglo operativo, no un
cambio de alcance: el encargo fija esa base explícitamente.

---

## 1. Qué construyo, y la regla que gobierna cada pieza

Seis piezas del §14 de la investigación y de los §2–§10 de la v2. La regla que
las atraviesa todas es la del §1.4 de la v1.1: **el backend emite
identificadores estables, esta app emite texto para humanos.** Cada
identificador nuevo de la v2 (`work_kind`, `sla`, `topic`, `warning_key`,
`checks[].name` de la prueba, `scope`) se traduce aquí y **nunca** se pinta
crudo como si fuera prosa.

| # | Pieza | Evento / dato de origen |
|---|---|---|
| 1 | Chips del expediente con `work_kind` | `intake.missing` (v2 §3) |
| 2 | Píldora de fase con `publish` | `phase.changed` (v2 §2) |
| 3 | Tarjeta del ticket de soporte | `support.ticket` + `hitl.requested.preview` (v2 §4) |
| 4 | Panel de la prueba en playground | `verify.result.trial` (v2 §7) |
| 5 | Pausa por presupuesto | `budget.paused` + 409 `budget_paused` (v2 §6) |
| 6 | Bandera por partner | `GET /console/me.companion_enabled` (v2 §10) |

---

## 2. Decisiones

### D1 · `publish` entra en el enum en su sitio, no al final

`PHASES` es un array ordenado y el orden **es** el del §7 de la investigación.
`publish` va entre `verify` y `respond`, que es donde el proceso lo pone. Un
enum desordenado invita a que alguien más adelante ordene la píldora por índice
y pinte "Publicando" antes de "Verificando".

i18n: `publish` → *Publicando* / *Publishing*. Sigo sin pintar
`phase.changed.label` — el fixture de CO-03 ya manda `"ETIQUETA DEL BACKEND"` a
propósito para que un test lo demuestre, y añado la fase nueva a ese test.

### D2 · `work_kind` titula el grupo; la clave cruda nunca se pinta

`intake.missing` pasa a `{slots, work_kind}`. El título del grupo sale de
`companion.intake.title.<work_kind>` — cinco valores cerrados (§3.2). Si llega
uno fuera del enum, cae al título genérico de CO-03 (*Me falta saber*), **no** al
identificador.

`work_kind` es lo que hace que el título sea una frase y no un encabezado
genérico: *"Para crear el cliente me faltan…"* frente a *"Me falta saber"*. Sin
él habría que deducirlo de prefijos de `key`, que es adivinar.

### D3 · El catálogo de 12 `key` tiene copy propio; el resto cae a `label`/`why`

§3.3 cierra el catálogo por tipo de trabajo. Escribo copy ES/EN para los doce:
`name`, `vertical`, `timezone`, `language`, `forbidden_behaviour`,
`phone_number`, `number_owner`, `channel_role`, `failing_behaviour`,
`real_example`, `connector_consent`, `ai_disclosure_decision`.

CO-03 ya trae cinco `companion.intake.slot.*`, de los cuales tres
(`business_hours`, `legal_name`, `escalation`) **no** están en el catálogo
cerrado de la v2. Los dejo: son copy de reserva sin coste, y un `key` que el
motor emita fuera del catálogo seguirá teniendo nombre humano en vez de caer.

La caída sigue siendo `label` → `why` del backend, y jamás la clave cruda. Eso
ya lo hacía CO-03 (`optionalKey`); solo crece el catálogo.

### D4 · `forbidden_behaviour` se pinta distinto — advertencia, no error

Es el campo que nadie escribe y el que causa los incidentes (§7.1), y es
obligatorio a propósito. Tres diferencias, todas justificadas:

1. **Va primero**, sea cual sea el orden que mande el backend. El orden de una
   lista es un argumento; enterrarlo detrás de "zona horaria" lo convierte en
   trámite.
2. **Borde y acento en `status-warning`**, no en `status-danger`. No es un
   error: es lo que más se te va a olvidar. Rojo aquí enseñaría a temer un
   campo que queremos que la gente rellene.
3. **`why` y `examples` siempre visibles**, no como texto secundario. Es la
   única fila donde el "por qué" es el argumento y no una nota al pie.

El tono **no es el único portador del mensaje** (WCAG 1.4.1): lleva icono y una
etiqueta textual propia.

### D5 · Responder un chip escribe en la caja. Sigue sin ser un formulario

CO-03 ya lo resolvió: el chip mete `«{label}: »` en el compositor y enfoca. No
lo toco. Añadir un `<form>` con Enviar habría sido el error obvio y la v2 lo
prohíbe explícitamente. Lo único que cambia es que el chip de
`forbidden_behaviour` prerrellena con su etiqueta larga, que es la pregunta
completa y no una palabra.

### D6 · El ticket sella la tarjeta existente; no añade una suelta

`support.ticket` se ata por `action_id`, **igual que `hitl.resolved`**. En el
reductor busca el `ActionItem` y le cuelga `ticket`; si no lo encuentra, **se
descarta en silencio**. Un ticket huérfano en el timeline sería una tarjeta sin
la propuesta que lo originó — exactamente lo que la regla 2 de CO-03 evita.

Llega en `execute`, después del 2xx de `console.apply` y antes de
`verify.result`, así que la tarjeta ya está en el timeline cuando llega.

### D7 · `ticket_ref` es lo más visible y lo más copiable de la tarjeta

`AU-142` es lo que la persona repetirá por teléfono. Va en tipografía mono,
tamaño mayor que el resto de la tarjeta, con un botón de copiar al lado
(`navigator.clipboard`, con el mismo patrón que `keys-list.tsx` ya usa) y
confirmación por región viva. Un identificador que hay que seleccionar a mano
con el ratón no es un identificador utilizable.

### D8 · `sla` y `category` los traduzco yo; `topic` se pinta como lo que es

- `sla ∈ business_hours | next_business_day | best_effort` → frase completa
  ES/EN. El backend **no** manda la frase (§4.4) y no la invento a partir del
  identificador: es una tabla.
- `category ∈ help | capability` → *Incidencia* / *Petición de funcionalidad*.
- `topic` es un **slug de agregación**, no prosa. Lo pinto en mono dentro de un
  chip etiquetado *Tema*, que es honesto sobre lo que es. Admite override por
  `companion.support.topic.<slug>` si algún día conocemos uno; sin override, el
  slug. **Nunca** intento convertir `connector.shopify` en una frase.

### D9 · La propuesta del ticket tiene componente propio, no la vista genérica

`hitl.requested.preview` de `support_help` / `support_capability` trae
`{category, topic, client_ref, need, checked[], alternative, bridge}`. La vista
genérica clave/valor de CO-03 pintaría `checked` con `JSON.stringify` — legible
para un programador y basura para todos los demás.

`checked` es lo que hace que el ticket no parezca una queja vaga: es la lista de
lo que el Companion ya leyó, y sale de las etiquetas del catálogo de
herramientas (misma procedencia que sostiene R1). Se pinta como lista con
palomita, con encabezado propio.

`bridge: true` es una etiqueta visible (*Solución puente*) con su explicación:
el puente no sustituye al ticket. Un puente que nadie registra es deuda
invisible (§25.4).

`client_ref` sigue siendo `client_ref`. Ningún enrutador BFF acepta ni reenvía
`tenant_id` ni `partner_id`.

### D10 · `trial: null` y `trial: {ran:false}` se pintan distinto, porque son distinto

La regla dura del §7 y la más fácil de romper:

| Valor | Significa | Qué pinto |
|---|---|---|
| `null` / ausente | la acción **no admite** prueba (`invite`, `usage_alerts`) | **nada** |
| `{"ran": false}` | admite prueba y **no se hizo** | el aviso |
| `{"ran": true, …}` | se probó | el panel de turnos |

El lector devuelve `null` para el primer caso y un objeto para los otros dos.
Un lector que colapsara ambos a "no hay panel" borraría el aviso, que es
precisamente la señal que la publicación necesita.

### D11 · El panel de la prueba no finge tener la conversación

`trial` **nunca** lleva la respuesta del agente borrador. Lleva `probe` (que
redacta el Companion, seguro de pintar), aserciones con nombre estable, latencia
y tokens. El panel dice explícitamente que la conversación está en el hilo de
playground y **pone el enlace**.

`checks[].name` se traduce (`companion.trial.check.<name>`), con caída al
identificador. `expected` y `actual` son cadenas siempre; coacciono un número
por si el backend regresa, igual que hace `readChecks`.

### D12 · El enlace al hilo de playground se construye si se puede, y si no se degrada a copiar

**Hueco del contrato, y es el más importante que encontré.** `verify.result`
lleva `trial.thread_id` pero **no** lleva `client_ref`, y la ruta del playground
es `/clients/{ref}/playground`. Sin `ref` no hay URL.

Lo que hago: correlaciono por `action_id` con la tarjeta de `hitl.requested` y
saco `preview.client_ref` — que el §3.4 garantiza para siete de los nueve
`kind`, pero es un objeto libre y no una garantía dura. Con `ref`, enlace; sin
`ref`, **el `thread_id` copiable en mono y ni un enlace**. Un enlace muerto es
peor que ningún enlace.

Segundo hueco, apilado sobre el anterior: la página del playground **no lee hoy
ningún parámetro de hilo de la URL** (`src/components/playground/playground.tsx`
guarda el hilo elegido en estado local). El `?thread=<id>` que emito queda
**inerte** hasta que alguien lo honre, y esa página está fuera de mi zona. Va al
informe.

### D13 · El aviso de publicar sin probar es un aviso, y los botones siguen activos

`preview` de `kind: publish` gana `{trial_ran, trial_ok, warning_key}` con
`warning_key ∈ not_tried | trial_failed | null`.

Se pinta como `Alert` en tono **advertencia**, encima de los botones, con la
frase que corresponde a cada `warning_key`. **Confirmar sigue habilitado.**
Prohibirlo convertiría la prueba en un peaje que la gente aprende a rodear, y
el §7.1 lo dice con esas palabras.

`evals_warning` sobrevive como cae hoy por la vista genérica de `preview`
(`companion.preview.evals_warning`), por compatibilidad con lo que CO-04 ya
emite.

### D14 · La pausa es una pausa. Nada de rojo

Estado nuevo, no error. Cinco consecuencias concretas:

1. **`RunStatus` gana `paused`**, terminal. `run.completed{status:"paused"}`
   **no** genera el aviso de error que genera `cancelled`/`error`: genera el de
   pausa. Sin este cambio, `terminal()` mapearía `paused` a `completed` por su
   caída por defecto y el corte sería invisible.
2. **`budget.paused` deja una marca en el timeline** — es dónde se paró el
   trabajo, y borrarlo dejaría un hilo que termina a media frase sin explicar
   por qué. Código de aviso `paused`, tono neutro.
3. **La caja de escribir se deshabilita con la explicación**: cuánto se usó de
   cuánto, cuándo se reinicia, y **qué lo desbloquea** (subir el tope). Sin la
   salida, un estado deshabilitado es un muro.
4. **La tarjeta pendiente sigue siendo respondible.** `resume` da 202 y no
   arranca trabajo nuevo (§6.2). El bloqueo del compositor **no** toca los
   botones de la confirmación. Tiene test.
5. **El hilo y la historia siguen enteros.** No se limpia el timeline, no se
   cierra el cajón, no se pierde nada.

`budget.updated.exhausted` sigue existiendo y sigue significando *vas por el
98 %*. `paused` significa *aquí se paró el trabajo*. Se pintan distinto porque
son distinto — es la razón por la que la v2 los separó.

### D15 · El 409 trae la instantánea; no hago una segunda petición

`POST …/threads/{id}/runs` da **409 `budget_paused`** y el cuerpo lleva
`{code, used, cap, period, resets_at}`. Para leerlo, el resultado de error del
cliente (`Err`) gana el cuerpo ya parseado. Hoy `call()` lo parsea, saca
`detail` y `code`, y **tira el resto** — así que la instantánea se perdería y
haría falta un `GET /budget` extra que el contrato dice explícitamente que
no hace falta.

`scope` viene con un solo valor hoy (`partner`) y el enum queda abierto: lo leo
y no lo pinto todavía. Cuando haya un segundo valor, la frase tendrá que
distinguirlos; con uno solo, decirlo es ruido.

### D16 · La burbuja apagada es ausencia

`companion_enabled === false` ⟹ **la burbuja no se monta**. No es un botón
deshabilitado con un tooltip: eso es publicidad de algo que no puedes tener.

Mientras la bandera es desconocida (`null`), tampoco se monta — así no hay un
parpadeo de burbuja que desaparece, que es peor que la espera.

Se lee por un enrutador BFF propio (`GET /api/companion/enabled`) que consulta
`GET /console/me`. Dos motivos para no tocar el tipo `Me` de `lib/backend.ts`:
está fuera de mi zona, y el estrechamiento defensivo (`companion_enabled !==
true` ⟹ apagado) es exactamente lo que quiero mientras E no haya desplegado el
campo — sin campo, apagado, que es el valor por defecto del contrato.

Ese enrutador **no** exige `companion:use`: un rol sin el permiso sigue viendo
la burbuja deshabilitada con su explicación (decisión de CO-03, intacta), y eso
es distinto de que el partner no tenga la función.

---

## 3. Los 5 estados de Hurff, pieza por pieza

El defecto real de la Ola 1 fue un `status` que arrancaba en `"loading"` y solo
pasaba a `"ready"` dentro de `openThread` — así que **el estado vacío no podía
renderizarse jamás**. La lección no es "escribe los cinco": es **comprobar que
cada uno es alcanzable**. Cada fila de abajo tiene un test que lo alcanza.

| Pieza | Cargando | Vacío | Error | Parcial | Ideal |
|---|---|---|---|---|---|
| Chips del expediente | el esqueleto del timeline | `slots` vacío ⟹ **no se pinta la tarjeta** | `work_kind` fuera del enum ⟹ título genérico | slot sin `why`/`examples` ⟹ solo el chip | grupo titulado con sus chips |
| Píldora de fase | sin píldora hasta el primer `phase.changed` | fase nula ⟹ sin píldora | fase fuera del enum ⟹ se ignora, la anterior aguanta | — | píldora traducida |
| Ticket | la tarjeta pendiente sin ticket todavía | `ticket_ref` vacío ⟹ no se pinta el bloque | `action_id` sin tarjeta ⟹ se descarta | `preview` sin `checked` ⟹ resto del ticket igual | ref + copiar + sla + tema |
| Panel de la prueba | — | `trial: null` ⟹ **nada** | `trial.ok === false` ⟹ turnos en rojo, sin culpar al usuario | `{ran:false}` ⟹ el aviso | tabla de turnos + enlace |
| Pausa | — | sin pausa ⟹ compositor normal | *(no hay estado de error: la pausa **es** el estado)* | pausa **con** confirmación pendiente ⟹ caja bloqueada, botones vivos | caja bloqueada con la salida |
| Burbuja | bandera desconocida ⟹ **nada** | bandera `false` ⟹ **nada** | la petición falla ⟹ **nada** (cerrado por omisión) | rol sin permiso ⟹ burbuja deshabilitada | burbuja |

La burbuja cierra por omisión a propósito: si no puedo demostrar que el partner
tiene la función, no la anuncio.

---

## 4. Accesibilidad

- **`aria-live="assertive"` sigue siendo exclusivo de `hitl.requested`.** Nada
  de lo que añado lo usa. El ticket, la prueba y la pausa son `polite` o van
  dentro del log, que ya lo es.
- La pausa **sí** se anuncia: es un cambio de lo que puedes hacer, no solo de
  lo que ves. `role="status"` (polite) en el bloque del compositor.
- `ticket_ref` copiado ⟹ confirmación por región viva, porque el `Toaster` vive
  fuera del diálogo modal y un lector de pantalla no lo oiría (mismo
  razonamiento que `companion.closeBlocked` en CO-03).
- La tabla de turnos de la prueba es una `<table>` de verdad con `<th scope>`,
  como la de verificación. `ok` no se codifica solo en color: lleva icono y
  texto para lector.
- Objetivos táctiles ≥ 24 px: el botón de copiar el ref usa `size="icon-sm"`,
  que ya cumple en el resto de la consola.
- Todo el texto nuevo pasa por i18n ES/EN.

**Antes de medir, dejo asentar.** El fundido de 200 ms del `Sheet` fue el que
hizo que axe leyera 1,97:1 donde hay ~19:1. El helper `settled()` del spec de
CO-03 ya lo resuelve y lo reutilizo tal cual; `waitFor` sobre el estado final,
nunca una captura a los 100 ms.

---

## 5. Tokens

Ningún hex suelto. Los mapeos nuevos, todos a token semántico:

| Dato | Token |
|---|---|
| `risk` `low\|medium\|high` | `status-positive` · `status-warning` · `status-danger` (ya existía) |
| `impact[].severity` `info\|warn\|danger` | `muted-foreground` · `status-warning` · `status-danger` (ya existía) |
| `forbidden_behaviour` | `status-warning` |
| `trial.turns[].ok` | `status-positive` / `status-danger` |
| `warning_key` (publicar sin probar) | `status-warning` — **nunca** `danger` |
| pausa por presupuesto | `muted` / `border` — **ningún** token de peligro |
| `bridge: true` | `status-info` |

---

## 6. Zona y límites

Toco **solo**: `src/components/companion/**`, `src/app/api/companion/**`,
`src/i18n/lanes/companion.ts`, `src/lib/backend/companion.ts`,
`e2e/companion.spec.ts`, y este documento.

No toco `apps/api/`, `apps/worker/`, `app/(console)/audit/**` (Agente E), ni
`app/(console)/layout.tsx` ni `lib/backend.ts` ni `lib/principal-access.ts`
(fuera de zona: por eso D16 lee la bandera por su propio enrutador BFF).

`packages/ui` no hace falta: el ticket, el panel y la pausa se componen con
`Alert`, `Badge`, `Button`, `Skeleton` y una `<table>`, que ya existen.

---

## 7. Cómo pruebo lo que no tiene backend

Igual que CO-03 y por el mismo motivo: **dobles con los payloads literales de
la v2**, copiados carácter a carácter. El publicador borra en silencio
cualquier clave no declarada, así que un nombre mal escrito falla callado en
producción en vez de ruidoso aquí.

Los fixtures nuevos van al mismo `__tests__/fixtures.ts` que los de la Ola 1.

Playwright: escribo los casos nuevos con rutas interceptadas donde puedo, pero
**no está en CI y necesita consola y API vivas**. Como el backend de la Ola 2 no
existe, los casos que dependen de él quedan marcados para la Fase 2.
