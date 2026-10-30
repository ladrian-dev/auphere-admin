# La consola de partners — spec viva

> Qué existe hoy en `apps/console` y en `/console/*` de `apps/api`, en línea
> con `kb/Auphere/nexus/architecture/console-map.md` (el mapa pantalla →
> acción → endpoint → tabla vive allí; aquí, las reglas). Se actualiza en el
> mismo commit que cambia el comportamiento (constitución §IX).
>
> La consola del **cliente final** (consola lite, spec 030) vive en la misma
> app y se describe aparte: [consola-lite.md](consola-lite.md); su versión para
> el teléfono, Auphere Customers, en [app-movil.md](app-movil.md). El panel de
> operador de Auphere, que comparte con ésta el sistema de diseño `@nexus/ui`,
> se describe en [admin.md](admin.md).

## Qué es

Una aplicación Next.js (App Router, BFF sin base de datos) donde un
**partner** —una agencia o integrador— opera a sus **clientes**: crea el
cliente, le asigna cupo, configura y publica su agente, conecta sus canales e
integraciones y observa lo que pasa. La API decide; la consola pinta y dice
«no puedes» antes del viaje con el mismo mapa de permisos
(`src/lib/permissions.ts` ↔ `core/console_auth.py`).

## El círculo que cierra (spec 016)

1. **Crear cliente** (`/clients/new`): cuatro etapas separadas —crear, generar
   el agente desde la plantilla, publicar, activar— cada una con su reintento.
   Publicar es `agents:write`; activar es `clients:write`. La ficha aterriza en
   `#setup` con lo que falta y su acción a un clic (`components/clients/health.ts`).
2. **Cupo** (`/usage`): la unidad es **créditos**. «Sin cupo» significa lo
   mismo en la ficha, la lista, la portada y el aviso que en la puerta del canal
   (`metering/wallet.py::quota_state`). Cuando un turno se salta por falta de
   cupo, el partner recibe `client.out_of_quota` (campana + correo, uno por
   cliente y día); el cliente final no recibe nada distinto. Mover cupo es
   **una** llamada transaccional (`POST /console/wallet/allocations/move`).
3. **Agente**: ajustes estructurados, herramientas, habilidades, conocimiento y
   la tarjeta **Modelo** (`GET /console/models` con `relative_cost`, «×N
   créditos»). Cambiar el modelo se aplica en el siguiente turno y se audita
   (`console.model.update`); si el plan deja de incluirlo, el binding se borra
   y llega `client.model_reset`.
4. **Canales**: «Conectar WhatsApp» es el Embedded Signup real cuando el entorno
   tiene `NEXUS_META_APP_ID` y un `NEXUS_META_CONFIG_ID_*`; sin ellos, la nota
   «lo conecta Auphere» (sin botón). Al volver, el cliente se activa si puede
   operar y la respuesta trae `client_status` y `health`. Un número de otro
   cliente es 409 `number_in_use`; cualquier fallo deja el signup sin rastro.
   **Desconectar** da de baja el número en Meta y, si era el último vivo de su
   cuenta, desuscribe la app, pero **solo si la suscripción emite al webhook de
   este entorno** (`NEXUS_META_WEBHOOK_CALLBACK_URL`). La app de Meta es la misma
   en staging y producción y cada entorno marca su suscripción con su
   `override_callback_uri`; si emite a otro sitio, o a ninguno, se deja como
   está y la auditoría lo dice en `meta.kept_subscription` (bug
   `desconectar-respeta-el-otro-entorno`). El número deja de llevar a su
   cliente **en el acto**: desconectar invalida la caché del resolver (una hora
   en Redis), antes incluso de llamar a Meta.
5. **Integraciones**: nunca se piden credenciales desde la consola (AgendaPro,
   que se enlazaba por su agenda pública, se retiró en la spec 048: ni su
   tarjeta ni su acción existen ya; las citas van por Reservas). Un conector por clave de API
   se guarda **y** sincroniza en la misma llamada; la respuesta dice qué pasó
   (`last_sync`), y las etiquetas de sus campos van en el idioma del partner
   (`connectors.field.{slug}.{campo}`).

## Un solo borrador por agente (spec 047, historia 2)

Llega a todos los partners, con la consola de hoy y con la nueva. Cada agente
tiene **como mucho un borrador** (`uq_agent_configs_one_draft`, migración 0178) y
todo cambio de comportamiento se escribe en él: las instrucciones, los ajustes,
las herramientas, las habilidades, el admin y la API de partners
(`services/agent_config_service.py`). Antes, guardar los ajustes y después el
prompt dejaba los ajustes en una versión que nadie iba a publicar.

- **Las rutas**: `GET/PATCH/DELETE /console/clients/{ref}/agents/{agent_id}/draft`
  y el historial `GET …/agents/{agent_id}/versions`
  (`api/console/agent_draft_routes.py`). `PATCH` y `DELETE` exigen `If-Match` con
  la `revision` que leyó la pantalla (`agents.draft_revision`); sin él, `428`. Si
  otra persona escribió entre medias, `412` con `detail.current` (el borrador
  como está) y `detail.changes` (quién cambió qué campos, en claves como
  `settings.tone`), y no entra nada.
- **Las rutas de antes** (`PUT …/agent/settings`, `PUT …/tools`, `PUT …/skills`,
  `PUT …/capabilities`, `POST …/agent/versions`) escriben en ese mismo borrador
  y mueven la revisión: otra pestaña con la de antes se entera.
