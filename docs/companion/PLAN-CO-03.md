# CO-03 · Cajón y burbuja del Companion

> Plan de ejecución del paquete de interfaz del Companion (Ola 1, Fase 1).
> Fuente normativa: [`CONTRACT-V1.md`](CONTRACT-V1.md) — **manda sobre todo lo
> demás**. Especificación de producto: §14 (interfaz), §8 (eventos), §10 (HITL),
> §4.1-4.2 (burbuja y cajón) y §19 (catálogo) de
> `Auphere/nexus/research/2026-08-17-companion-agente-de-consola.md`;
> §22 C1 (reconexión) y §24 (parada explícita) de la Parte II.
>
> Este documento vive en el repo a propósito: el cambio cruza ~20 archivos de
> `apps/console`. Sobrevive a la compactación; el historial de chat no.

---

## 0. Qué entrega CO-03

La cara del Companion, y nada más que la cara:

- **burbuja** anclada abajo a la derecha, presente en toda la consola salvo
  `(auth)`, con sus cuatro estados (inactiva · trabajando · esperando
  confirmación · deshabilitada por rol o por tope);
- **cajón** (`Sheet` lateral de `@nexus/ui`) con ancho redimensionable
  persistido, hilo activo en la URL y modo Consultar/Construir;
- **timeline del hilo** que pinta los 18 eventos del §2.7 del contrato, incluidos
  los cinco que **todavía no emite nadie** (`plan.proposed`, `intake.missing`,
  `hitl.requested`, `hitl.resolved`, `verify.result`);
- **medidores** de coste del turno, ventana de contexto y tope mensual;
- los **cinco estados de Hurff**, WCAG 2.2 AA, ES/EN y cero hex suelto.

Fuera de alcance: el backend de las propuestas y el HITL (CO-04, en paralelo),
los evals (CO-07), y todo lo posterior a la Ola 1.

---

## 1. La restricción que define el paquete

**CO-04 aún no existe.** Los cinco eventos de propuesta/HITL/verificación se
construyen **contra el contrato**, no contra una implementación observable, y se
prueban con **dobles**: fixtures de eventos SSE con el payload literal del §2 del
contrato. La integración real la valida la Fase 2.

Consecuencia de diseño, no accidente: **el reductor del timeline es una función
pura y separada de todo React** (`state.ts`). Es lo único que puede probarse
exhaustivamente hoy contra un contrato de papel, y es donde vive la lógica que
más cara sale si está mal (deduplicación, sellado de tarjetas, medidores).

Lo mismo vale para `POST …/resume` y `GET /console/companion/actions/{id}`: se
tipan contra el contrato y se mockean en las pruebas.

---

## 2. Decisiones abiertas — con recomendación

### D1 · ¿Cómo llama el cajón a la API? → **Route handlers bajo `app/api/companion/**`**

La consola tiene dos patrones para hablar con el backend: *server actions*
(`app/(console)/**/actions.ts`, que es lo que usa el playground) y *route
handlers* (`app/api/**`, que es lo que usa el proxy SSE y las descargas).

Se eligen los route handlers, por dos motivos independientes:

1. **Zona.** `app/(console)/**/actions.ts` **no está en la zona de CO-03**;
   `app/api/companion/**` sí. Un archivo de acciones nuevo bajo `(console)`
   sería tocar fuera de zona para conseguir lo mismo.
2. **Forma.** El cajón vive en el *shell*, no en una ruta. Es un componente de
   cliente montado en el layout que ya hace `fetch` contra el proxy SSE del
   mismo directorio. Meter la mitad de sus llamadas por *server actions* y la
   otra mitad por `fetch` sería dos mecanismos para un solo consumidor.

Ninguno de los dos patrones es más seguro que el otro: los dos resuelven el
principal en el servidor, comprueban `companion:use` y acuñan un token de 60 s.
Ese es el invariante que importa y se mantiene idéntico.

