# Especificación: cuatro conectores más

**Rama**: `023-cuatro-conectores-mas` · **Creada**: 2026-09-30 · **Estado**: Borrador

**Entrada**: descripción del usuario: ver §Origen.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. Los cuatro se conectan por el consentimiento que ya existe |
| **Garantías de aislamiento tocadas** | Ninguna. Las cuentas conectadas cuelgan del tenant como hoy; no entra ninguna lectura nueva de otro sitio |
| **Nota de KB que la justifica** | `[[sessions/2026-09-29-spec-021-el-numero-se-puede-mover]]` (continuación 2026-09-30, revisión de Composio) |
| **Qué se mide** | Nada nuevo: las herramientas de Composio ya se miden como herramienta de pago cuando lo son |

## Origen

El 2026-09-30 el owner pidió revisar qué conectores se pueden añadir a la
sección Conectores. Medido en el código, un conector por consentimiento
**no se siembra en el repositorio**: aparece en cuanto existe en el panel del
proveedor de consentimientos, y por eso Google Calendar, Google Sheets,
Notion, Gmail y Outlook ya están sin que nadie los escribiera aquí. Pero
«aparecer» no es «servir»: lo que llega así llega **sin categoría** (cae en
«otros»), **sin frase** que diga para qué lo usa el agente, **con todas sus
herramientas bloqueadas** —incluidas las de leer, porque lo desconocido nace
bloqueado, y eso es correcto— y **con nombres técnicos** en Capacidades
(`SHOPIFY_LIST_PRODUCTS`).

Se eligen cuatro por lo que venden hoy los partners: **Shopify** (tienda),
**Stripe** (cobros), **Calendly** (citas) y **HubSpot** (clientes). Cada uno
es la alternativa a algo que ya hay (WooCommerce, Amigable Cobro, AgendaPro,
nada aún) para el partner que no usa eso.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El partner conecta uno de los cuatro y el agente lo usa (Prioridad: P1)

En Conectores, el partner ve Shopify en «Tienda», Stripe en «Cobros»,
Calendly en «Citas» y HubSpot en «Clientes», cada uno con una frase que dice
para qué lo usará el agente. Pulsa **Conectar**, da su consentimiento en el
proveedor, vuelve, y en Capacidades ve las capacidades de lectura de ese
conector **encendidas y con nombre de negocio** («Consultar productos y
precios», «Ver el estado de un cobro», «Consultar huecos», «Buscar un
contacto»). Las que escriben aparecen **bloqueadas** con la frase de siempre:
las abre Auphere cuando se confía en el agente.

**Por qué esta prioridad**: sin esto, los cuatro «aparecen» pero no sirven, y
el partner que los conecta acaba escribiéndonos.

**Prueba independiente**: con las cuatro cuentas dadas de alta en el
proveedor, conectar cada una en un cliente de prueba y leer Capacidades.

**Escenarios de aceptación**:

1. **Dado** el catálogo de Conectores, **cuando** el partner lo abre,
   **entonces** cada uno de los cuatro está en su categoría y su tarjeta dice
   para qué lo usa el agente.
2. **Dado** un conector de los cuatro recién conectado, **cuando** el partner
   abre Capacidades, **entonces** las capacidades de lectura están encendidas
   y con nombre de negocio, y las que escriben, bloqueadas hasta que un
   operador las abra.
3. **Dado** una herramienta del proveedor que no esté en nuestra lista,
   **cuando** llega, **entonces** nace bloqueada (como hoy) y se enseña con
   un nombre legible, nunca con un identificador técnico.

---

### Historia 2 — Las plantillas recomiendan el conector que toca (Prioridad: P2)

Un cliente creado con una plantilla de tienda recomienda Shopify o WooCommerce;
uno de barbería, clínica o spa recomienda Calendly o AgendaPro; uno de
cobranza, Stripe o Amigable Cobro. La recomendación es una sugerencia en
Conectores, no una obligación.

**Por qué esta prioridad**: acorta el camino de «acabo de crear el cliente» a
«el agente ya consulta la tienda». Va después porque sin la Historia 1 no hay
nada que recomendar.

**Prueba independiente**: crear un cliente con cada plantilla y ver qué
recomienda Conectores.

**Escenarios de aceptación**:

1. **Dado** un cliente de tienda, **cuando** abre Conectores, **entonces**
   Shopify y WooCommerce aparecen como recomendados.
2. **Dado** un cliente de barbería, **cuando** abre Conectores, **entonces**
   Calendly y AgendaPro aparecen como recomendados.
3. **Dado** un cliente de cobranza, **cuando** abre Conectores, **entonces**
   Stripe y Amigable Cobro aparecen como recomendados.

---

### Casos límite

- **El proveedor de consentimientos no responde**: los cuatro no aparecen y
  Conectores lo dice, como hoy con los cinco que ya hay.
- **La cuenta del proveedor aún no existe** para uno de los cuatro: ese no
  aparece; los otros tres sí. No hay tarjeta apagada.
- **El proveedor añade una herramienta nueva** a un conector: nace bloqueada
  y con nombre legible; un operador la abre.
- **El partner conecta Shopify y WooCommerce a la vez**: el agente tiene las
  dos y la consola no lo impide; las plantillas recomiendan, no excluyen.