- **El borrador nace** de la versión activa, o de la última publicada si no hay
  activa, con todos sus campos (también las capacidades del runtime) y recuerda
  de cuál partió. **Descartar** lo archiva sin publicarlo: el agente vuelve a su
  versión activa, que no cambia.
- **El número** va por agente («v{n} de {agente}», `agent_version_number`); el
  `version` de cada cliente no cambia y las rutas de antes lo siguen usando.
- **La pestaña Agente** tiene **una sola barra de guardado**
  (`components/agent-draft/`): las instrucciones y los ajustes dicen qué tienen
  pendiente y la barra lo guarda en una escritura, con una nota opcional. El 412
  abre el aviso «Hay cambios más nuevos de …» con los cambios de cada uno, lo
  que tocaron los dos y dos salidas: «Guardar los míos encima» o «Quedarme con
  los suyos». El historial enseña autor, fecha, nota y versión de partida. Su
  e2e corre aparte: `pnpm exec playwright test -c e2e/agent-draft.config.ts`.

## Módulos del partner (spec 032)

Auphere decide desde el panel qué secciones tiene la consola de cada partner
(`partners.console_modules`). La consola los recibe en el principal y en `/console/me` y
los aplica en tres sitios: el menú (`navForPartner`: módulo **y** permiso del rol), la
paleta ⌘K y una puerta por sección (`requirePartnerModule` en el `layout.tsx` de cada
carpeta y en el Panel), que lleva al primer módulo asignado. El Companion es el módulo
`companion`. Un partner sin ninguna sección de menú se lee como consola apagada.

## La consola nueva, la de todos los partners (spec 047)

La fábrica de agentes (`specs/047-la-fabrica-de-agentes/`) llegó detrás de una
**activación por partner** (research D38). Desde el 2026-10-29 es la consola de
**todos**: la migración `0204_console_v2_for_all` la encendió para cada partner que
seguía en la de antes (con la audiencia de sus números escrita como lo hacía la
activación), y un partner nuevo nace con ella
(`services/console_v2.born_on_new_console`, en el alta, en el panel y en los
scripts de semilla). El interruptor del panel y sus rutas
(`/admin/partners/{id}/console-v2…`) ya no existen; lo que el panel enciende o
apaga por partner son los módulos (spec 032).

`partners.console_v2_enabled_at` sigue siendo la marca que leen la API y el
worker. `/console/me` devuelve `console_version` (`v1` | `v2`) y
`app/(console)/layout.tsx` elige el marco:
- **`v1`** (`components/shell/console-shell-v1.tsx`): el de antes. Solo lo ve un
  partner sin la marca (en producción ya no hay ninguno) o cuando `/console/me`
  falla.
- **`v2`** (`console-shell-v2.tsx`): barra lateral plegable a 64 px con tooltip y
  solo el grupo «Operar» (`nav-v2.ts`; plegada, la etiqueta solo la leen los
  lectores de pantalla). Equipo, Facturación y API («Cuenta») viven en el menú del
  perfil; el tema es un interruptor junto a la campana (`theme-switch.tsx`); un
  botón redondo de vidrio vuelve a la miga anterior (`shell-back-button.tsx`, un
  enlace, no el historial), junto al título de cada página que tiene a dónde volver
  (`PageHeader back`, la cabecera del cliente y las del agente); el botón del menú
  queda a plomo con el borde del lienzo, y al plegar solo se desliza el ancho: los
  iconos no se mueven y los textos se desvanecen (Andrés, 2026-10-28). `nav.ts` no cambia: la app de escritorio compara con él.
  Migas con el último elemento sin enlace
  (`crumbs-v2.ts`), la campana con los 5 últimos avisos, «Marcar todo como leído»
  y «Ver todas», el menú de perfil con el tema (que se queda en móvil) y cada
  pantalla con su URL en el historial. Las rutas de la v2 viven en `routes-v2.ts`.

**⌘K** busca en `GET /console/search?q=` a través de `app/api/search/route.ts`:
el principal se resuelve en el servidor y cada llamada lleva su token de 60 s, como
el puente del Companion. Devuelve clientes y agentes (con su cliente; los agentes
se leen con el contexto de cada cliente puesto, nunca sin RLS) y **todas** las
pantallas y acciones que la persona puede hacer, como claves: la consola pone el
texto (`i18n/lanes/shell.ts`, `shell.search.screen.*` y `shell.search.action.*`) y
filtra por él. Lo que no se puede hacer no aparece (§V).

**Trabajos largos.** Lo que tarda responde `202 {job_id}` y la consola consulta
`GET /console/jobs/{job_id}` con espera creciente. La ruta solo recibe el id: la
función SQL `job_tenant` (SECURITY DEFINER) devuelve el cliente del trabajo, la API
comprueba que es del partner y solo entonces abre la transacción con ese cliente.
Un trabajo de otro partner es el mismo 404 opaco que uno inexistente. Nunca sale
el coste (C9), y un fallo viaja como `error_code`. Un trabajo vivo sin latido
caduca al leerlo (`timeout`). Los ejecuta `jobs-consumer` en el worker (familia
runner, stream `nexus:jobs`; research D43), cada uno con la clave del partner del
cliente atada al proxy de modelos (`modelos-y-router.md` §El transporte).

**Sistema visual** (`@nexus/ui`, spec 047 T005, para las dos consolas, el panel,
la app de escritorio y la móvil): el primario es el verde profundo, con contraste
≥ 4,5:1 con su texto; pestañas en píldora; diálogos con trampa y devolución del
foco; avisos que no se van con el foco o el ratón encima; `money` en `es-ES`, y la
gráfica de bloques (`block-chart.tsx`) con su tabla equivalente. El vidrio solo
existe en la capa flotante y se apaga con `prefers-reduced-transparency`.

