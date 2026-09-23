# Tabla de paridad — spec 017 (R12.1)

Campo a campo y acción a acción, **antes → después**, por pantalla. Cada fila
termina en «se conserva», «se mueve a …» o «se retira porque …», y ninguna
fila retira algo sin decisión escrita del owner. La tabla de una pantalla se
completa **antes** de implementarla y se revisa al cerrar la iteración.

Leyenda: ✅ se conserva · ➡️ se mueve · ❌ se retira (con decisión) · ➕ nuevo.

## Iteración 1 · Ficha del cliente (`/clients/{ref}`)

Fuente: `apps/console/src/app/(console)/clients/[ref]/layout.tsx`, `page.tsx`,
`components/clients/client-tabs.tsx`, `lifecycle-actions.tsx`, `health.ts`.

| # | Hoy (antes) | Después | Estado |
|---|---|---|---|
| 1 | Migas «Clientes / {referencia}» en mono | Migas «Clientes / {nombre}»; la referencia vive en Ajustes del cliente (Datos, copiable) | ➡️ Ajustes del cliente |
| 2 | Título: nombre del cliente | Igual | ✅ |
| 3 | Badge de estado del ciclo de vida | Igual, en la cabecera | ✅ |
| 4 | Zona horaria en mono junto al estado | Ajustes del cliente (Datos) | ➡️ |
| 5 | Teléfono conectado en mono | En la cabecera, en texto normal, si hay canal | ✅ |
| 6 | Tarjeta «Listo para atender / Falta: …» con cada elemento enlazado | Cuatro puntos con nombre en la cabecera + un botón con el primer paso pendiente; los demás pasos siguen enlazados al pulsarlos | ✅ (forma nueva) |
| 7 | Descripción «Agente: v3 · WhatsApp: conectado» | Punto «agente» muestra «v3» al pasar/enfocar; punto «canal» muestra el número | ✅ |
| 8 | Aviso «Sin cupo» con enlace a Consumo (016 R2) | Punto «cupo» en aviso + botón «Asignar cupo» que abre el diálogo de tope aquí mismo | ✅ (acción más corta) |
| 9 | Botón «Ir a Agente» de la tarjeta | Botón del primer paso pendiente | ➡️ |
| 10 | Botones Pausar / Reactivar / Archivar en la tarjeta | Menú «Más» en la cabecera | ➡️ |
| 11 | Botón Eliminar (rojo) siempre visible con `clients:delete` | En «Más», solo con el cliente archivado; misma confirmación por nombre | ✅ (condición nueva, decisión del owner en el plan) |
| 12 | Métricas Conversaciones · Escaladas · Fallidas con enlace | Se conservan en Resumen | ✅ |
| 13 | 10 pestañas planas: Resumen, Agente, Herramientas, Habilidades, Conocimiento, Playground, Puesto de trabajo, Canales, Conversaciones, Ajustes | Tres grupos: Configurar (Agente, Ajustes, Capacidades, Conocimiento) · Conectar (Canales, Integraciones, Puesto de trabajo) · Observar (Resumen, Conversaciones, Playground) | ✅ |
| 14 | Pestaña Herramientas | Capacidades (fusión con Habilidades) + Integraciones | ➡️ iteración 2 |
| 15 | Pestaña Habilidades | Capacidades | ➡️ iteración 2 |
| 16 | Pestañas visibles para todos los roles, con 403 al entrar | Filtradas por permiso de lectura | ✅ (menos ruido) |
| 17 | Redirección al entrar en la URL raíz | Resumen sin redirección visible | ✅ |
| 18 | Toast «Borrador guardado · Ir a publicar» en Ajustes, Herramientas, Habilidades | Barra de borrador en todas las pestañas + toast que solo confirma | ✅ (más visible) |
| 19 | Publicar y Revertir en Agente con confirmación | Se conservan; Publicar también desde la barra | ✅ |
| 20 | Diff del prompt en Agente (`prompt-diff.tsx`) | Se conserva, y «Ver diferencias» lo incluye plegado | ✅ |
| 21 | — | Cupo restante como barra en la cabecera | ➕ |
| 22 | — | «Atendiendo desde el {fecha}» cuando está listo | ➕ |
| 23 | — | Barra de borrador con «Ver diferencias» por pantalla | ➕ |

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
