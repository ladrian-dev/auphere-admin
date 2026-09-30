# Especificación: tres conectores más

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

Se eligieron cuatro por lo que venden hoy los partners; **Shopify queda
fuera por ahora** (el proveedor de consentimientos no lo gestiona: haría
falta una app propia de Shopify Partners). Entran **Stripe** (cobros),
**Calendly** (citas) y **HubSpot** (clientes). Cada uno es la alternativa a
algo que ya hay (Amigable Cobro, AgendaPro, nada aún) para el partner que no
usa eso.

## Clarifications

### Session 2026-09-30

- Q: ¿Entra Shopify en esta spec, si Composio no ofrece credenciales gestionadas y hace falta una app de Shopify Partners? → A: **Shopify queda sin conexión por ahora** (owner). Esta spec entrega Stripe, Calendly y HubSpot; Shopify volverá en otra spec cuando exista la app de Partners.
- Q: ¿Qué herramientas de cada conector llegan a Capacidades: todas las del proveedor (Stripe 426, HubSpot 262, Calendly 53) gateadas una a una, o una lista cerrada? → A: **una lista cerrada por toolkit, escrita por Auphere** (8–12 herramientas que un negocio usa en una conversación). Lo que no está en la lista no se sincroniza ni llega al agente ni a Capacidades.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El partner conecta uno de los cuatro y el agente lo usa (Prioridad: P1)

En Conectores, el partner ve Stripe en «Cobros», Calendly en «Citas» y
HubSpot en «Clientes», cada uno con una frase que dice
para qué lo usará el agente. Pulsa **Conectar**, da su consentimiento en el
proveedor, vuelve, y en Capacidades ve las capacidades de lectura de ese
conector **encendidas y con nombre de negocio** («Consultar productos y
precios», «Ver el estado de un cobro», «Consultar huecos», «Buscar un
contacto»). Las que escriben aparecen **bloqueadas** con la frase de siempre:
las abre Auphere cuando se confía en el agente.

**Por qué esta prioridad**: sin esto, los cuatro «aparecen» pero no sirven, y
el partner que los conecta acaba escribiéndonos.

**Prueba independiente**: con las tres cuentas dadas de alta en el
proveedor, conectar cada una en un cliente de prueba y leer Capacidades.

**Escenarios de aceptación**:

1. **Dado** el catálogo de Conectores, **cuando** el partner lo abre,
   **entonces** cada uno de los tres está en su categoría y su tarjeta dice
   para qué lo usa el agente.
2. **Dado** un conector de los tres recién conectado, **cuando** el partner
   abre Capacidades, **entonces** las capacidades de lectura están encendidas
   y con nombre de negocio, y las que escriben, bloqueadas hasta que un
   operador las abra.
3. **Dado** las cientos de herramientas que el proveedor expone para cada
   uno, **cuando** el partner abre Capacidades, **entonces** solo ve las de
   la lista cerrada, cada una con su nombre de negocio.

---

### Historia 2 — Las plantillas recomiendan el conector que toca (Prioridad: P2)

Un cliente creado con una plantilla de barbería, clínica o spa recomienda
Calendly o AgendaPro; uno de cobranza, Stripe o Amigable Cobro; uno de
tienda sigue recomendando WooCommerce. La recomendación es una sugerencia en
Conectores, no una obligación.

**Por qué esta prioridad**: acorta el camino de «acabo de crear el cliente» a
«el agente ya consulta la tienda». Va después porque sin la Historia 1 no hay
nada que recomendar.

**Prueba independiente**: crear un cliente con cada plantilla y ver qué
recomienda Conectores.

**Escenarios de aceptación**:

1. **Dado** un cliente de barbería, **cuando** abre Conectores, **entonces**
   Calendly y AgendaPro aparecen como recomendados.
2. **Dado** un cliente de cobranza, **cuando** abre Conectores, **entonces**
   Stripe y Amigable Cobro aparecen como recomendados.

---

### Casos límite

- **El proveedor de consentimientos no responde**: los cuatro no aparecen y
  Conectores lo dice, como hoy con los cinco que ya hay.
- **La cuenta del proveedor aún no existe** para uno de los tres: ese no
  aparece; los otros sí. No hay tarjeta apagada.
- **El proveedor añade una herramienta nueva** a un conector: no llega —
  la lista es cerrada—; entra cuando Auphere la añada a la lista con su
  nombre y su pista.
- **El partner conecta Calendly y AgendaPro a la vez**: el agente tiene las
  dos y la consola no lo impide; las plantillas recomiendan, no excluyen.
- **Quien solo mira** ve el catálogo y las capacidades sin poder conectar ni
  encender.

## Requisitos *(obligatorio)*

### Requisito 1 — Cada conector llega entero

**Historia de usuario:** Como partner, quiero que Stripe, Calendly y HubSpot
aparezcan en Conectores en su sitio y con su frase, para saber para
qué sirven antes de conectarlos.

#### Criterios de aceptación

1. El sistema DEBE enseñar Stripe en «Cobros», Calendly en «Citas» y HubSpot
   en «Clientes».
2. El sistema DEBE describir cada uno de los tres con una frase de negocio en español e
   inglés, sin nombres técnicos ni siglas.