Desde el 2026-10-28 los valores son los del prototipo aprobado «Consola de partners
v2» (análisis completo en `specs/047-la-fabrica-de-agentes/evidence/prototipo/`):
- **Vidrio** (utilidad `glass`): 60 % de opacidad (62 en oscuro), desenfoque de
  22 px, el canto de luz arriba (`--glass-edge`) y la sombra que lo despega
  (`--glass-shadow`), sumadas a `ring-1` por las variables de Tailwind. Lo llevan la
  barra de pestañas fija, la barra de guardar flotante, los menús, los avisos y el
  control segmentado (`segmented-control.tsx`).
- **Radios**: controles a 8 px (`rounded-md`), tarjetas, menús y avisos a 12
  (`rounded-lg`), lienzo y diálogos a 16 (`rounded-xl`). El lint `radius-enum`
  admite `lg` y `xl`.
- **Título de página**: `text-display` (40 px, −0,03 em), con `PageHeader
  size="display"` y sin antetítulo en todas las páginas del partner.
- **Botones y campos**: 36 px (`sm` 32), radio 8.
- **Insignias**: el fondo suave del tono y el texto en su color legible
  (`status-*-text`), sin borde. Con un icono dentro (el globo de «Leído de la web»),
  el icono va en línea con el texto y hace de punto.
- **Menú lateral**: 256 px, 15 px, el activo en verde suave (`--sidebar-accent`) y
  el gris al pasar; grupos «Operar» y «Cuenta» de 11 px.
- **Avisos** abajo en el centro, en vidrio; el tono lo dice su icono.
- **Chat de prueba**: `--chat-bg` y `--bubble-out`.
- **Movimiento**: los diálogos suben y crecen un poco al abrirse (`slide-in-from-bottom-2`,
  `zoom-in-98`) y no se mueven con «reducir movimiento».

El e2e del marco nuevo corre aparte, contra una API simulada del contrato:
`pnpm exec playwright test -c e2e/shell.config.ts`.

**El alta en tres datos** (spec 047, historias 3 y 4). Con la consola nueva,
«Nuevo cliente» es un modal (`components/clients/client-modal.tsx`; `clients/new`
lleva a `/clients?new=1`). Pide nombre (1–60), nicho (2–80) e información
(≤ 2.000), y `POST /console/clients` con ese cuerpo (`ClientNewIn`) **no crea ningún
agente ni aplica la plantilla por defecto**: el cliente nace `active`, con su ficha
(`business_profiles`) y su auditoría, en una sola transacción. El cuerpo de antes
(`external_client_ref`…) sigue igual para los partners sin activar y para la API de
partners (`docs/partner-integration.md`). La zona, el país y las monedas se deducen
por este orden: dominio y prefijo, país del partner, navegador. «Más ajustes» solo
enseña la zona horaria y la moneda (EUR o USD); el país, la moneda de los precios y
«Solo UE» se deducen y se mandan sin pedirlos. Los ejemplos de los campos son
generales, sin aludir a ningún nicho. `POST /console/clients/link-detection` saca de la información las
webs y las redes (un `@` suelto se propone como Instagram), y
`GET /console/clients/niche-suggestions` sugiere nichos de los 6 grupos y de los más
usados, sin sustituir lo escrito.

**La lectura de la web** va en segundo plano (`client_read`, un trabajo de
`jobs-consumer`, `services/business/reader.py`): hasta 25 páginas del mismo
dominio, con `robots.txt`, solo direcciones públicas y las guardas de
`knowledge_indexer.py`; sin web, los perfiles públicos de redes. Lo leído es dato y
nunca instrucción (§III). Lo que no choca se aplica marcado «Leído de la web ·
revísalo» (`review=pending`); lo que contradice algo escrito por una persona queda
como sugerencia (`business_suggestions`). Si falla, dice por qué y el cliente sigue
usable. Se mide en «Construcción y pruebas» (`source=reader`, `task=read_source`).
La consola la sigue con `client-read-card.tsx` (`GET …/business/read`); quien la
lanzó recibe `client.read.done` o `client.read.failed` en la campana.

**La tarjeta de lectura en el Panel del cliente** (enmienda del 2026-10-29, T210,
requisitos 59.4 y 59.7): arriba a la izquierda, mientras se lee («Completando la
ficha», con las páginas leídas) y al terminar («Lo que leímos»): qué se encontró,
qué otras redes se leyeron, si había datos estructurados, cuántos datos quedan por
revisar en Negocio (lo aplicado «revísalo» más lo propuesto) con «Revisar», y una
frase por red que no se leyó. Una red que no deja leer perfiles sin cuenta
(`networks[].status = blocked_by_network`) lo dice («Instagram no deja leer
perfiles sin cuenta.») sin tono de aviso: no es un fallo de la lectura. Una que
falló dice por qué, con el vocabulario de siempre. Las redes se leen de
`networks` de `GET …/business/read` si traen su estado, si no del `result` del
trabajo, y de una lectura de antes, de sus `sources` (`client-read-model.ts`,
`networkLines`). Sin lectura, no hay tarjeta.

**Agentes y canales.** Cómo nace, se prueba, se publica y vive un agente está en
`docs/agentes.md`; los números, su audiencia, la coexistencia y el enlace del
dueño, en `docs/canales.md`; el dinero (bolsas, Consumo por partidas, la partida
«Construcción y pruebas»), en `docs/billing.md`.

