# Tabla de paridad — spec 017 (R12.1)

Campo a campo y acción a acción, **antes → después**, por pantalla. Cada fila
termina en «se conserva», «se mueve a …» o «se retira porque …», y ninguna
fila retira algo sin decisión escrita del owner. La tabla de una pantalla se
completa **antes** de implementarla y se revisa al cerrar la iteración.

Leyenda: ✅ se conserva · ➡️ se mueve · ❌ se retira (con decisión) · ➕ nuevo.

## Iteración 1 · Ficha del cliente (`/clients/{ref}`)

Fuente: `apps/console/src/app/(console)/clients/[ref]/layout.tsx`, `page.tsx`,
`components/clients/client-tabs.tsx`, `lifecycle-actions.tsx`, `health.ts`.

| # | Hoy (antes) | Después | Estado | Revisado contra el código (2026-09-26) |
|---|---|---|---|---|
| 1 | Migas «Clientes / {referencia}» en mono | Migas «Clientes / {nombre}»; la referencia vive en Datos del cliente (copiable) | ➡️ | ✅ migas «Clientes / {nombre}», sin mono. La referencia es copiable desde «Más» y editable en Datos del cliente |
| 2 | Título: nombre del cliente | Igual | ✅ | ✅ `layout.tsx` |
| 3 | Badge de estado del ciclo de vida | Igual, en la cabecera | ✅ | ✅ `ClientStatusBadge` en la cabecera |
| 4 | Zona horaria en mono junto al estado | Datos del cliente | ➡️ | ✅ fuera de la cabecera; se lee y se edita en Datos del cliente |
| 5 | Teléfono conectado en mono | En la cabecera, en texto normal, si hay canal | ✅ | ✅ en texto normal junto al estado |
| 6 | Tarjeta «Listo para atender / Falta: …» con cada elemento enlazado | Cuatro puntos con nombre + un botón con el primer paso pendiente | ✅ | ✅ `ClientSetup` + `client-header-model` (8 casos). Sin ordinales ni conectores: los pasos son independientes |
| 7 | Descripción «Agente: v3 · WhatsApp: conectado» | El punto «agente» muestra «v3» al pasar/enfocar; el de «canal», el número | ✅ | ✅ el dato va **a la vista**, no en un tooltip: «Agente · versión 1», «Canal · +34…». Lo que solo existe al pasar el ratón no existe en táctil ni en un lector |
| 8 | Aviso «Sin cupo» con enlace a Consumo (016 R2) | Punto «crédito» + botón «Asignar crédito» que abre el diálogo aquí mismo | ✅ | ⚠️ **parcial**: el botón existe y lleva a `/usage`, que es la pantalla que lo asigna hoy. El diálogo sin salir de la ficha es de la iteración 3 |
| 9 | Botón «Ir a Agente» de la tarjeta | Botón del primer paso pendiente | ➡️ | ✅ `nextAction()` |
| 10 | Botones Pausar / Reactivar / Archivar en la tarjeta | Menú «Más» en la cabecera | ➡️ | ✅ movidos; la fila suelta de la tarjeta de Resumen se retira para no ofrecer dos veces lo mismo. El componente conserva las dos formas |
| 11 | Botón Eliminar (rojo) siempre visible con `clients:delete` | En «Más», solo archivado; misma confirmación por nombre | ✅ | ✅ `moreMenuItems()` (4 casos) + e2e |
| 12 | Métricas Conversaciones · Escaladas · Fallidas con enlace | Se conservan en Resumen | ✅ | ✅ intactas |
| 13 | 10 pestañas planas | Tres grupos: Observar · Configurar · Conectar | ✅ | ✅ `client-nav-model` (8 casos). Son **once**: «Ajustes» pasó a ser los del agente y los datos del cliente tienen pestaña propia, porque compartirla hacía que el punto de «sin publicar» señalara una pantalla que no había cambiado |
| 14 | Pestaña Herramientas | Capacidades (fusión con Habilidades) + Integraciones | ➡️ it. 2 | ⏭️ iteración 2 (T037). La URL `/capabilities` ya existe y redirige |
| 15 | Pestaña Habilidades | Capacidades | ➡️ it. 2 | ⏭️ iteración 2 (T037) |
| 16 | Pestañas visibles para todos, con 403 al entrar | Filtradas por permiso de lectura | ✅ | ✅ `navGroupsFor()` por rol |
| 17 | Redirección al entrar en la URL raíz | Resumen sin redirección visible | ✅ | ✅ la raíz es Resumen; no hay `redirect` en `page.tsx` |
| 18 | Toast «Borrador guardado · Ir a publicar» en Ajustes, Herramientas, Habilidades | Barra de borrador en todas las pestañas + toast que solo confirma | ✅ | ✅ barra en el layout; los toasts pasan a «Borrador v{v} creado.» |
| 19 | Publicar y Revertir en Agente con confirmación | Se conservan; Publicar también desde la barra | ✅ | ✅ intactos + `publishFromBarAction` con `from: "draft_bar"` en la auditoría |
| 20 | Diff del prompt en Agente (`prompt-diff.tsx`) | Se conserva, y «Ver los cambios» lo incluye plegado | ✅ | ✅ intacto en Agente, y la hoja lo pliega dentro con el mismo componente |
| 21 | — | Crédito restante como barra en la cabecera | ➕ | ✅ `Meter`; la barra mide lo que QUEDA y su tono va con ella |
| 22 | — | «Atendiendo desde el {fecha}» cuando está listo | ➕ | ✅ `serving_since` derivado de la última pieza que lo permitió (versión publicada o canal conectado), sin migración; `null` mientras falte algo |
| 23 | — | Barra de borrador con «Ver los cambios» por pantalla | ➕ | ✅ `DraftBar` + hoja con el `draft-diff` real |

