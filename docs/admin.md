# El panel de operador (`apps/admin`)

Spec viva del panel interno de Auphere. Se actualiza en el mismo commit que cambia lo
que describe. Origen: [spec 031](../specs/031-el-panel-se-ordena/spec.md).

## Qué es

El panel con el que el equipo de Auphere opera la plataforma: partners, clientes,
altas, tickets, conectores, canales propios, Playground QA y estado de la instancia.
Solo lo usan operadores; la identidad vive en la API (`/admin/auth/*`, ADR-034) y el
panel no tiene base de datos.

## Sistema de diseño

Desde la spec 031 el panel usa **`@nexus/ui`** como la consola de partners:

- Instala desde el workspace raíz (un solo `pnpm-lock.yaml`).
- `src/app/globals.css` solo importa `@nexus/ui/tokens.css`. No hay tokens propios.
- Tipografía Inter (`--font-inter`), tema claro/oscuro/sistema desde el menú del usuario.
- Lint `@nexus/ui/eslint` con `--max-warnings 0`: sin colores crudos, sin la paleta de
  Tailwind, espaciado en múltiplos de 4 px y radios `none | sm | md | full`.
- **Vercel**: el proyecto del panel necesita Root Directory `apps/admin` con «Include
  source files outside of the Root Directory» activado, como la consola.

## Navegación

Ordenada como el super admin de Chatwoot (`src/components/shell/nav.ts`):

| Grupo | Vistas |
|---|---|
| — | Panel (`/`) |
| Gestionar | Partners · Clientes (`/tenants`) · Consumo (`/usage`) · Altas · Tickets (con contador de abiertos) |
| Plataforma | Canales (`/channels`) · Conectores (`/connectors`) · Números de Auphere (`/auphere/channels`) · Playground QA (`/qa`) · Modelos (`/models`) · Router (`/router`) · Certificaciones (`/certifications`) · Constructor (`/builder`) |
| Instancia | Estado (`/status`) |

⌘K abre una paleta que busca vistas, partners, clientes y tickets abiertos.

Las migas viven en la barra superior (`components/shell/crumbs.ts`) y dicen el recorrido
completo: «Clientes › Volumen 03 › Canales › WhatsApp». Las páginas no las repiten ni
ponen una etiqueta encima del título. El nombre de cada registro lo anuncia su página con
`<CrumbName>`.

## Panel (`/`)

Lee `GET /admin/overview`: partners y clientes activos, saldo disponible total de los
partners (cada uno leído con su GUC), tickets abiertos, altas pendientes y clientes sin
tope. «Necesita tu atención» enlaza cada caso. Una sección ilegible se nombra en
`unreadable` y la pantalla se pinta parcial.

## Ficha de partner (`/partners/{id}`)

Cabecera con estado, consola, clientes, personas, saldo y alta. Pestañas:

| Pestaña | Contenido |
|---|---|
| Resumen | Nombre, correo de contacto y de facturación (editables y auditados); qué tiene encendido |
| Clientes | Uso de 30 días por cliente y mapeos `external_client_ref` → cliente, enlazados |
| Equipo | Personas (`GET /admin/partners/{id}/members`) e invitaciones pendientes |
| Módulos | Consola encendida y qué secciones y servicios tiene (spec 032): rejilla Operar · Cuenta · Asistente; el Companion se enciende aquí |
| Facturas | Saldo recargado, pool semanal y asignado en US$; recarga en dólares con confirmación e idempotencia; «¿cuadra el libro?»; movimientos con tipo (spec 033); tarjeta, modo de cobro, cobros y la línea de crédito del pospago (spec 041); recibos |
| Configuración | Límites (broadcast, rate limits, blueprint), modelos, claves API e impersonación |
| Consola nueva | Ensayo, activación y vuelta atrás de la consola de la fábrica, con el historial de informes (spec 047, [abajo](#palancas-del-partner-y-del-cliente-spec-047)) |
| Tope y moneda | El tope mensual de «Construcción y pruebas», los «Pedir ampliación» y la moneda de la cuenta (spec 047, [abajo](#palancas-del-partner-y-del-cliente-spec-047)) |
| Conocimiento · Auditoría | Sin cambios |

Grupos: Observar (Resumen, Clientes, Auditoría), Configurar (Módulos, Configuración,
Conocimiento, Consola nueva) y Cuenta (Equipo, Facturas, Tope y moneda).

Las rutas antiguas (`keys`, `tenants`, `usage`, `wallet`, `receipts`, `models`)
redirigen a la pestaña que las contiene. `limits` redirigía a Configuración hasta la
spec 047; ahora es Tope y moneda, y enlaza a Configuración para lo de antes.

## Consumo (`/usage`, spec 038)

Lo que gastan todos los partners y sus clientes, por periodo (este mes, 7, 30 o 90 días).
Lee `GET /admin/usage`.

- **Cifras.** Hay cuatro:
  - gasto de los clientes, a precio de venta y del libro de cada partner;
  - coste interno, lo que el modelo le costó a Auphere, incluido el Playground;
  - margen;
  - mensajes, con las conversaciones y los clientes activos.
- **Gráfico.** Gasto por día.
- **Tablas.** Por partner (gasto, fuera de clientes, coste interno, mensajes, saldo disponible) y por cliente (gasto, coste interno, mensajes, conversaciones). Cada fila abre su ficha.
- **Clientes directos.** Los de Auphere no tienen saldo de partner: salen «Sin saldo» y solo cuentan su coste interno.

Consumo también enseña la **ganancia** (spec 039): venta, coste del modelo de esos mismos turnos (`usage_records`), ganancia, margen y «se cobra sobre el coste» frente a la tarifa fijada (2,2×). Las pruebas del Playground van aparte y solo restan de la ganancia neta.

## Conectar WhatsApp desde el dispositivo del dueño (spec 040)

En el paso «Conectar WhatsApp» del asistente, la primera opción es **enviar un enlace al dueño** del negocio.
- Lo abre en su teléfono o su computadora, donde ya tiene su cuenta de Meta, y conecta él mismo el número (coexistencia o Cloud API).
- El enlace sirve una vez, caduca a los 7 días y se puede anular desde Canales, en el Admin y en la consola del partner.
- Hay uno vivo por cliente: crear otro anula el anterior.
- La página del dueño vive en la consola. El enlace (`/connect/whatsapp/{token}`) pasa el token a una cookie httpOnly y redirige a `/connect/whatsapp`, así que el token no queda en la dirección, el historial ni el `Referer`.

## Lista de clientes (`/tenants`, spec 036)

- **Vistas en pestañas con contador.** Son Todos, Necesitan atención, Activos, En pausa y Archivados. «Todos» no incluye los archivados.
- **Necesita atención** el cliente con un canal con problemas, un conector por reconectar, sin canal, con el agente sin publicar o a medio montar. El motivo sale en palabras en la columna Estado.
- **Columnas.** Son Cliente (con su partner), Canal (logo y número), Agente, Actividad y Estado. La Mensualidad solo aparece si algún cliente tiene plan mensual.
- **Orden.** Por defecto va primero lo urgente; también se ordena por actividad o por nombre. Búsqueda, vista, orden y filtros viven en la dirección.
- **Datos.** Salen de `GET /admin/tenants-health`, que lee cada cliente con su GUC.

## Ficha de cliente (`/tenants/{id}`)

- **Cabecera.** Lleva nombre con su estado, una línea de contexto (partner, plan, mercado, zona), «Probar agente», Acciones y cuatro hechos enlazados: canal, agente, última conversación y esta semana.
- **Pestañas.** Son el mismo `NavTabs` que la ficha del cliente en la consola de Partners, con el rótulo de cada grupo (spec 037):
  - Observar: Resumen, Conversaciones, Playground, Auditoría, Aislamiento.
  - Configurar: Agente, Habilidades, Acceso, Facturación. En Acceso, el módulo
    Reservas se activa con su modo (Servicios o Aforo con su tipo de negocio);
    cambiar de modo con reservas futuras pide «Cancelarlas y cambiar», y las
    versiones del agente que la activación prepara se promueven en Agente
    ([reservas.md](reservas.md#activarlo-panel-de-operador)).
  - Conectar: Canales, Conectores, Canal del dueño.

  Canales lleva un punto si ningún canal atiende o alguno tiene problemas. La ficha del partner usa el mismo componente con Observar, Configurar y Cuenta.
- **Agente.** Como en la consola: «Nuevo borrador» a partir de la versión activa (solo el prompt) y una tarjeta por versión con «⋯» para publicar, revertir o ver el prompt. Debajo van las capacidades del runtime y las evaluaciones. Spec 047: cada agente tiene un solo borrador, y guardar desde aquí escribe **en** él. Lo que el operador deja como está en la versión activa conserva lo que el borrador ya tenía, así que editar desde aquí no deshace lo que el partner dejó pendiente.
- **Habilidades.** El catálogo de la consola, con un interruptor por habilidad que guarda en el borrador. Se sirve en `GET/PUT /admin/tenants/{id}/capabilities`, con el mismo código que la consola y la auditoría firmada por el operador.
- **Playground.** El de `/qa/{cliente}/chat`, dentro de la ficha. «Probar agente» lleva aquí.
- **Resumen.** A dos columnas. A la izquierda va lo que falta para operar, solo lo pendiente y con lo hecho plegado; con todo hecho es una línea. Debajo, las conversaciones recientes. A la derecha, los datos del cliente, la **restricción soberana** (spec 047, [abajo](#palancas-del-partner-y-del-cliente-spec-047)) y las pruebas del agente.
- **Conversaciones.** Nombra al contacto por su nombre o número y dice quién responde. El control es un botón «Tomar control» / «Devolver», que no aparece en las conversaciones resueltas.

Los logos de canales y conectores son las marcas de cada app (Simple Icons, CC0) sobre su
color, en `components/brand/brand-marks.ts`. Lo que no tiene marca usa la imagen del
catálogo o sus iniciales.

## Canales y Conectores (spec 035)

Separados como las Bandejas y las Integraciones de Chatwoot.

- **Canales del cliente** (`/tenants/{id}/channels`): una fila por canal con
  «Configurar». «Añadir canal» abre un asistente de cuatro pasos: Elegir canal ·
  Conectar · Asignar agente · ¡Listo!. La ficha del canal tiene Ajustes (papel del número
  y si el agente responde), Agente, Plantillas (solo WhatsApp) y Salud (estado, envío de
  prueba, pausar o desconectar la conexión).
- **Catálogo de canales** (`GET /admin/channel-catalog`): WhatsApp, TikTok, Instagram,
  Telegram, X y Threads con su disponibilidad. Lo que no es `available` ni `beta` se
  enseña y no se puede iniciar (constitución §V 1.1.0; desde la 1.2.0, también en el
  catálogo de canales de la consola de partners). En `/channels` cada canal que funciona
  dice cuántos números lo usan, y cada «Pendiente» o «Próximamente» lleva su insignia y
  el porqué (`note`) (`channels/catalog-grid.tsx`, spec 047 T172). El catálogo de
  integraciones (`/connectors`) todavía no tiene esos estados: un conector es
  `available`, `beta` o `deprecated`. La ficha de cada conector (`/connectors/{slug}`)
  enseña los **ajustes que pide** al activarlo, leídos de su `settings_schema` (JSON
  Schema): cada ajuste con su tipo, si es obligatorio y sus reglas (URL, empieza por
  `https://`, de 0 a 23…), con los grupos aplanados (`reminders.hour_local`).
- **Conectores del cliente** (`/tenants/{id}/connectors`): rejilla con buscador, categoría
  y estado; sin WhatsApp ni TikTok, que son canales. La ficha de cada conector tiene sus
  acciones y el editor de permisos por herramienta: por defecto, siempre, pide
  aprobación o bloqueada.
- **Vistas globales**: `/channels` lista los canales de todos los clientes
  (`GET /admin/channels`) y `/connectors` el catálogo con cuántos clientes usan cada uno
  (`GET /admin/connectors-installs`). Las dos leen cliente a cliente con su GUC.

## Beta «WhatsApp login» por país (spec 047)

`/channels/whatsapp-login`, la segunda pestaña de Canales (T117; requisitos 31.5, 31.6
y 54.7; `api/admin/whatsapp_login_beta.py`). Lista los países donde el enlace del dueño
ofrece «Conectar con WhatsApp, sin cuenta de Meta» (desde cuándo y quién la activó) y
permite activarla en otro o quitarla. Se activa solo cuando Meta la da a la app de
Auphere en ese país. Los países de la UE y del EEE aparecen en el selector pero no se
pueden elegir, con el porqué al lado: la lista es la misma que `EU_EEA` de la API y el
CHECK de la migración 0191, y la API los rechaza igual (`eu_country_not_allowed`).
Activar y quitar piden un **motivo** de 3 a 300 caracteres y llevan `X-Operator-Id`;
los dos van a la auditoría (`whatsapp.login_beta.enabled|disabled`).

## Estado (`/status`)

`GET /admin/instance`: entorno, revisión de Alembic, commit de la imagen de la API
(`NEXUS_GIT_SHA`, lo pasan los workflows de despliegue) y si Postgres y Redis responden.

Debajo, las **anomalías** (spec 047 T172; requisitos 54.9, 43.9 y 2.6), por periodo
(último día, 7, 30 o 90 días; `?days=`, 7 por defecto). Arriba, cinco cifras: decisiones
con modelo de reserva, sin modelo, conversaciones que esperan por «Sin modelo
disponible», diferencias del libro y días con diferencias con Meta. Una fuente que no
se pudo leer sale «Sin leer», nunca 0. Luego:

- **Router**: la misma vista que `/router/anomalies` (`GET /admin/router/anomalies?since=`).
- **Libro de las bolsas** (`GET /admin/reconciliations?days=`, `ledger`): el cuadre
  calculado al momento, el mismo del proceso diario, de los partners con la consola
  nueva y las bolsas activas. Cada diferencia en palabras: la bolsa de un cliente (por
  su nombre) cuyo saldo no es la suma de sus asientos, o una cuenta cuyo libro no
  coincide con sus traspasos. Los importes van exactos al micro y en su moneda (la de la
  bolsa o la de la cuenta, `currency`).
- **Mensajes de Meta** (`meta`): los días en que lo que Meta entregó a un número no es
  lo guardado (`diff = meta_count − stored_count`: «Faltan N mensajes por guardar» o
  «Hay N guardados de más»), con el número del negocio (`identifier`) enlazado al canal.

## Módulos por partner (spec 032)

`GET/PUT /admin/partners/{id}/access` con `X-Operator-Id`. Catálogo: `panel, clients,
usage, audit, knowledge, workstation, team, billing, keys, companion`. Con la consola
encendida hace falta al menos una sección del menú. El módulo `companion` escribe
`companion_enabled` en la misma transacción. La consola filtra menú, buscador, rutas y
burbuja; una sección sin módulo redirige al primer módulo del partner.

## Facturas (antes «Dinero», spec 033)

Todo en US$. La recarga (`POST /admin/partners/{id}/wallet/purchased`) lleva
`amount_cents`, la clave de idempotencia que genera el formulario y el operador; saldo,
asiento y auditoría van en una transacción. `GET …/wallet/reconcile` compara el saldo
recargado con el libro.

## Modelos, Router y Certificaciones (spec 047)

El catálogo de modelos, la política del router y las certificaciones, sin tocar la
base a mano (historia 30; `contracts/admin-api.md` §1 a §3). Cada escritura lleva
`X-Operator-Id` y un **motivo**, que van a la auditoría de plataforma, y se aplica
desde el siguiente turno: la API olvida su catálogo y publica `catalog` en el canal
de promoción para los workers. Son las únicas pantallas que enseñan costes (54.11).
Cómo funciona lo que hay detrás: [modelos-y-router.md](modelos-y-router.md).

- **Modelos** (`/models`, `api/admin/models_catalog.py`). Una fila por despliegue:
  proveedor y ruta, residencia, estado (con la fecha de retirada), precio vigente,
  tareas certificadas y **lo que le falta para activarse**, en palabras. Filtros por
  estado. Acciones de la fila: «Activar» (por la puerta de
  `router_catalog.activate_deployment`, que dice antes y después todo lo que falta),
  «Precio» (con vigencia y fuente; si sube más de un 10 % el precio por mensaje de un
  agente, avisa a su partner y dice a cuántos), «Retirar» (con fecha: enseña el
  sustituto propuesto a cada agente fijado) y «No disponible». «Nuevo despliegue» da
  de alta en borrador, sin retención ni contrato: una licencia excluida (Llama 4,
  Qwen3.8-Flash-Next, AGPL) se rechaza y la razón queda en la auditoría
  (`deployment.rejected`). Editar las capacidades, la región, la ruta o el modelo
  caduca sus certificaciones por clase (`PATCH`, sin pantalla todavía).
- **Router** (`/router`, `api/admin/router_policies.py`; no se llama `router.py`
  porque taparía el `router` del paquete). El editor de cada perfil, tarea por tarea:
  calidad mínima, techo por llamada, hasta qué gama escala, razonamiento, muestreo
  del juez y modelo de reserva, y los techos del turno, que se pueden bajar y nunca
  subir. Guardar publica una **versión nueva** con su motivo (`router.policy_changed`).
  Debajo, la **vista previa**: cliente, agente opcional, tarea y perfil → qué
  elegiría el router, las alternativas y cada descartado con su motivo, sin llamar a
  ningún modelo (`POST /admin/router/preview`, el mismo `chain_for` del turno).
  `/router/anomalies`: los modelos de reserva y los `no_model` de los últimos 7 días,
  cliente a cliente con su GUC, y quién espera en la Bandeja por «Sin modelo
  disponible».
- **Certificaciones** (`/certifications`, `api/admin/certifications.py`). Por
  despliegue (batería, nota, métricas, fecha y si sigue vigente) y por agente (la
  suite, quién la pagó, estado), con filtros por despliegue y tarea, y el aviso si la
  batería está incompleta (sin el paquete `es` de τ-bench). «Lanzar una
  certificación» todavía responde que no se puede, y por qué: la batería por clase
  corre fuera de línea y la suite por agente es el trabajo `quality_check` de T147.

## Constructor (spec 047)

La calidad del constructor de agentes, en tres pestañas bajo `/builder` (historias 8 y
18; `api/admin/sector_tests.py`). Son tablas de plataforma: ningún dato de un cliente.

### Pruebas del sector (`/builder/sector-tests`)

T090, requisitos 21.1, 21.2 y 54.10. Un selector con los seis sectores
(`builder/sectors.py`) y, de cada uno, la versión vigente, quién la publicó y cuándo, y
sus 12 pruebas: nombre, clave, persona simulada, primer mensaje, plan, estado esperado,
criterios del juez y si es crítica (`GET /admin/builder/sector-tests`). «Editar y
publicar versión nueva» abre el editor con la vigente: cada prueba se despliega, se
quita o se añade, y el panel comprueba lo mismo que `sector_catalog.SectorTest` antes
de enviar (exactamente 12, claves únicas en minúsculas, de 1 a 6 criterios, el estado
esperado como objeto JSON). Publicar es `POST /admin/builder/sector-tests/{sector}` con
`X-Operator-Id`; los rechazos (`twelve_tests_required`, `duplicate_key`,
`invalid_test`, `unknown_sector`) se dicen en palabras. Las suites de los agentes que
ya existen no cambian; los agentes nuevos del sector nacen con la versión nueva.

### Calibración del juez (`/builder/judge-calibration`)

T087, requisito 21.8. Dice arriba si el juez **ya bloquea** publicaciones (hay un
despliegue con la calibración aprobada y vigente, la misma regla que
`judge.judge_calibrated`) o si todavía no, y entonces una prueba se decide solo por el
estado final. Debajo, el informe de un despliegue: el acuerdo con las etiquetas humanas
frente al umbral del 85 %, y cada criterio del conjunto etiquetado
(`judge_calibration_es.json`) con la etiqueta, lo que dijo el juez y si coinciden, con
el filtro «Solo los desacuerdos». Si hay varias, la tabla «Todas las calibraciones»
abre cada una (`?deployment=`). «Calibrar un despliegue» elige uno del catálogo y corre
`POST /admin/builder/judge-calibration`: una llamada al modelo por ejemplo, la paga
Auphere, y la pantalla espera el resultado.

### Evaluación del constructor (`/builder/eval`)

T100, requisito 54.4, CE-002 y CE-003. La última evaluación contra el banco de 100
descripciones (`eval_bank_v1.json`) en tres cifras, cada una con su objetivo y la
diferencia con la anterior: el porcentaje de borradores que pasan el validador a la
primera (objetivo 95 %), el que pasa la batería del sector sin edición (70 %; hoy sale
«Sin medir», porque la evaluación no corre esas pruebas) y el p90 del borrador (menos de
30 s; bajar es mejorar). Debajo, el historial (`GET /admin/builder/eval`, las últimas
20). «Correr la evaluación» acepta un número de descripciones (vacío: las 100) y llama
a `POST /admin/builder/eval`, que no escribe nada en ningún cliente y responde cuando
termina.

## Palancas del partner y del cliente (spec 047)

T172, historia 30 (requisitos 54.5, 54.6, 54.8, 54.9, 54.11 y 55; `contracts/admin-api.md`
§5). Cada escritura lleva `X-Operator-Id`; la API firma la auditoría como
`operator:{correo}`. Los rechazos de la API se dicen en palabras (`lib/action-result.ts`).
Las llamadas viven en `lib/backend-levers.ts`; lo que comparten (el motivo de 3 a 300
caracteres, quién lo hizo, el dinero en `amount_micros`) en `lib/levers.ts`.

### Consola nueva (`/partners/{id}/console-v2`)

`api/admin/console_v2.py`, requisitos 55.2, 55.4 y 55.5.

- **Qué consola ve hoy** (`GET …/console-v2`): «Consola de hoy» o «Consola nueva», desde
  cuándo y quién la activó. Según eso la pantalla ofrece «Activar» o «Volver a la consola
  de hoy»; si no se pudo leer, las dos.
- **«Correr el ensayo»** (`POST …/console-v2/dry-run`): no cambia nada y deja su informe.
  Acepta un motivo opcional.
- **El informe**: cada agente con su versión activa (si el prompt compilado es idéntico,
  byte a byte, y si el modelo sigue fijado; «Sin AgentSpec» si la versión todavía no lo
  tiene) y cada número con a quién responde hoy y a quién respondería con la consola nueva
  («A todos», «A todos, salvo N números», «Solo mi equipo · números»), qué números entran
  o salen y si aún está sin migrar. Las diferencias van primero y marcadas. Cada fila trae
  su nombre de la API (`client_name`, `agent_name`, `identifier`); los informes de antes,
  sin nombres, enseñan el principio del id.
- **«Activar la consola nueva»**: solo se puede pulsar con un ensayo sin diferencias de las
  últimas 24 horas, y la pantalla dice por qué no; la API lo vuelve a comprobar
  (`dry_run_required`, `dry_run_has_differences`). Pide un **motivo** obligatorio.
- **«Volver a la consola de hoy»**: con motivo obligatorio. La API lo rechaza si el partner
  ya confirmó el reparto en bolsas (`wallet_split_confirmed`).
- **Historial**: ensayos y activaciones, del último al primero (`GET …/console-v2/reports`),
  con su motivo, y «Ver» abre cualquiera. El informe enseña su motivo encima.

El motivo (de 3 a 300 caracteres, `{reason}`) queda en el informe y en la auditoría.

### Tope y moneda (`/partners/{id}/limits`)

`api/admin/partner_money.py`, requisitos 43.1, 46.5 y 54.5.

- **Construcción y pruebas**: la partida de este mes (`GET …/build-budget`): su estado
  («Con margen», «Cerca del tope» desde el 80 %, «Agotada») y lo gastado frente al tope.
  El formulario parte del tope vigente, en dinero y nunca en tokens, y en la moneda de la
  cuenta, que dice la API y el operador no elige. Importe (0 detiene la construcción) y
  motivo (`PUT …/build-budget`). Cambia el de este mes (subirlo desbloquea al momento) y
  el de los meses que vienen. Si la moneda cambió mientras tanto, la API responde
  `currency_mismatch` y la pantalla pide recargar.
- **«Pedir ampliación»**: quién la pidió y cuándo (`GET …/build-budget/requests`).
- **Moneda de la cuenta**: la de hoy (la de `GET …/build-budget`) y el cambio a la otra,
  EUR o USD, con motivo (`PUT …/account-currency`); si no se pudo leer, el operador
  elige. El diálogo
  avisa antes de que convierte el saldo que queda (comprado, incluido, límite de
  crédito) y el tope de este mes al cambio del BCE del día, y que deja un asiento.
  Después dice el cambio aplicado y el saldo comprado que queda; si ya estaba en esa
  moneda, que no se convirtió nada.

### Restricción soberana (Resumen del cliente)

`GET/PUT /admin/clients/{tenant_id}/sovereign` (`api/admin/client_controls.py`, 54.6):
solo proveedores europeos y modelos de pesos abiertos. Se activa o se quita con motivo;
el partner la ve como insignia y no la cambia. Un cliente sin ficha del negocio no la
admite (`no_business_profile`) y la tarjeta lo dice.

### Solo el admin enseña costes (54.11)

`lib/__tests__/costs-only-in-admin.test.ts` comprueba que los campos de coste de la API
(`internal_cost_usd`, `estimated_cost_micros`, `max_cost_per_call_micros`,
`turn_cost_ceiling_micros`, `current_price`, `meter_weights`) y `formatCostUsd` los usa el
admin y no aparecen en el código de la consola, la app, el escritorio ni los paquetes de
UI.