**El Panel** (`GET /console/home`, bloque `panel`, solo con la consola nueva;
`services/partner_panel.py`): el gasto del mes con los 3 clientes que más gastan,
el resto y las demás partidas (la misma función que Consumo, así que cuadran), los
clientes atendiendo sobre los no archivados, el saldo disponible y lo que hay en
bolsas, las conversaciones por día («Resueltas sin persona» y «Pasadas a una
persona», contadas por estado, nunca por texto) y «Necesita tu atención»: la
regla única de `services/attention.py`, de más a menos grave, cada fila con su
arreglo (`assign_balance` o `request_balance` según quién mire, `fix_channel`,
`reconnect`, `raise_cap`, `connect_channel`, `new_agent`). Cada bloque dice su
periodo. La composición es la del prototipo aprobado (`components/home/partner-panel.tsx`):
«Hola, {nombre}» con el partner y el día (`today-date.tsx`, en el reloj del
navegador) y «Nuevo cliente»; a la izquierda el gasto del mes con su barra por
cliente; a la derecha tres cifras (conversaciones de la semana, clientes atendiendo
y saldo disponible con lo asignado a clientes) y las conversaciones por día; abajo,
«Necesita tu atención» con «N de M clientes sin problemas», su arreglo y un ⋯ por
fila. El título grande de la consola nueva es `PageHeader size="display"`.

**La pantalla del agente** (`components/builder/agent-builder.tsx`), como el
prototipo: el agente es el título de la página, con su estado y «de {cliente}» (en
las páginas de un agente, del nuevo y de sus canales la ficha del cliente deja su
cabecera y solo pone su nombre en las migas). Debajo, cuatro pestañas en vidrio:
Rendimiento (con Mejoras), Configurar y probar (cinco filas, «Qué hace», «Cómo
habla», «Qué sabe», «Qué puede hacer» y «Cuándo pasa a una persona», que reúnen los
nueve bloques del AgentSpec, cada una con su lápiz, y «Qué sabe» abre el
conocimiento propio del agente; debajo, «Más ajustes» plegado con la recepción,
las pruebas, la revisión, el historial, Avanzado, el copiloto y las propuestas; a la derecha, fija, la tarjeta de pruebas
y el chat de prueba), Canales y Conectores. Rendimiento solo existe cuando el agente
tiene una versión guardada (63.2). Un agente «Listo · sin canal» abre en Canales,
uno publicado en Rendimiento y uno sin publicar en Configurar y probar. «Guardar»
flota abajo, en vidrio. Las pestañas ocultas siguen montadas: cambiar de pestaña no
pierde el chat de prueba ni un editor abierto.

**La configuración de un canal, dentro del agente** (spec 047, requisito 63.1, hueco
H5; `channel-page.tsx`): se abre en la pestaña Canales con `?canal={id}`
(`channelHref`), con la cabecera y las pestañas del agente arriba; la ruta vieja
`agents/{id}/channels/{channelId}` redirige ahí (308) y, si el número es de otro
agente, la pantalla va al suyo. A la izquierda, el índice («A quién responde»,
«Excepciones» solo con «A todos», «Escalado a personas»); la cabecera del canal con
su logo y «WhatsApp · {método} · canal de {agente}» (`ChannelPage.method`:
`coexistence`, `cloud_api` o `null` si no se sabe, y entonces no se dice; D64); dos modos, «Solo mi equipo» (con sus números
de prueba) y «A todos»; el escalado en filas de una línea; las comprobaciones; y
«Mensaje de espera» e «Historial» plegados en «Más ajustes». La barra de vidrio de
un canal sin configurar ofrece «Activar solo para mi equipo», «Activar para todos»
(los dos guardan con `PUT …/channels/{id}/config` y el modo elegido) y «Decidir
luego» (vuelve a la lista sin guardar); configurado, «Guardar» y «Descartar» cuando
hay cambios, y «Deshacer» durante 10 minutos. Cambiar de pestaña la cierra y quita
`?canal=`. La miga es «Clientes › {cliente} › {agente} › Canal {número}», y el agente
vuelve a Canales. Si el número pedido no se puede leer (otro cliente, 404, la API no
responde), la pantalla abre Canales con la lista y lo dice (`channelUnavailable`).
Lo que recibe el foco deja sitio bajo la barra de vidrio (`scroll-mb-48`): con el
teclado ningún campo queda tapado por ella (WCAG 2.4.11).

**Negocio** (`components/business/sections/*`), como el prototipo: cada sección se
lee primero y se edita con «Editar» (o «Añadir sede», «Añadir servicio») en su
cabecera, una sola a la vez (`SectionEditProvider`, `useSectionEdit`). La tarjeta
solo marca lo que pide algo: «Leído de la web · revísalo» con «Es correcto»
(`confirmSectionAction`) y «Falta». El índice lleva un círculo por sección y la
nota de que lo heredan sus agentes. Ocho secciones: Datos básicos, Sedes, Horarios
(con las fechas especiales dentro), Servicios, Políticas, Preguntas frecuentes,
Documentos y webs (`BusinessSources`) y Redes sociales (`BusinessLinks`, con las
redes de `GET /business`). La consola lite usa las mismas secciones.

