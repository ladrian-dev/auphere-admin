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
5. **Integraciones**: AgendaPro se **enlaza por su agenda pública**
   (`PUT …/integrations/agendapro/public-url`, solo `https` en `agendapro.com`);
   nunca se piden credenciales desde la consola. Un conector por clave de API
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

## La consola nueva, partner a partner (spec 047)

La fábrica de agentes (`specs/047-la-fabrica-de-agentes/`) llega detrás de una
**activación por partner** (research D38): `partners.console_v2_enabled_at` y
`_by`, que escribe Auphere (`services/console_v2.py`; auditoría
`partner.console_v2_enabled` / `_disabled`). `/console/me` devuelve
`console_version` (`v1` | `v2`) y `app/(console)/layout.tsx` elige el marco:
- **`v1`** (`components/shell/console-shell-v1.tsx`): el de hoy, sin cambios.
  Un partner sin activar no ve nada nuevo salvo el sistema visual.
- **`v2`** (`console-shell-v2.tsx`): barra lateral plegable a 64 px con tooltip y
  sin etiquetas de grupo (`nav-v2.ts`), migas con el último elemento sin enlace
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
runner, stream `nexus:jobs`; research D43).

**Sistema visual** (`@nexus/ui`, spec 047 T005, para las dos consolas, el panel,
la app de escritorio y la móvil): el primario es el verde profundo, con contraste
≥ 4,5:1 con su texto; pestañas en píldora; diálogos con trampa y devolución del
foco; avisos que no se van con el foco o el ratón encima; `money` en `es-ES`, y la
gráfica de bloques (`block-chart.tsx`) con su tabla equivalente. El vidrio solo
existe en la capa flotante y se apaga con `prefers-reduced-transparency`.

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
por este orden: dominio y prefijo, país del partner, navegador; se ven y se cambian
en «Más ajustes». `POST /console/clients/link-detection` saca de la información las
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
