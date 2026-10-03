# Investigación (Fase 0): la ficha de cliente y el consumo, por flujo

Todo lo que el plan decide sale de leer el código en `develop` (`5002c0a`, con
los Bloques A, B y C dentro). Formato: decisión · razón · alternativas.

## R1 · El sector del cliente

- **Decisión**: el sector es `agent_configs.seed_template_ref` de la versión
  activa (o del borrador si no hay activa), traducido a sector con la misma
  función `_vertical(name)` que ya usa `GET /console/seed-templates`
  (`api/console/seed_templates.py:148`). No se añade columna: la API expone
  `sector` en `ClientOut` y en el catálogo de capacidades, calculado.
- **Razón**: el dato ya existe por versión y es el que sembró el agente; una
  columna en `tenants` duplicaría una verdad que puede cambiar con el
  historial. Un agente escrito a mano tiene `seed_template_ref = NULL` →
  «sin sector», que la spec ya contempla (casos límite).
- **Alternativas**: columna `tenants.vertical` (duplicado); inferir por
  etiquetas de las herramientas activas (frágil).

## R2 · Capacidades: una vista sobre dos catálogos

- **Decisión**: endpoint nuevo `GET /console/clients/{ref}/capabilities`
  que une `GET …/tools` (herramientas del catálogo `tools`, con
  `capability_tags`) y `GET …/skills` (`skills_catalog.py`) en una lista de
  **capacidades** con `kind: tool | skill`, `function` (Citas, Pedidos,
  Mensajes, Escalado, Conocimiento, Otras), `sectors` (de las etiquetas que
  nombran un vertical), `business_name` y `description` en ES/EN, `recommended`
  (la plantilla del sector la enciende por defecto), `enabled`/`enabled_in_active`,
  `connector` y `effective_mode`. La función y los nombres de negocio salen de
  un **mapa mantenido en el repo** (`apps/api/src/nexus_api/api/console/capability_names.py`)
  indexado por nombre técnico, con fallback al nombre técnico humanizado y a la
  descripción del catálogo. El `PUT …/capabilities` escribe herramientas y
  habilidades en el borrador con la misma lógica que hoy (`ensure_draft`,
  lista blanca del agente, `runtime_skills`) y **un solo cambio por llamada**
  (R5.4: cada clic guarda).
- **Razón**: el partner no distingue tool de skill (decisión 3 del owner); las
  dos pantallas actuales ya calculan «en borrador / en activa» por separado y la
  vista unificada evita dos estados. El mapa en el repo es el lugar donde ya
  viven las traducciones de campos de conectores (spec 016 R7).
- **Alternativas**: componer en la consola con dos llamadas (dos estados de
  borrador, doble ida y vuelta por clic); columnas nuevas en `tools` para
  nombre de negocio (mezcla catálogo de runtime con copy).
- **«Requiere aprobación»**: el selector deja de ofrecer `needs_approval`
  (`TOOL_MODES` en la consola); el backend sigue aceptándolo por compatibilidad
  y la vista muestra `effective_mode` real.

## R3 · El borrador por pantalla y «Ver diferencias»

- **Decisión**: endpoint nuevo `GET /console/clients/{ref}/agent/draft-diff`
  que compara borrador y versión activa y devuelve secciones por pantalla:
  `settings` (identidad, tono, horario, idiomas, escalado, aviso de IA, modelo:
  campo → antes/después, calculado desde `policies` y el modelo vinculado),
  `capabilities` (activadas/desactivadas y cambios de modo),
  `knowledge` (documentos añadidos/quitados), `prompt` (el diff de texto que
  ya calcula `prompt-diff.tsx`, ahora servido). La barra `DraftBar` lee
  `has_draft` del `AgentBundleOut` que ya llega en el layout de la ficha y
  solo pide el diff al abrirse.
- **Razón**: las pantallas guardan en columnas distintas de la misma
  `AgentConfig` (`policies`, `tools`, `runtime_skills`, `system_prompt_rendered`);
  el servidor es el único que ve las dos versiones enteras. R3.2 pide las
  palabras de cada pantalla: el diff lleva claves i18n, no frases.
- **Alternativas**: diff solo del prompt (opción B, descartada por el owner);
  calcular en el cliente pidiendo dos versiones enteras (más tráfico, lógica
  duplicada).

## R4 · Estado de puesta en marcha y cupo en la cabecera y en la lista

- **Decisión**: `ClientHealthOut` ya trae `missing` y `ready`; se añade
  `setup: {agent, channel, quota, active}` como cuatro booleanos y
  `quota: {cap, remaining} | null` a `ClientOut`. En la lista,
  `ClientSummaryOut` gana `setup` y `quota` calculados **una vez por página**
  con la misma técnica que `out_of_quota` (spec 016 R2.1: `quota_state` leído
  en bloque), más `conversations_7d` por una consulta agrupada por tenant sobre
  `conversations.started_at >= now() - 7d`.
- **Razón**: la lista no puede hacer una transacción por fila; la técnica ya
  existe y está medida. El canal se cuenta con `customer_facing_channel()`
  (excluye el Playground), que es lo que R8.3 exige.
- **Alternativas**: pedir `health` por fila desde la consola (N llamadas).

## R5 · Consumo en créditos y equivalencias