Con la enmienda del 2026-10-29 (T209; requisitos 57.5, 60.4 y 60.5):
- **El sector**, en Datos básicos (`basics-section.tsx`): su etiqueta con «Con
  guía» (hay guía de Auphere) o «Generada» (se generó una para este cliente) y una
  línea que lo explica; «Identificando el sector…» mientras es `null`; nada si la
  API aún no manda el campo. Si el sistema propone otro contra uno fijado por una
  persona (la sugerencia con puntero `/business/sector`), sale al lado del valor
  con «Aceptar» y «Descartar». «Editar» lo corrige con un selector de los sectores
  con guía (`GET /console/sectors`) más «Otro», que pide la etiqueta (1–40); sin
  la lista, quedan el actual y «Otro». `422 sector_unknown` se dice en palabras.
- **Políticas** (`policies-section.tsx`): cancelación, pagos, señal y no
  presentarse, lo que ya entraba en el prompt de todos sus agentes; «Editar» las
  escribe las cuatro (`PUT …/policies`, que las sustituye).
- **Preguntas frecuentes** (`faqs-section.tsx`): las confirmadas, con «Editar» y
  «Quitar», y «Añadir pregunta»; debajo, «Por confirmar».
- **Lo sugerido** (`suggestion-card.tsx`, `proposals-model.ts`): cada propuesta
  pendiente de `GET /business` (`/policies/{clave}`, `/faqs/-`) va en su sección,
  marcada «Sugerido · confirma», con de dónde sale («Propuesto a partir de la
  ficha», «Leído de la web»…, sin nombrar al constructor) y «Aceptar», «Editar» y
  «Descartar» (`POST …/suggestions/{id}/decide`). Una pregunta guardada como
  sugerida (`suggested: true`) se acepta con `PATCH … {suggested: false}` y se
  descarta archivándola. Aceptar vuelve a leer la sección; descartar solo la quita.
  Si la ficha no cargó, cada sección enseña lo escrito y dice que lo sugerido no
  cargó. Quien solo lee lo ve sin botones.
- **Errores con salida** (T218): un 412 en Políticas o Preguntas frecuentes lleva
  «Recargar» en el aviso, que vuelve a leer la sección (Políticas enseña lo nuevo en
  el formulario; una pregunta conserva lo escrito) para guardar con la revisión de
  ahora. Mientras se decide la propuesta de sector, sus dos botones esperan.
- **Cargando** (`business/loading.tsx`): la misma rejilla que la página
  (`sections/layout.ts`, que comparten las dos), el índice de ocho secciones también
  en el móvil y las tarjetas con su radio; se anuncia («Cargando Negocio»).

**«Necesita tu atención»** (Panel): sin botones sueltos en la fila; el arreglo que
pide (asignar o pedir saldo, conectar o arreglar un canal…) es la primera opción
de su «⋯», y el saldo se asigna o se pide sin salir del Panel.

**La gráfica de bloques** (`block-chart.tsx`) tiene la forma del prototipo:
cuadros redondeados con aire (hasta 32 px con pocas columnas, 20 con un mes, 10 con
90 días), columnas repartidas a lo ancho, cinco marcas en el eje y «Hoy» en tinta;
con una semana o dos, cada columna ocupa su parte del ancho con bloques de 16 px de
alto (sin huecos grandes entre días); al pasar o enfocar, línea guía discontinua, la columna abierta más viva y las demás
atenuadas, y un aviso de vidrio al lado con el día, el total grande y el reparto.
Los colores no cambian: cada serie cumple 3:1 sobre el fondo (R47.10). Sigue siendo
una lista con flechas y una tabla para lectores de pantalla.

**Canales del agente** (`channel-picker.tsx`, `connect-whatsapp-dialog.tsx`): los
cuatro pasos y las tarjetas de canal del prototipo (WhatsApp se conecta; los demás,
«Próximamente» o «Pendiente»); WhatsApp abre «Conectar WhatsApp» con Coexistencia o
Cloud API y «Compartir un enlace»; «Conectar» usa el alta de siempre
(`runWhatsAppSignup`) y pasa el número a este agente. El logo de la app va donde se
ve un canal (`brand-logo.tsx`).

**El Panel del cliente** lleva Saldo, Este mes y Agentes que más consumen, y,
cuando hay una lectura, su tarjeta arriba a la izquierda (enmienda del
2026-10-29, 59.7; deja sin efecto lo del 2026-10-28 de seguirla solo en Negocio).
La pestaña Agentes va sin número, la campana
lleva su borde (32 px, como el buscador y el interruptor del tema) y, con el
lateral plegado, el nombre de cada entrada sale pegado a su icono.

**Un solo botón primario por vista** (Andrés, 2026-10-28): «Nuevo cliente» y
«Nuevo agente» están en la cabecera, y los vacíos no los repiten. En la lista de
clientes, la columna Estado dice solo el estado del cliente (lo de sus agentes
está en su columna), y el Panel del cliente no anuncia lo que falta en la ficha.
Las redes sociales se escriben con el usuario y la consola enseña el enlace que
saldrá (las mismas plantillas que `services/business/links.py`), con el logo de
cada app (`components/brand-logo.tsx`, de Simple Icons, como el panel).

**Pantallas del partner** alineadas con el prototipo el mismo día: la lista de
clientes (buscador que filtra al escribir, filtro en un selector, columna «Saldo»
con su barra, archivar sin confirmar y con «Deshacer»), el Panel del cliente (dos
columnas, la barra del saldo contra lo asignado, los agentes que más consumen),
el Panel del partner (cifras de 28 px y la semana frente a la anterior), la pestaña
«Configurar y probar» del agente (cinco filas, la tarjeta de pruebas y el chat de
prueba a la derecha, «Más ajustes» plegado con lo demás), Consumo, Auditoría, Guía
del partner, Teammate, Equipo, Facturación, API y Notificaciones.