- **Quien solo mira** ve el catálogo y las capacidades sin poder conectar ni
  encender.

## Requisitos *(obligatorio)*

### Requisito 1 — Cada conector llega entero

**Historia de usuario:** Como partner, quiero que Shopify, Stripe, Calendly y
HubSpot aparezcan en Conectores en su sitio y con su frase, para saber para
qué sirven antes de conectarlos.

#### Criterios de aceptación

1. El sistema DEBE enseñar Shopify en «Tienda», Stripe en «Cobros», Calendly
   en «Citas» y HubSpot en «Clientes».
2. El sistema DEBE describir cada uno con una frase de negocio en español e
   inglés, sin nombres técnicos ni siglas.
3. IF uno de los cuatro no existe en el proveedor de consentimientos THEN el
   sistema NO DEBE enseñar una tarjeta apagada ni un hueco.

### Requisito 2 — Lo que lee nace encendido; lo que escribe, bloqueado

**Historia de usuario:** Como partner, quiero que al conectar uno de los
cuatro el agente pueda consultar sin que nadie intervenga, y que lo que cambia
cosas espere a que alguien lo abra.

#### Criterios de aceptación

1. WHEN un partner conecta uno de los cuatro THEN el sistema DEBE dejar
   encendidas sus capacidades de lectura (productos, precios y pedidos;
   estado de un cobro; huecos y citas; contactos).
2. WHEN un partner conecta uno de los cuatro THEN el sistema DEBE dejar
   bloqueadas las que escriben (crear o cambiar un pedido; cobrar o
   reembolsar; crear o cancelar una cita; crear, cambiar o borrar un
   contacto) hasta que un operador las abra, y la consola DEBE decirlo con la
   frase de siempre.
3. IF llega una herramienta que no está en nuestra lista THEN el sistema DEBE
   dejarla bloqueada, como hoy.
4. La lista de qué lee y qué escribe DEBE escribirse contra las herramientas
   que el proveedor expone de verdad para cada uno, no de memoria.

### Requisito 3 — Nombres de negocio, nunca técnicos

**Historia de usuario:** Como partner, quiero leer «Consultar productos y
precios», no `SHOPIFY_LIST_PRODUCTS`.

#### Criterios de aceptación

1. El sistema DEBE enseñar cada capacidad de los cuatro con un nombre de
   negocio en español e inglés.
2. IF una capacidad no tiene nombre de negocio THEN el sistema DEBE
   enseñarla con un nombre legible derivado del técnico (sin guiones bajos ni
   prefijo del proveedor), y NO DEBE enseñar el identificador tal cual.

### Requisito 4 — Las plantillas recomiendan

1. WHERE la plantilla del cliente es de tienda EL sistema DEBE recomendar
   Shopify y WooCommerce; WHERE es de citas (barbería, peluquería, clínica,
   spa, uñas), Calendly y AgendaPro; WHERE es de cobranza, Stripe y Amigable
   Cobro.
2. Recomendar NO DEBE impedir conectar cualquier otro.

### Requisito 5 — Lo que no cambia

1. Conectar sigue siendo por consentimiento en el proveedor, con el enlace
   firmado de hoy.
2. El catálogo sigue siendo dinámico: los cuatro aparecen porque existen en el
   proveedor, no porque estén escritos aquí.
3. Lo desconocido sigue naciendo bloqueado.

### Entidades clave

- **Conector**: lo que ya existe. Los cuatro nuevos no añaden filas: se
  proyectan desde el proveedor. Lo que se añade es su **frase**, su
  **categoría** y la **lista de qué lee y qué escribe**.
- **Cuenta conectada**: pertenece al **tenant** (cliente final) y la RLS la
  alcanza por `tenant_id`, como hoy.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un partner conecta Shopify y, sin que Auphere intervenga, el
  agente responde qué productos hay y a qué precio.
- **CE-002**: en Capacidades, ninguna capacidad de los cuatro se lee con un
  identificador técnico.
- **CE-003**: ninguna capacidad que escriba en la tienda, el cobro, la
  agenda o los contactos está encendida sin que un operador la haya abierto.
- **CE-004**: los cuatro están en su categoría, con su frase, en español e
  inglés.
- **CE-005**: un cliente nuevo de tienda, citas o cobranza ve recomendado el
  conector que le toca.

## Fuera de alcance

- **Otros conectores** (Square, Zoho, Zendesk, Mailchimp…) — la lista completa
  quedó en la revisión del 2026-09-30; entran de cuatro en cuatro.
- **Sincronizar datos** entre conectores (Shopify ↔ catálogo de Meta) —
  lo hace el proveedor.
- **Abrir las capacidades que escriben desde la consola** — sigue siendo de
  operador, por la regla de lo desconocido.

## Supuestos

- Las cuatro cuentas en el proveedor de consentimientos las crea el owner;
  hasta entonces, los cuatro no aparecen y no hay nada que probar en staging.
- La lista de herramientas de cada uno se lee del proveedor en el momento de
  planificar; los nombres de negocio y qué lee / qué escribe se escriben
  contra esa lista.
- «Recomendado» ya existe como concepto en Conectores para el sector del
  cliente; se amplía, no se inventa.