### D2 · Enumerar los runs de un hilo → **RESUELTO en el contrato v1.1 (§5.2)**

**Planteamiento original.** El §4.3 dice que el timeline es **del hilo**: hay que
concatenar los `…/runs/{id}/events` de los runs del hilo. Pero la API no exponía
ningún `GET /console/companion/threads/{id}/runs` — solo
`POST …/threads/{id}/runs` (arrancar) y `GET …/runs/{id}/events` (leer uno). Desde
el navegador no había manera de descubrir qué runs tuvo un hilo, así que el índice
tenía que vivir en `localStorage`… y entonces **el requisito de §14 de que
`?companion=<thread>` sea compartible dentro del equipo se rompía**: quien abriera
el enlace en otra máquina vería un hilo vacío.

**Resolución.** Se elevó al orquestador y el contrato pasó a **v1.1**: el endpoint
existe y es **requerido** (§5.2), lo construye el Agente B. Un índice local no era
un fallo de la interfaz, era la ausencia del dato en el servidor.

La interfaz queda así:

- **El servidor es la fuente.** `openThread` llama a `GET …/threads/{id}/runs`,
  que devuelve `{thread_id, runs[{run_id, status, started_at, ended_at}]}`
  ascendente por `started_at`, y concatena en ese orden deduplicando por
  `(run_id, seq)`.
- **`localStorage` queda como caché, no como fuente.** Se refresca con lo que
  diga el servidor (`cacheRunIds`, que **reemplaza**, no fusiona).
- **El camino degradado sigue existiendo**, porque un endpoint puede fallar: si
  la llamada devuelve 5xx o no hay red, se cae a la caché y **el timeline se
  marca parcial** — no se puede prometer completitud con un índice que no
  incluiría un run arrancado en otra máquina. Un 404/401/403 no es un hueco que
  tapar: es estado de error.
- **`status` del servidor decide si hay que engancharse al stream**, en vez de
  deducirlo del replay. Un run cuyo `run.completed` haya rotado fuera del log
  parecería vivo para siempre y mantendría una conexión abierta para nada.

El estado *parcial* deja de ser la norma para una URL compartida y vuelve a ser lo
que debía ser: un fallo.

### D3 · Reductor puro y separado → **`state.ts`, deduplicación por `(run_id, seq)`**

Todo el estado del timeline sale de una función
`companionReducer(state, action) → state` sin nada de React dentro. Entradas:
eventos SSE, eventos del historial REST, y las transiciones de conexión.

- **Deduplicación por `(run_id, seq)`**, no por `seq`: el §4.3 obliga a
  concatenar varios runs y `seq` es monótono **por run**, así que dos runs del
  mismo hilo tienen `seq` solapados. Deduplicar solo por `seq` borraría eventos
  legítimos del segundo run — es el error exacto que este plan quiere evitar.
- `hitl.resolved` **sella** la tarjeta de `hitl.requested` buscándola por
  `action_id`; no añade una tarjeta nueva (§2.4 del contrato).
- `verify.result` se ancla a su `action_id` cuando lo hay.

### D4 · Modo Consultar/Construir → **el hilo manda; `localStorage` es el defecto**

§14 dice "modo en `localStorage`". El backend, sin embargo, ya guarda `mode` en
`companion.threads` y lo acepta en `PATCH …/threads/{id}`. Se hacen las dos
cosas, y no es redundancia:

- el **hilo** lleva su modo (es lo que decide qué herramientas se habilitan, y
  tiene que ser igual para cualquiera que abra ese hilo por la URL compartida);
- `localStorage` guarda **la última elección del usuario**, que es con la que
  arranca un hilo nuevo.

Cambiar el modo es un acto del usuario y hace `PATCH`; nunca lo cambia el modelo.

### D5 · Ancho redimensionable → **`role="separator"` con teclado, no solo arrastre**