**El constructor no se ve.** Trabaja por dentro (lee, propone y prepara el primer
borrador), sin nombre, botón ni tarjeta en la interfaz: Negocio ya no lleva
«Completar con el constructor» y los textos dicen «borrador» o «sugerido»
(`i18n/__tests__/words.test.ts` lo vigila). El rol del equipo «Constructor» sigue
con su nombre. Desde la enmienda del 2026-10-29 (60) el constructor del cliente
se lanza solo al terminar la lectura o al cambiar el sector: sus propuestas se
deciden en Políticas y Preguntas frecuentes, y los agentes que sugiere salen en la
pestaña Agentes. `client-builder-panel.tsx` sigue sin montar.

**Agentes sugeridos** (T210, requisito 60.6; `agent-cards.tsx`): detrás de los
agentes del cliente, los de `GET /console/clients/{ref}/suggested-agents` como
tarjetas «Sugerido» (borde discontinuo, nombre, para qué papel y la descripción),
con «Crear este agente», que abre «Nuevo agente» con `?name=&description=`
(`proposedAgentHref`; no crea nada), y «Descartar»
(`POST …/suggested-agents/{id}/dismiss`, `suggested-actions.ts`). Si la lista no
se puede leer, la pestaña se pinta sin ellas. Quien solo lee las ve sin botones.
El nombre accesible del enlace empieza por lo que se ve («Crear este agente:
{nombre}», WCAG 2.5.3), y un papel que la consola no conoce no se pinta.

**«Por qué falló», turno a turno** (T215, requisitos 58.4 y 61.6;
`test-conversation.tsx`): en la lista de pruebas y en la tarjeta de pruebas («Ver
la conversación»), lo comprobado y la conversación con el cliente simulado, con las
burbujas del chat de prueba (el cliente a la derecha, el agente a la izquierda y
«Lo que habría hecho: …») y por qué terminó (plan cumplido, despedida, paso a una
persona o 8 turnos). La conversación sale de `transcript`/`stop` de la prueba o, si
la API la manda por pasadas, de la primera que falló (`failedConversation`); sin
ella, solo lo comprobado. Las pruebas con `origin: "generated"` llevan «Generada», y
el grupo «Del sector» dice que Auphere no tiene guía para ese sector.

**Auditoría** (`GET /console/audit`): filtra por cliente (también archivados),
persona (`person`), categoría y periodo (`days=7|30|90|all`); cada fila dice quién
(`actor_kind`) y desde dónde (`origin`: `console`, `lite_web`, `app`, `admin`,
`api`, `system`), marca lo sensible (`sensitive`) y junta las filas seguidas con
la misma persona, acción, cliente y día (`more_like_this`; `group=false` las
separa). El vocabulario de las acciones de la 047 está en la migración 0197; la
0203 cambia «integración» por «conector» en sus frases, y la categoría
`integrations` se dice «Conectores».

**Notificaciones**: cada aviso lleva su enlace al arreglo (`href`, tabla `LINKS` de
`api/console/notifications.py`, según `events.md` §3). Los que van a un agente
abren su pantalla con `?tab=`, que `sectionForTab` (`builder-model.ts`) lleva a su
sección, y `tabOfSection` abre la pestaña que la tiene (un enlace `#agente-…` hace lo
mismo): `performance` a Rendimiento, `improvements` a Mejoras, `tests` a Pruebas,
`advanced` a Avanzado, `quality` a la línea de Avanzado que dice que el modelo lo
gestiona Auphere (`#agente-calidad`), `channels` a Canales e `integrations` a
Conectores (`#agente-conectores`). Cada tipo de aviso de la 047 tiene sus
palabras en `i18n/lanes/notices.ts` (`render.test.ts` comprueba que ninguno queda
«desconocido»); si el aviso trae el nombre del agente (`agent`), la variante
`.agent` lo nombra con quien lo hizo («Marta pausó Recepción»). Un cambio de la
ficha que deja en rojo pruebas de un agente publicado avisa con
`agent.tests.failing` (una vez por agente y día, desde el trabajo de pruebas del
worker). Los avisos que también ve el cliente enlazan, en su campana, a la lite
(`LITE_LINKS`).

**Rendimiento y Mejoras del agente** (spec 047, historias 31 y 32;
`components/builder/agent-performance.tsx` y `agent-improvements.tsx`, acciones
en `clients/[ref]/agents/improve-actions.ts`), como el prototipo (63.2, hueco H9):
arriba, en dos columnas (1,35fr / 1fr; una por debajo de 980 px), «Últimos 30 días»
de `GET …/agents/{id}/performance` con tres cifras —conversaciones, resueltas sin
persona (porcentaje, o «—» sin conversaciones) y consumido de la bolsa, con el tope
mensual del agente si lo tiene— y «Sugerencias de esta semana»: una fila por mejora
con su bombilla, lo que pasó y «Ver», que abre la propuesta con «Aceptar» y
«Descartar». Debajo, a todo el ancho, la gráfica de bloques (7, 30 y 90 días en su
píldora, con las flechas; el resumen de arriba sigue en 30) y, con
`conversations:read`, la lista de
`GET …/conversations` **solo con metadatos** (fecha, canal, duración, mensajes,
resultado, motivo del traspaso de `events.md` §2 y gasto), con «Ver más» por
cursor. Las sugerencias son las de la semana (a cuántas conversaciones y
clientes afectan, nunca cuáles) y las correcciones de comportamiento del negocio
(la lección y la paráfrasis, nunca el mensaje), cada una con su propuesta (el
diff y la prueba nueva). «Aceptar» dice en qué revisión queda el borrador y la
pantalla lo vuelve a leer; publicar sigue pasando por «Guardar». «Descartar» pide
el motivo (3–300). Sin `agents:write` no hay botones; cada parte falla sola.