**Cierre de la iteración 1 (2026-09-26)**: **21 filas cerradas**, 1 parcial
(8: asignar crédito lleva a Consumo; el diálogo sin salir de la ficha es de
la iteración 3, por alcance) y 2 diferidas a la iteración 2 (14 y 15, con la
URL `/capabilities` ya fijada y redirigiendo). Ninguna fila retira nada sin
decisión escrita.

El owner decidió el 2026-09-26 que las cinco pendientes entraban en esta
iteración, y entraron. La fila 7 se resolvió **a la vista** y no con un
tooltip, que es lo que pedía la tabla: un dato que solo aparece al pasar el
ratón no existe en una pantalla táctil ni para un lector de pantalla.

## Iteración 2 · Capacidades e Integraciones (`/capabilities`, `/integrations`)

Fuente: `components/agent-tools/tools-catalog.tsx` (603 L), `skills-grid.tsx`,
`lib.ts`, las cuatro páginas de `/tools` y `/skills` con su `loading`/`error`,
sus dos `actions.ts` y `i18n/lanes/agent-tools.ts`. Inventariado el 2026-09-26
antes de escribir una línea de la pantalla nueva.

### Lo que hoy hay en Herramientas

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 24 | Nombre técnico en mono (`booking.check_availability`) como único nombre | Nombre de negocio y descripción en el idioma del partner; el técnico pasa a detalle plegado | ➡️ detalle |
| 25 | Descripción libre | Igual, bajo el nombre de negocio | ✅ |
| 26 | Casilla por fila, **no guarda hasta pulsar «Guardar herramientas»** | Conmutador que guarda con el clic, sin «Guardar» aparte (R5.4) | ➡️ (decisión escrita: R5.4) |
| 27 | «Marcar todas» / «Desmarcar todas» (solo estado local) | Se conservan, ahora sobre **las visibles** del filtro actual, guardando | ✅ |
| 28 | Insignia «En la versión activa» | Se conserva | ✅ |
| 29 | Insignia «Aún no publicada» | Se conserva | ✅ |
| 30 | Insignias «Solo lectura» y «Destructiva» | Se conservan | ✅ |
| 31 | Insignia «Requiere conectar {X}» + ayuda «Marcada pero inutilizable» | Se conserva y además enlaza a conectarlo; no cuenta como utilizable (R5.8) | ✅ (mejor) |
| 32 | Etiquetas `#tag` de capacidad | Al detalle plegado, con el nombre técnico y la versión (R5.6) | ➡️ detalle |
| 33 | Selector de modo por fila: `__default` · Siempre · **Requiere aprobación** · Bloqueada | Siempre y Bloqueada se conservan con sus nombres; **«Requiere aprobación» se retira** (R5.7) y una versión anterior que lo tuviera muestra su modo efectivo real | ❌ (decisión escrita: R5.7) |
| 34 | El modo **guarda con el clic**, sin botón | Igual | ✅ |
| 35 | Ayuda «Modo forzado por ti» cuando hay `override_mode` | Se conserva | ✅ |
| 36 | Contador «{n} de {total} herramientas marcadas», `aria-live` | Se conserva, por la vista actual | ✅ |
| 37 | Aviso de solo lectura + casillas deshabilitadas sin `agents:write` | El conmutador **no existe** y el estado se lee igual (R5.4) | ➡️ (mejor: sin controles muertos) |
| 38 | Agrupación por conector, nativas primero | Agrupación **por función** (Citas, Pedidos, Mensajes, Escalado, Conocimiento, Otras); el conector se dice en la tarjeta | ➡️ (R5.1) |
| 39 | Sin buscador, sin filtros | Buscador por nombre de negocio y descripción (R5.5) + filtro por sector con «Ver todas» y cuántas oculta (R5.2) | ➕ |
| 40 | Sin marca de «recomendada» | «Recomendada para tu sector» en las que la plantilla enciende (R5.3) | ➕ |
| 41 | Alerta inline cuando los conectores no cargan, y la lista sigue | Se conserva: una fuente que falla no puede tumbar la pantalla | ✅ |
| 42 | **El estado vacío del catálogo oculta también los conectores** | Se corrige: sin catálogo, las integraciones siguen a la vista | ✅ (fallo de hoy) |
| 43 | Toast «Lista blanca guardada en el borrador v{v}» con enlace a publicar | Solo confirma; la barra de borrador es quien lleva a publicar (fila 18) | ➡️ |