WCAG 2.2 añade **2.5.7 Dragging Movements**: una función que solo se puede usar
arrastrando falla el criterio. El asa de redimensionado es por tanto un
`role="separator"` enfocable con `aria-orientation="vertical"`,
`aria-valuenow/min/max`, y flechas ←/→ (±16 px, ±64 px con Shift), además del
arrastre. Ancho persistido en `nexus.companion.width`, acotado a 380-880 px.

Por debajo de 768 px el cajón es de pantalla completa y el asa **no se renderiza**
(no hay nada que redimensionar y un objetivo táctil inútil es peor que ninguno).

### D6 · Hilo en la URL → **`window.history.replaceState`, no `router.replace`**

`?companion=<thread>` tiene que ser compartible dentro del equipo, pero el cajón
vive en el layout: `router.replace` volvería a ejecutar los componentes de
servidor de la página en cada apertura del cajón. Se usa
`window.history.replaceState`, que el App Router de Next 16 soporta para
navegación superficial, y se lee de `window.location.search` al montar. Eso
además evita el requisito de envolver `useSearchParams` en `<Suspense>`.

### D7 · `preview` de un `kind` desconocido → **vista genérica clave/valor**

El §3.4 del contrato lo pide explícitamente: es lo que permite que CO-04 añada un
`kind` sin romper la interfaz. Se implementan las cuatro formas garantizadas
(`prompt`-like, `publish`, `client`, `invite`) y una vista genérica de reserva.

### D8 · Cuenta atrás → **solo desde `expires_at`**

La interfaz **no** calcula 15 minutos por su cuenta (§2.3 del contrato). Si el
backend cambia el plazo, la interfaz sigue. Al vencer, la tarjeta se marca como
caducada y los botones se deshabilitan: la decisión ya no es posible y ofrecerla
sería mentir.

### D9 · `phase` y los nombres de comprobación → **los traduce la línea, no el backend**

§1.4 del contrato: `phase.changed.label` viene en español hardcodeado y **no se
pinta**. Se pinta `phase` traducido por `i18n/lanes/companion.ts`. Igual para
`verify.result.checks[].name`. Las dos excepciones que sí se pintan tal cual son
`citation.claim` y `tool.call.started.label`, que salen del catálogo de
herramientas de CO-02, y `plan.proposed.steps[].title`, que lo redacta el modelo
(§2.1).

### D10 · Estado vacío → **tres sugerencias derivadas del `page_context` real**

§14 prohíbe las genéricas. Las sugerencias se derivan de la ruta en la que está
el usuario y del cliente que hay en ella: en `/clients/boreal/channels` no se
ofrece "explícame el consumo", se ofrece "¿por qué bajó la calidad de este
número?". Sin cliente en la ruta, las sugerencias son de nivel de partner.

### D11 · `Esc` con confirmación pendiente → **`eventDetails.cancel()`**

Base UI expone el motivo del cierre (`escape-key`, `outside-press`,
`close-press`) y un `cancel()`. Con una confirmación pendiente se cancelan
`escape-key` y `outside-press`, y se anuncia por qué; el botón ✕ explícito
también, porque cerrar por accidente una decisión pendiente es el fallo caro.
El foco atrapado lo da `modal` de Base UI, que ya es el defecto del `Sheet`.

### D12 · El pensamiento no sobrevive a la recarga → **y se dice**