**Recepción** (spec 047, historia 33; `components/builder/reception-section.tsx`):
la sección `reception` del AgentSpec en la pantalla del agente —marcarlo,
elegir a qué agentes vivos de este cliente deriva y cuándo derivar a cada uno
(1–300 caracteres, hasta 10)— se guarda en el borrador con la misma revisión que
los bloques; la API pone y quita la herramienta `reception.handoff`. La cabecera
del agente dice lo que dice la versión publicada (`is_reception`, también en la
tarjeta de `GET …/agents`) y, si el borrador lo cambia, «Recepción al publicar»
o «Deja de ser Recepción al publicar». Entre los destinos, los que también son
Recepción lo dicen.

**Conectores del agente** (spec 047, historia 21, T129;
`components/builder/agent-connectors.tsx`, acciones en
`clients/[ref]/agents/connector-actions.ts`): la sección lee al montar
`GET …/agents/{id}/integrations`. Como el prototipo (63.3, hueco H10): una sola
tarjeta con filas —logo, nombre con su categoría, una nota con qué hace, «lo
necesita una habilidad de este agente» y cómo se autoriza, y «Conectar» (el
principal si lo pide una habilidad) o «Conectado» con «Ajustes» y «Quitar»—, un
buscador sin etiqueta a la vista y el filtro segmentado con recuentos («Todos»,
«Conectados» y cada categoría). Primero lo que piden las habilidades y luego lo
conectado (62.5, `orderConnectors`). WhatsApp y TikTok no
salen: son canales (`provider_meta.channel_only`), como en el admin. «Conectar» pide el
permiso y llama a `POST …/connections`: si ya estaba autorizado, lo activa; si es
OAuth, abre la autorización y la API lo activa al terminar; si pide una clave
(`409 authorize_with_form`), se guarda con el alta de siempre y después
`PUT …/activations/{slug}`. El permiso y los ajustes del `settings_schema` del
catálogo se cambian dentro de «Ajustes» (no en la fila), con el enlace a su página;
«Quitar» pide confirmación y `DELETE` dice qué habilidades se quedan sin él.
«Conectar {X}» en la línea de una habilidad de «Qué puede hacer» o en el arreglo de
una prueba abre aquí mismo este diálogo, sin cambiar de pestaña (62.3, hueco H11);
al terminar, la línea dice «{X} · conectado» y la pantalla vuelve a leer el
borrador y sus pruebas. Si el conector no está en el catálogo del agente, se va a
la pestaña Conectores. Cada conexión
tiene su página en `/clients/{ref}/integrations/{connectionId}` (`?agent=` para
volver): cuenta, estado, última comprobación, agentes con su permiso y ajustes,
«Reconectar» y «Desconectar para todos», que primero lista lo afectado.

**Avanzado: el modelo lo gestiona Auphere** (spec 047, requisito 64, D55): mientras
no exista la gestión de modelos en el panel de operador, Avanzado no enseña
«Calidad» ni «Fijar un modelo»; dice en una línea que el modelo de este agente lo
gestiona Auphere (`#agente-calidad`, adonde siguen llegando los avisos
`model.retirement` y `model.price_change`). `agent-model-quality.tsx` y sus pruebas
se quedan, sin montar, para cuando vuelva (64.4). La API lo sostiene: un cambio de
política pedido desde la consola (`PATCH …/draft` con otra `model_policy`, `POST
…/quality/check`) responde `409 model_policy_managed` (D64).

**Solo lo que tenemos** (spec 047, enmienda del 2026-10-30, T228; requisitos 65.3,
65.4, 65.7, 65.8 y 65.9; contrato en `contracts/console-api.md` §11). Un agente
puede ser para cualquier cosa, pero solo con las herramientas que existen: la
consola no inventa ni promete lo que no tenemos.

- **«No tenemos herramienta para: …»** (`components/builder/missing-capabilities.tsx`,
  lógica pura en `missing-model.ts`). Sale de `missing_capabilities`, con la
  `label` de cada elemento, que llega en español y lista para ir detrás de esa
  frase. Llega en tres sitios:
  - el borrador (`AgentDraftOut` de `GET`, `PATCH` y `DELETE …/draft`, siempre
    presente): la pantalla del agente lo pinta encima de la tabla y lo actualiza
    con cada guardado y cada vez que vuelve a leer el borrador;
  - el trabajo `agent_draft` (`result.missing_capabilities`): «Nuevo agente» abre
    la pantalla del agente con `?job=` si trae algo, y la página lo usa solo si el
    borrador no trae el campo (una respuesta de antes); recién creado dicen lo
    mismo;
  - la respuesta del copiloto: debajo de su texto. El copiloto no propone esa parte.

  Siempre dice la alternativa del agente: «Si se lo piden, el agente pasa la
  conversación a una persona». Una promesa del texto (`kind: "action"`) dice «Lo
  promete su texto» y, a quien puede editar, «Quitar la promesa» abre el bloque al
  que apunta su `pointer`. Con la lista vacía no se enseña nada. Sus cinco estados:
  cargando (un esqueleto del tamaño de lo que había, anunciado; sin nada antes,
  nada), vacío, error (si no se pudo volver a leer el borrador, lo dice sin enseñar
  lo de antes, con «Reintentar» sin doble envío), parcial (sin `label`, se nombra
  por su clave) e ideal (una frase con una, una lista con varias).