- **Decisión**: `GET /console/wallet` gana `equivalence: {usd_per_credit,
  credits_per_message, basis: partner_30d | platform_default}`. `usd_per_credit`
  sale del precio de compra de crédito vigente (spec 005: 10 $ por millón de
  unidades, en `billing.py`); `credits_per_message` es la media del partner en
  los últimos 30 días (`usage_records` agrupados: créditos de `llm.*` entre
  `channel.message`), con el valor de referencia de la plataforma cuando no
  hay historial. La consola formatea «≈ X USD · ≈ Y mensajes» siempre como
  segunda línea. Las etiquetas humanas de medidores ya existen
  (`hu.usage.meter.*`); la tabla deja de mostrar el nombre crudo.
- **Razón**: la unidad interna no cambia (constitución: todo lo que gasta se
  mide igual); solo se nombra y se convierte. La media propia es más honesta
  que una cifra fija, y el `basis` permite decir «estimación general».
- **Alternativas**: conversión fija en la consola (miente cuando cambia el
  precio); mostrar USD como cifra principal (decisión 4: créditos).
- **Mover cupo y editar tope en un diálogo**: mismos endpoints de la 016
  (`PUT …/allocation`, `POST /wallet/allocations/move`); solo cambia la
  pantalla. Alertas: `GET/PUT /console/usage/alerts` se consumen desde el
  panel plegable de Saldo; la ruta `/usage/alerts` se mantiene y redirige a
  `/usage#alerts` para no romper enlaces (R12.5).

## R6 · Navegación de la ficha y filtro por rol

- **Decisión**: bloque nuevo `NavTabs` en `@nexus/ui` (`{groups: {label,
  items: {href, label, exact?}[]}[]}`), con `aria-current`, grupos con nombre
  y un modo compacto (`NativeSelect` con `optgroup`) por debajo de `md`. El
  filtro por rol lo hace `client-tabs.tsx` con el mapa `PERMISSIONS` que ya
  existe: Agente/Ajustes/Capacidades/Conocimiento ← `agents:read`
  (+`knowledge:read`), Canales ← `channels:read`, Integraciones ←
  `agents:read`, Puesto de trabajo ← `workstation:read`, Resumen ←
  `clients:read`, Conversaciones ← `conversations:read`, Playground ←
  `playground:run`. Escritura oculta con `can()` como hoy.
- **Razón**: no hay permisos nuevos (supuesto de la spec); el mapa ya está
  probado contra la API (`permissions.test.ts`).
- **Alternativas**: `Tabs` de Base UI (no son enlaces; rompe la URL por pestaña).

## R7 · Prototipos antes de cada iteración

- **Decisión**: cada iteración empieza con una story de prototipo en
  `packages/ui/src/stories/prototypes/*.stories.tsx` montada con los bloques
  del DS y copy real en español, revisada en Storybook local (Node 24) y, si el
  owner lo prefiere, publicada como página estática. La aprobación se anota en
  `specs/017/evidence/iteracion-N.md` con la captura.
- **Razón**: R12.4; Storybook ya tiene el addon de accesibilidad en modo error,
  así que el prototipo pasa axe antes que el código.
- **Alternativas**: maquetas en Figma (otra herramienta, sin tokens reales).

## R8 · Selectores de zona horaria e idioma con nombres

- **Decisión**: `Intl.supportedValuesOf("timeZone")` y `Intl.DisplayNames`
  (idiomas) del navegador, sin dependencia nueva; la lista de zonas se agrupa
  por región y se busca por nombre de ciudad; el valor guardado sigue siendo
  el identificador IANA / el código ISO. Fallback: si el navegador no soporta
  `supportedValuesOf`, la lista corta que ya usa el wizard (`wizardTimezoneOptions`).
- **Razón**: cero dependencias (constitución §VIII), datos siempre al día.

## R9 · Glosario y ayuda

- **Decisión**: página `/ayuda` (Next, misma cáscara) que renderiza un
  glosario desde `apps/console/src/i18n/lanes/glossary.ts`
  (`glossary.<term>.title/body`), y `HelpHint` en cada término apunta a
  `/ayuda#<term>`. Sin CMS.
- **Razón**: el glosario es copy del producto, versionado con el código.

## R10 · Playground

- **Decisión**: hilo sin nombre → título automático «Conversación del {fecha}»
  en la API al crear (`schemas_playground.py:27` deja de usar «Untitled»); el
  estado `error` con causa ya existe desde el Bloque A (`playground.inspector.status.error`);
  la spec solo exige que se conserve y que el presupuesto ocupe una línea
  (`BudgetBar` con `Meter size="sm"`).

## R11 · Auditoría por categoría

- **Decisión**: `GET /console/audit` acepta `category` (la columna ya existe
  en el vocabulario, `audit.py:55`) y `GET /console/audit/vocabulary` devuelve
  las categorías con su etiqueta ES/EN. Títulos de negocio: ya vienen del
  vocabulario; lo que falta es que la consola los use en Notificaciones
  (`notifications-list.tsx` muestra `kind` crudo en dos casos).

## R12 · Sin dependencias nuevas

- Ninguna librería nueva en `apps/console`, `apps/api` ni `packages/ui`. Se
  verifica con `pnpm-lock.yaml` y `uv.lock` sin cambios al cerrar cada
  iteración.
