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
| 1 | Migas «Clientes / {referencia}» en mono | Migas «Clientes / {nombre}»; la referencia vive en Datos del cliente (copiable) | ➡️ | ⏳ **pendiente**: las migas siguen con la referencia en mono. La referencia ya es copiable desde «Más». |
| 2 | Título: nombre del cliente | Igual | ✅ | ✅ `layout.tsx` |
| 3 | Badge de estado del ciclo de vida | Igual, en la cabecera | ✅ | ✅ `ClientStatusBadge` en la cabecera |
| 4 | Zona horaria en mono junto al estado | Datos del cliente | ➡️ | ⏳ **pendiente**: sigue en la cabecera en mono |
| 5 | Teléfono conectado en mono | En la cabecera, en texto normal, si hay canal | ✅ | ⏳ **pendiente**: sigue en mono |
| 6 | Tarjeta «Listo para atender / Falta: …» con cada elemento enlazado | Cuatro puntos con nombre + un botón con el primer paso pendiente | ✅ | ✅ `ClientSetup` + `client-header-model` (8 casos). Sin ordinales ni conectores: los pasos son independientes |
| 7 | Descripción «Agente: v3 · WhatsApp: conectado» | El punto «agente» muestra «v3» al pasar/enfocar; el de «canal», el número | ✅ | ⏳ **pendiente**: los pasos no llevan detalle al pasar el ratón. El dato sigue visible en la tarjeta de salud de Resumen |
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
| 20 | Diff del prompt en Agente (`prompt-diff.tsx`) | Se conserva, y «Ver los cambios» lo incluye plegado | ✅ | ⚠️ **parcial**: `prompt-diff.tsx` intacto en Agente; la hoja dice «Las instrucciones del agente cambian» pero aún no lo pliega dentro |
| 21 | — | Crédito restante como barra en la cabecera | ➕ | ✅ `Meter`; la barra mide lo que QUEDA y su tono va con ella |
| 22 | — | «Atendiendo desde el {fecha}» cuando está listo | ➕ | ⏳ **pendiente**: la fecha de inicio de servicio no la devuelve la API |
| 23 | — | Barra de borrador con «Ver los cambios» por pantalla | ➕ | ✅ `DraftBar` + hoja con el `draft-diff` real |

**Cierre de la iteración 1 (2026-09-26)**: 16 filas cerradas, 2 parciales
(8 y 20), 5 pendientes (1, 4, 5, 7, 22) y 2 diferidas a la iteración 2 (14,
15). Ninguna fila retira nada sin decisión escrita. Las cinco pendientes son
de colocación y de un dato que la API no da; ninguna bloquea el uso de la
ficha, pero **la iteración no se da por cerrada hasta que el owner decida**
si entran ahora o se difieren.

## Iteración 2 · Capacidades e Integraciones

_Se completa al empezar la iteración, desde `tools-catalog.tsx` y `skills-grid.tsx`._

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