- **«Conectar {X}» solo con conectores ofrecidos.** Reservas es un módulo y nunca
  se «conecta» (`NEVER_CONNECT` en `builder-model.ts`). Lo que la API dice que
  falta como conector o como módulo (`kind` `integration` o `module`) tampoco: ni en
  las habilidades de «Qué puede hacer» (ni «Conectar» ni «conectado»), ni en los
  arreglos de la revisión de la tarjeta de pruebas. `result.connect` y
  `connection_requests` ya solo traen conectores ofrecidos; el filtro es la red de
  la consola por si no.
- **Las tarjetas «Sugerido» sin papel obligatorio** (`suggested-agents.ts`,
  `suggestedRole`). `role` es opcional: `null` es lo normal, puede no venir y un
  valor que la consola no conoce cuenta como `null`. Sin papel, la tarjeta sale
  entera y sin línea de papel. La consola no decide nada con él.
- **La revisión y la puerta.** `promises_without_tool` llega como bloqueante con
  `fix {kind: "edit", pointer}`: «Arreglar en el borrador» lleva al texto que
  promete, en la revisión, en la tarjeta de pruebas y en la hoja de «Por qué no se
  guardó» (si el bloqueante trae `pointer`). `no_applicable_tests` en `gate.hard`
  se dice con las palabras de la consola («Este agente no tiene ninguna prueba que
  le aplique. Añade una antes de guardar.») y «Añadir una prueba» cierra la hoja,
  abre «Más ajustes» y la lista de pruebas con su formulario abierto y el foco en
  su primer campo. En la lista, un agente estructurado sin ninguna prueba que le
  aplique lo dice encima de «Añadir una prueba»; uno de antes (`instructions`) no,
  porque la puerta no se lo pide.
- **Las pruebas del sector que no aplican** llegan ya «No aplica», con su razón.
  Se ven como cualquier otra «No aplica» (la razón sin repetir el «No aplica» con
  el que puede llegar, `naReason`) y se reactivan como hoy, con «Vuelve a aplicar»,
  que ya no se pulsa dos veces y, si falla, lo dice en su fila.
- **Los errores, en palabras.**
  - `facts_unavailable`: en «Nuevo agente», tanto si el trabajo falla como si
    «Desde una plantilla» responde 503, «No pudimos leer la ficha de {cliente}»,
    sin perder lo escrito, con «Reintentar» (repite lo que se intentó) y sin
    ofrecer «Desde una plantilla», que también la lee.
  - `integration_unknown` dentro de `spec_invalid.problems`: «{conector} no es un
    conector que tengamos para este cliente. Hay que quitar lo que lo pide para
    poder guardar.», con el conector leído del AgentSpec por su puntero.
  - `structured_agent` y `seed_template_retired`: `lib/action-error.ts` los dice
    con su frase en las pantallas de antes que aún usan esa función (la barra de
    guardar del borrador y el alta de agente con plantilla). La consola nueva no
    usa esas rutas.

**Equipo**: además de invitar en un modal (el rol por su descripción, el enlace
para copiar, las invitaciones pendientes), «Qué puede hacer cada rol»
(`components/team/roles-table.tsx`) sale del mismo mapa de permisos que la API
(`lib/permissions.ts`), así que no promete lo que un rol no puede hacer.

El e2e de estas pantallas y de las de la consola lite corre contra su API
simulada: `pnpm exec playwright test -c e2e/fabrica.config.ts` (proyectos `lite` y
`partner`), con la auditoría de la spec 047 (T162) en cada una: axe, 390 px, 200 %,
teclado, «Reducir transparencia y movimiento», sus estados y textos largos en
alemán (`e2e/fabrica-audit.ts`).

## Reglas que no se negocian

- **Ningún cuerpo lleva `partner_id` ni `tenant_id`**: salen del principal y del
  `ref`. Un cliente ajeno es el mismo 404 opaco que uno inexistente
  (`tests/isolation/test_console_scope.py`).
- **Toda acción de servidor comprueba su rol** con el permiso exacto que la API
  exige, y tiene su test permitido/denegado con el arnés `src/test/actions.ts`
  (una carpeta, un `__tests__/actions.test.ts`). La única sin `can()` es aceptar
  una invitación: todavía no hay principal.
- **Sin permiso, el control no existe** —no se muestra deshabilitado.
- **La pantalla no miente** (§V): un estado que la API no puede leer se pinta
  como error o ausencia, nunca como «todo bien» ni como «agotado».
- **Las acciones nuevas se auditan** con vocabulario sembrado
  (`console_audit_vocabulary`; migración de datos por spec) y sin secretos en
  `after_json` (`tests/unit/test_console_audit_vocab_016.py`).

## Cómo se comprueba

```bash
cd apps/console && pnpm typecheck && pnpm lint && pnpm test   # Node ≥ 22.12
cd apps/api && uv run pytest tests/isolation -q               # bloquea el merge
./scripts/verify.sh                                           # todo, antes de fusionar
```

## Lo que queda fuera (y dónde está)

- Rediseño por flujo (ficha en tres grupos, capacidades dinámicas, tema claro y
  oscuro): spec 017, KB `PLAN-ACCION-CONSOLA-2026-09-22.md` bloque D.
- WhatsApp solo se puede probar de punta a punta en staging con las claves de
  Meta; en local se prueba la ausencia diseñada.