### Integraciones (hoy dentro de Herramientas)

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 44 | Cabecera por conector: nombre, estado con sus 8 tonos, «{on} de {total} activas», última sincronización | A la pestaña **Integraciones**, y como bloque superior de Capacidades cuando algo visible dependa de uno sin conectar (R4.1) | ➡️ |
| 45 | Conectar / Reconectar (consentimiento firmado en ventana nueva, con enlace de respaldo si el navegador la bloquea) | Se conserva entero | ✅ |
| 46 | Diálogo de clave de API con campos traducidos, obligatorios validados, secretos como contraseña; «Guardar y conectar» sincroniza en la misma llamada | Se conserva entero | ✅ |
| 47 | AgendaPro por URL pública: enlazar, cambiar, desenlazar, validación `agendapro.com`, textos propios | Se conserva entero | ✅ |
| 48 | Sincronizar · Pausar · Reanudar · Desconectar (con confirmación) | Se conservan | ✅ |
| 49 | Tira del último sync con «Reintentar» y «Corregir» | Se conserva | ✅ |
| 50 | — | Qué desbloquea cada integración, en lenguaje de negocio (R4.2) | ➕ |
| 51 | — | Al conectar, lo que dependía pasa a utilizable **sin recargar a mano** (R4.3) | ➕ |

### Lo que hoy hay en Habilidades

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 52 | Pantalla propia en rejilla de tarjetas | Se fusiona en Capacidades; `/skills` redirige | ➡️ (R5.1) |
| 53 | Nombre técnico como único nombre | Nombre de negocio; el técnico al detalle | ➡️ detalle |
| 54 | Descripción recortada a 3 líneas con `title` | Se conserva | ✅ |
| 55 | «Versión {v}» por tarjeta | Al detalle plegado, como fecha (R5.6) | ➡️ detalle |
| 56 | Insignia «En la versión activa» | Se conserva | ✅ |
| 57 | «No activable en esta versión…» **bloquea la casilla** | **Decisión pendiente**: hoy las herramientas avisan y dejan marcar, las habilidades bloquean. Una pantalla no puede tener dos políticas ante el mismo problema | ⚠️ pendiente |
| 58 | Casilla, guardar con botón «Guardar habilidades» | Conmutador que guarda con el clic (R5.4) | ➡️ |
| 59 | Contador «{n} de {total} activadas» | Se funde con el de herramientas | ➡️ |
| 60 | Aviso de solo lectura | Igual que en herramientas: sin conmutador | ➡️ |
| 61 | Sin «marcar todas», sin buscador, sin modo | Los hereda de la pantalla unificada; el modo **no** (las habilidades no lo tienen) | ➕ |
| 62 | Estado vacío propio («para este vertical») e icono `Sparkles` | Un solo estado vacío, que distinga catálogo vacío de filtro sin resultados | ➡️ |

### Decisiones que faltan antes de implementar

1. **Fila 57** — qué hace una capacidad que no se puede activar: ¿avisar y dejar
   marcar, como las herramientas, o bloquear, como las habilidades? Afecta a
   las dos mitades de la pantalla.
2. **Modos**: los valores reales son `always`, `needs_approval`, `blocked`. La
   spec (R5.7) habla de «siempre» y «nunca»; «nunca» es `blocked`. Hay que
   fijar el nombre visible antes de escribir el copy.
3. **Dónde vive cada cosa**: qué parte de los conectores se queda como bloque
   superior de Capacidades y qué parte solo existe en Integraciones (R4.1).



## Iteración 3 · Consumo

_Se completa al empezar la iteración, desde `usage/page.tsx`, `usage/alerts/*`, `buy-credit-form.tsx`._

## Iteración 4 · Alta

_Se completa al empezar la iteración, desde `clients/new/wizard.tsx`._

## Iteración 5 · Inicio y lista

_Se completa al empezar la iteración, desde `(console)/page.tsx`, `clients/page.tsx`, `clients-table.tsx`._

## Iteración 6 · Ajustes del agente

_Se completa al empezar la iteración, desde `agent-settings-form.tsx` y `settings-schema.ts`._

## Iteración 7 · Transversal

_Playground, Ajustes del cliente, Facturación, Notificaciones, Auditoría._