§8.2: el razonamiento no se persiste. La línea de resumen ("Pensó 4 s · comprobó
3 cosas") se calcula en el navegador a partir del tiempo entre el primer
`reasoning.delta` y el siguiente evento no-razonamiento, y del número de
herramientas del turno. Tras un F5 el historial REST no trae `reasoning.delta`
y la sección simplemente no aparece — no se pinta un "Pensó 0 s" falso.

---

## 3. Archivos

Todos dentro de la zona de CO-03 del §9 del contrato.

| Archivo | Qué hace |
|---|---|
| `components/companion/state.ts` | **El reductor puro.** Eventos → timeline, medidores, fase, acción pendiente. Deduplicación por `(run_id, seq)` |
| `components/companion/types.ts` | Narrowing de los payloads del §2 del contrato. Ni un `as` sin comprobar |
| `components/companion/client.ts` | `fetch` contra `/api/companion/*`. Resultado discriminado, nunca lanza |
| `components/companion/page-context.ts` | Ruta → `{route, client_ref, tab, selection}` + las tres sugerencias |
| `components/companion/companion-launcher.tsx` | Burbuja + cajón. El punto de montaje |
| `components/companion/drawer.tsx` | `Sheet`, ancho redimensionable, guardia de `Esc`, hilo en la URL |
| `components/companion/timeline.tsx` | `role="log"` `aria-live="polite"` + región `assertive` propia |
| `components/companion/thinking.tsx` | Pensamiento colapsable |
| `components/companion/tool-card.tsx` | Nombre humano + desplegable con petición/respuesta crudas |
| `components/companion/plan-card.tsx` | Tarjeta de plan |
| `components/companion/intake-card.tsx` | Expediente: chips respondibles, **no un formulario** |
| `components/companion/confirm-card.tsx` | Confirmación: diff, impacto, cuenta atrás, Confirmar/Editar/Cancelar |
| `components/companion/verify-table.tsx` | Tabla de verificación |
| `components/companion/meters.tsx` | Coste · contexto · tope mensual |
| `components/companion/composer.tsx` | Entrada + modo + Enviar/Detener |
| `i18n/lanes/companion.ts` | ES/EN completo |
| `app/api/companion/**` | Route handlers (D1) |
| `lib/backend/companion.ts` | +`resumeCompanionRun`, +`getCompanionAction` (tipados contra el contrato) |
| `e2e/companion.spec.ts` | axe, 360/1920, cadena alemana, teclado |

---

## 4. El bucle de conexión (C1), literal

Es la parte con más trampas, así que queda escrita:

```
abrirHilo(threadId):
  GET …/threads/{threadId}/runs   → runs[] ascendente          (D2, §5.2)
      ok        → runIds = runs.map(run_id); refrescar la caché; parcial=no
      404/401/403 → estado de ERROR (no es un hueco que tapar)
      otro fallo  → runIds = caché de localStorage; parcial=SÍ
  para cada runId en orden:
      GET …/runs/{runId}/events?since_seq=0   → al reductor
  si runs.at(-1).status == "running":
      conectarStream(ultimoRunId, since=última seq vista de ESE run)

conectarStream(runId, since):
  fetch del proxy SSE  → parser incremental → reductor
  al reconectar: NO se reinicia `since`; se pide desde la última seq de ese run
  run.completed → parar

enviar(prompt):
  POST …/threads/{id}/runs {prompt, page_context}   → 202 {run_id}
  añadir run_id al índice; conectarStream(run_id, 0)

decidir(action_id, decision, note):
  POST …/runs/{runActual}/resume                    → 202 {run_id: NUEVO}
  añadir el run NUEVO al índice; conectarStream(nuevo, 0)      (§4.3)

detener():
  DELETE …/runs/{runActual}     ← el trabajo se cancela AQUÍ
  (abortar el fetch solo cierra la vista; no cancela nada — §24)
```

---

## 5. Pruebas

- **Unitarias (vitest)** sobre el reductor y los componentes, con **fixtures de
  eventos SSE con el payload literal del §2 del contrato**. Es la única defensa
  real contra la desincronización con CO-04.
- Casos que tienen prueba propia por ser los caros: deduplicación por
  `(run_id, seq)` con `seq` solapados entre runs; sellado de la tarjeta por
  `action_id`; `context.updated` ausente ⇒ **sin medidor**, nunca una barra al
  0 % (§2.6); `kind` desconocido ⇒ vista genérica; `expires_at` vencido ⇒
  botones deshabilitados; `Detener` llama al `DELETE`.
- **e2e (Playwright)** con axe sobre el cajón abierto, a 360 px y 1920 px, con
  la cadena alemana y con el flujo de confirmación por teclado.

---

## 5.1. Lo que encontró Playwright al correr de verdad (2026-08-19)

Los nueve casos se escribieron a ciegas y al ejecutarse encontraron **un fallo
real de producto y tres artefactos de medición**. Merece la pena separarlos,
porque la lección de cada uno es distinta.

**Fallo real — el estado vacío no existía.** `status` arrancaba en `"loading"` y
solo pasaba a `"ready"` dentro de `openThread`. Al abrir el cajón sin
`?companion=` en la URL, `openThread` no se llama nunca: el timeline se quedaba
en esqueletos **para siempre** y el estado vacío —con sus tres sugerencias
derivadas del `page_context`— no podía renderizarse jamás. Arreglado arrancando
en `"ready"`: hasta que se abre un hilo no hay nada que cargar. De rebote se
arregló también el desbordamiento a 360 px, que era del esqueleto.

**Artefacto 1 — contraste.** axe reportaba tres nodos a 1,6-1,97:1. Medidos los
colores computados, el texto es casi negro sobre blanco (~19:1). La causa: el
`Sheet` tiene un fundido de 200 ms y la auditoría muestreaba **a mitad de la
transición**, con la capa a opacidad parcial. No era un token ni una clase. El
gate ahora espera a que la orquestación de apertura termine — que es lo que §14
presupone al presupuestarla en =300 ms.

**Artefacto 2 — trampa de foco.** El test leía `activeElement` justo después de
`press("Tab")` y veía el foco fuera del cajón. Base UI contiene el foco con
centinelas (`data-base-ui-focus-guard`, `aria-hidden`) que viven **fuera** del
popup y devuelven el foco desde su propio manejador; la lectura síncrona pillaba
ese relevo en el aire, y como la siguiente tabulación se pulsaba desde esa
posición intermedia, la deriva se acumulaba hasta llegar al enlace de saltar al
contenido. Medido dejando asentar el foco: **0 escapes de 20**. Para comparar, la
paleta de comandos (CP-07, ya auditada en CP-30) da **9 de 14** con el mismo
patrón — es comportamiento del primitivo, no de este paquete. El test ahora
afirma la garantía real (el foco no puede **quedarse** fuera) en vez de un
detalle de implementación.

**Artefacto 3 — selector ambiguo.** `[aria-live="assertive"]` resolvía a dos
elementos: el nuestro y el `#__next-route-announcer__` de Next. Acotado al cajón.

Nota para el sistema, **no** para este paquete: Base UI marca el contenido de
fuera con `aria-hidden` pero **no** con `inert`, y `aria-hidden` no saca nada del
orden de tabulación. Por eso los centinelas tienen que trabajar. Afecta a todos
los diálogos de la consola por igual; cambiarlo es tocar `packages/ui`.

---

## 6. Lo que este paquete NO puede cerrar

1. La integración real con los cinco eventos de CO-04 y con
   `GET …/threads/{id}/runs` — **Fase 2 por diseño**. Todo está cableado contra
   el contrato y doblado en las pruebas; nada de eso lo sirve nadie todavía.
2. `citation` se pinta como fuente junto al dato, pero sin `plan.proposed` real
   no hay forma de comprobar el encaje visual con datos de verdad.
3. ~~El gate de Playwright~~ — **cerrado el 2026-08-19**: el orquestador levantó
   el stack y los nueve casos pasan. Ver §5.1.
4. **Contraste de `--color-status-*` en tema oscuro**: no tienen override en
   `[data-theme="dark"]`, así que `text-status-danger` sobre `bg-card` queda
   flojo en oscuro. Es una propiedad del sistema (`packages/ui`) que ya usan el
   playground y agent-tools, no algo que introduzca CO-03. Anotado aparte.