3. IF uno de los tres no existe en el proveedor de consentimientos THEN el
   sistema NO DEBE enseñar una tarjeta apagada ni un hueco.

### Requisito 2 — Lo que lee nace encendido; lo que escribe, bloqueado

**Historia de usuario:** Como partner, quiero que al conectar uno de los
tres el agente pueda consultar sin que nadie intervenga, y que lo que cambia
cosas espere a que alguien lo abra.

#### Criterios de aceptación

1. WHEN un partner conecta uno de los tres THEN el sistema DEBE dejar
   encendidas sus capacidades de lectura (estado de un cobro y enlaces de
   pago; huecos y citas; contactos).
2. WHEN un partner conecta uno de los tres THEN el sistema DEBE dejar
   bloqueadas las que escriben (cobrar o reembolsar; crear o cancelar una
   cita; crear, cambiar o borrar un contacto) hasta que un operador las abra, y la consola DEBE decirlo con la
   frase de siempre.
3. El sistema DEBE sincronizar de cada uno de los tres **solo una lista
   cerrada** de herramientas, escrita por Auphere; las demás del proveedor NO
   DEBEN llegar a Capacidades ni al agente.
4. IF el proveedor añade o retira una herramienta de la lista cerrada THEN el
   sistema DEBE avisarlo en el registro y NO DEBE enseñar la retirada ni
   inventar la nueva; cambiar la lista es un cambio de Auphere.
5. La lista cerrada, y qué lee y qué escribe en ella, DEBE escribirse contra
   las herramientas que el proveedor expone de verdad para cada uno, no de
   memoria.

### Requisito 3 — Nombres de negocio, nunca técnicos

**Historia de usuario:** Como partner, quiero leer «Ver el estado de un
cobro», no `STRIPE_LIST_PAYMENT_INTENTS`.

#### Criterios de aceptación

1. El sistema DEBE enseñar cada capacidad de los tres con un nombre de
   negocio en español e inglés.
2. Toda herramienta de la lista cerrada DEBE tener nombre de negocio; una
   sin nombre NO DEBE entrar en la lista. (Con la lista cerrada, el nombre
   derivado del técnico deja de hacer falta.)

### Requisito 4 — Las plantillas recomiendan

1. WHERE la plantilla del cliente es de citas (barbería, peluquería, clínica,
   spa, uñas) EL sistema DEBE recomendar Calendly y AgendaPro; WHERE es de
   cobranza, Stripe y Amigable Cobro.
2. Recomendar NO DEBE impedir conectar cualquier otro.

### Requisito 5 — Lo que no cambia

1. Conectar sigue siendo por consentimiento en el proveedor, con el enlace
   firmado de hoy.
2. El catálogo sigue siendo dinámico: los cuatro aparecen porque existen en el
   proveedor, no porque estén escritos aquí.
3. Lo desconocido sigue naciendo bloqueado.

### Entidades clave

- **Conector**: lo que ya existe. Los tres nuevos no añaden filas: se
  proyectan desde el proveedor. Lo que se añade es su **frase**, su
  **categoría** y la **lista de qué lee y qué escribe**.
- **Cuenta conectada**: pertenece al **tenant** (cliente final) y la RLS la
  alcanza por `tenant_id`, como hoy.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un partner conecta Stripe y, sin que Auphere intervenga, el
  agente responde si un cobro está pagado y manda un enlace de pago.
- **CE-002**: en Capacidades, ninguna capacidad de los tres se lee con un
  identificador técnico.
- **CE-003**: ninguna capacidad que escriba en el cobro, la agenda o los
  contactos está encendida sin que un operador la haya abierto.
- **CE-004**: los tres están en su categoría, con su frase, en español e
  inglés.
- **CE-005**: un cliente nuevo de citas o cobranza ve recomendado el
  conector que le toca.

## Fuera de alcance

- **Shopify** — sin credenciales gestionadas en el proveedor; entra cuando
  exista la app de Shopify Partners (owner, 2026-09-30).
- **Otros conectores** (Square, Zoho, Zendesk, Mailchimp…) — la lista completa
  quedó en la revisión del 2026-09-30; entran por tandas.
- **Sincronizar datos** entre conectores (Shopify ↔ catálogo de Meta) —
  lo hace el proveedor.
- **Abrir las capacidades que escriben desde la consola** — sigue siendo de
  operador, por la regla de lo desconocido.

## Supuestos

- Las cuentas en el proveedor de consentimientos: **Stripe, Calendly y HubSpot
  creadas el 2026-09-30** (`evidence/README.md`). **Shopify no**: el proveedor
  no ofrece credenciales gestionadas para Shopify; hace falta una app propia
  de Shopify Partners con su Client ID y Client Secret, que hoy no existe.
  Shopify queda fuera de esta spec (Clarifications).
- La lista de herramientas de cada uno se lee del proveedor en el momento de
  planificar; los nombres de negocio y qué lee / qué escribe se escriben
  contra esa lista.
- «Recomendado» existe hoy en Capacidades (lo que la plantilla del sector
  enciende), no en Conectores: medido en el plan (D4). Se lleva a la tarjeta
  de conector con el mismo criterio —lo dice la plantilla del sector— sin
  cambiar lo que Capacidades ya hace.
