# Recorrido UI de la spec 047 · 2026-10-28

Recorrido a mano, vista por vista y flujo por flujo, de las tres apps de la 047 con
la app levantada en local: el **panel de administración** (`apps/admin`, :3100), la
**consola de partners** (`apps/console`, :3110, como Luis en Ladrian Studio y con
cada rol) y la **consola lite** (como Marta en Flor y Encanto, también a 375 px). La
app móvil queda fuera.

## Cómo se recorrió

- **Stack propio**: Postgres `nexus_047_ui` (migrada a la cabeza, `0203`) y Redis
  `db 7`; API, consola y panel con `preview_start`; el worker en segundo plano con
  `NEXUS_LLM_USE_INMEMORY=true` (constructor, copiloto y probador sin claves). Semilla
  `dev_seed_fabrica.py` y un operador local (`seed_operator.py`). La contraseña de
  prueba de la semilla está en `apps/api/.env.local` (gitignored), variable
  `FABRICA_TEST_PASSWORD`.
- **Conversaciones**: un simulador de webhook firmado con el secreto de desarrollo,
  contra números de mentira de la semilla (nada sale a Meta: los canales no tienen
  credenciales).
- **Barrido de cada vista** (Playwright, guion en el scratchpad): claro y oscuro a
  1280 px y claro a 375 px; axe (WCAG 2.0–2.2 A/AA, serio y crítico), desbordamiento
  horizontal, errores de consola y respuestas ≥ 400, y las palabras prohibidas
  («Integraciones», «Capacidades», «créditos», «tokens», punto y coma) en el texto
  visible y en `aria-label`/`title`/`placeholder`. Cada rol con sus vistas clave.
- **Flujos**: en el panel del navegador y con guiones de Playwright contra la API
  real (los campos de fecha no se pueden escribir desde la herramienta del panel).
- **Contraste**: medido con `getComputedStyle` (convertido a sRGB), no a ojo.
- **Teclado y movimiento**: tabulación con foco visible, `prefers-reduced-motion`
  (0 transiciones con «reducir»), vidrio solo en la capa flotante.

Estados: **OK**, **Arreglado**, **Defecto abierto**, **Frontera externa**,
**Decisión pendiente**. Las capturas son del momento del recorrido: en lo arreglado,
el «antes». Están en el scratchpad de la sesión.

## Vista por vista

| App | Vista o flujo | Estado | Gravedad | Qué se probó y cómo | Captura |
|---|---|---|---|---|---|
| Admin | Panel, Partners, ficha de partner | OK | — | Barrido claro/oscuro/375 px con axe (serio y crítico), desbordamiento y palabras: sin hallazgos. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/panel-light-1280.png` |
| Admin | Constructor › Pruebas del sector | Arreglado | Baja | Barrido. El texto de cabecera llevaba punto y coma: corregido (`copy-047.test.ts`). «Editar y publicar versión nueva» cubierto por vitest, no se publicó ninguna versión. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/builder-sector-tests-light-1280.png` |
| Admin | Constructor › Calibración del juez | Frontera externa | — | Barrido sin hallazgos. «Calibrar un despliegue» llama a un modelo de verdad: no se pulsó. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/builder-judge-light-1280.png` |
| Admin | Constructor › Evaluación | Frontera externa | — | Barrido: «Todavía no se ha corrido la evaluación». Correrla pasa el banco por el constructor con un modelo: no se lanzó. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/builder-eval-light-1280.png` |
| Admin | Canales › Catálogo | OK (nota anterior a la 047) | Baja | Barrido. La nota de Instagram «Diseñado (ADR-030); se construye…» lleva punto y coma, pero viene de `channel_catalog.py` del 19-oct (anterior a la 047). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/channels-light-1280.png` |
| Admin | Canales › Beta «WhatsApp login» | Arreglado | Media | La página no hidrataba: `Intl.DisplayNames` da nombres distintos en Node y en Chromium («RAE de Hong Kong (China)» / «Hong Kong»). Los nombres se calculan en el servidor y viajan como dato (`login-beta.test.tsx`). Verificado en vivo: 0 errores de hidratación. Activar/quitar con motivo: vitest. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/channels-wa-login-light-1280.png` |
| Admin | Conectores y ficha del conector (ajustes) | Arreglado + abierto anterior | Baja | «Lo que cada agente rellena… en su página de la integración» → «…en la página del conector» (`copy-047.test.ts`). Abierto, anterior a la 047: el término «Capacidades» de la ficha y, en `/connectors`, axe `list` y el contraste del icono de Amigable Venta. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/connector-woocommerce-light-1280.png` |
| Admin | Partners › Tope y moneda | Arreglado | Baja | Guardar el tope con motivo (50 → 60 €, verificado). Diálogo de cambio de moneda abierto (no se convirtió). Punto y coma del texto de la moneda corregido. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/partner-limits-light-1280.png` |
| Admin | Partners › Consola nueva | OK | — | Demo USD: ensayo con motivo opcional → «Sin diferencias»; «Activar» exige motivo («Hace falta el motivo») y activa; «Volver a la consola de hoy» con motivo; historial con los dos informes. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/flow-console-v2-dryrun.png` |
| Admin | Router (perfiles y vista previa) | OK con observación | Baja | Barrido sin hallazgos. Los valores de razonamiento salen crudos (`none/low/medium/high`) en la tabla del operador. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/router-light-1280.png` |
| Admin | Router › Anomalías, Certificaciones, Modelos | Arreglado | Baja | Los vacíos de solo lectura pintaban en desarrollo «EmptyState without action — pass one or set readonly» (lo que axe marcaba como contraste). `readonly` en 6 vacíos de la 047 (`router-screens.test.tsx`). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/router-anomalies-light-1280.png` |
| Admin | Estado (anomalías y conciliaciones) | Arreglado | Baja | Cinco cifras, Router, libro de las bolsas («El libro cuadra») y Meta. Mismo aviso de desarrollo del vacío: corregido. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/status-light-1280.png` |
| Admin | Ficha del cliente › Restricción soberana | Arreglado + abierto anterior | Media | Activar y quitar con motivo obligatorio: OK. Punto y coma del texto corregido. Abierto: en oscuro los enlaces `text-primary-deep` («Ver todas», «Abrir») dan 2,26:1 (medido con getComputedStyle); el token oscuro es el mismo desde antes de la 047. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/admin/operator/flow-sovereign-on.png` |
| Admin | Login del panel | Abierto (anterior) | Baja | Los campos se anuncian por su placeholder en el árbol de accesibilidad del navegador. | — |
| Partner | Panel | Decisión pendiente | Media | Barrido y lectura: «Necesita tu atención» dice «3 agentes sin canal» para agentes cuyo número existe con la audiencia sin elegir; «Clientes 0 de 4 atendiendo». | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/panel-light-1280.png` |
| Partner | Clientes (lista) y alta en tres datos | Decisión pendiente | Media | Alta real: chips de web e Instagram, el correo no se toma por web, «Más ajustes» con país/zona/monedas/Solo UE, lleva al Panel con la lectura (falla limpia en un dominio .test con «Reintentar»). La moneda de la bolsa sale siempre USD (ver decisiones). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/clients-light-1280.png` |
| Partner | Migas del cliente | Arreglado | Media | «Clientes › flor-y-encanto»: ninguna página anunciaba el nombre. `ClientHeaderV2` lo anuncia (`client-header-v2.test.tsx`). Verificado en vivo. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/client-flor-light-1280.png` |
| Partner | Panel del cliente | Decisión pendiente | Media | «Resueltas sin persona 100 %» cuenta una conversación fuera de la audiencia que el agente nunca respondió. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/client-flor-light-1280.png` |
| Partner | Negocio a 375 px | Arreglado | Alta | La página medía 435 px: el estado `sr-only` (absoluto) de cada sección escapaba de la tira deslizable. `relative` en la tira (`business-page.test.tsx`). Verificado: 375/375. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/client-flor-business-light-375.png` |
| Partner | Negocio › Horario (nocturno) | Arreglado | Media | 22:00–03:00 → «Nocturno · cierra al día siguiente» y la frase «…de 22:00 a 03:00 del día siguiente». Error de hidratación de ids del editor de turnos (contador de módulo): ids por posición (`shift-editor.test.tsx`). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/client-flor-business-light-1280.png` |
| Partner | Negocio › Fechas especiales | Arreglado | Media | Cerrada (Navidad) y con turno nocturno (Nochevieja) guardadas. Sin «Desde» decía «La fecha final no puede ser anterior a la inicial» → «Elige el día en que empieza.» ES/EN (`special-dates-section.test.tsx`, la prueba de interacción que faltaba). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-special-dates.png` |
| Partner | Negocio › Servicios | Arreglado + decisión | Media | No reservable sin precio, gratis 30 min y 25.000 CLP creados. Cada fila tenía 4 iconos (regla de los tres puntos): ahora «⋯» con `RowActions`, la lite sigue con 2 botones (`services-section.test.tsx`). Decisión: «Solo Ventas mayoristas» no se puede si todos los agentes atienden todos los servicios, y el diálogo no lo explica. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-services.png` |
| Partner | Negocio › Sedes y horario por sede | OK | — | Sede creada; «Horario de» con la sede y «Usar el horario del negocio» (heredado). Observación: el ejemplo de teléfono es +34 en un negocio de Chile. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/client-flor-business-light-1280.png` |
| Partner | Agentes (lista) | OK | — | Barrido con y sin agentes. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/client-flor-agents-light-1280.png` |
| Partner | Nuevo agente (describir y preguntas) | Arreglado | Alta | Borrador real del worker en ~10 s (generador local), 2 preguntas. «Guardar respuestas» daba 500 (`NoBusinessProfile`) en un cliente sin ficha: `update_policies` estrena la ficha como `update_basics` (pytest `test_agent_draft_job`). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/agent-new-cafe-light-1280.png` |
| Partner | Agente › Aviso de IA y puerta | Arreglado | Bloqueante | La puerta exige decidir el aviso de IA y la pantalla no tenía dónde: ningún agente nuevo podía guardarse. Bloque «Aviso de IA» (leer y editar; «Arreglar en el borrador» lo abre) (`agent-builder.test.tsx`, `builder-model.test.ts`). Verificado: aviso decidido → puerta solo con lo saltable → owner «Guardar igualmente» con motivo → v1 «Atiende ahora». | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-publish-1-gate.png` |
| Partner | Agente › cabecera tras guardar | Arreglado | Media | Seguía «Borrador» hasta recargar. `refreshAll` relee la cabecera (`agentHeaderAction`, que existía sin uso) (`agent-builder.test.tsx`). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-publish-2-published.png` |
| Partner | Agente › Historial, deshacer y restaurar | Arreglado | Media | «Cambió: … mode, schema_version, test_suite» → solo partes con palabra (`agent-history.test.tsx`). Deshacer no aparece en la primera versión (no hay adónde volver: correcto). Restaurar: vitest. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/agent-recepcion-light-1280.png` |
| Partner | Agente › Probador y pruebas | OK (frontera de modelo) | — | Probador con hora y agenda simuladas responde con el modelo simulado local («[fallback:…] ok»). Las pruebas corren al guardar; con el modelo simulado fallan las críticas, como se espera. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/agent-recepcion-tests-light-1280.png` |
| Partner | Agente › Copiloto y constructor del cliente | OK | — | Copiloto: propone la regla y una prueba (Aplicar/Rechazar, caducan a los 15 min). «Completar con el constructor»: una pregunta frecuente por confirmar y un agente propuesto. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-client-builder.png` |
| Partner | Agente › Calidad (Avanzado) | Arreglado + frontera | Media | Salía «En el borrador: nexus/current-binding» (el modelo de antes) como si cambiara algo. Se reconoce como «el de antes» (`model-quality-model.test.ts`). Las opciones salen «Sin precio estimado · Sin comprobar»: ningún despliegue certificado en local (D44). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/agent-recepcion-quality-light-1280.png` |
| Partner | Agente › Conectores | Arreglado + frontera | Media | WhatsApp y TikTok salían como conectores «Sin conectar» (con el número conectado) y sus logos daban 404. La API los omite (`channel_only`, pytest `test_activations`). Conectar de verdad (OAuth/Composio/claves) es frontera. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/agent-recepcion-integrations-light-1280.png` |
| Partner | Agente › Conocimiento («Enseñar») | OK | Baja | «Solo este agente»: «Enseñado · Indexado». Observación: enseña «68 B» de tamaño en un dato enseñado. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-teach-dialog.png` |
| Partner | Agente › Recepción | OK | — | Editor «Este agente es Recepción» (destinos: vitest `reception-section`). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-reception-editor.png` |
| Partner | Agente › Rendimiento y Mejoras | Arreglado | Media | Sin conversaciones suficientes: estados vacíos correctos («Nada que mejorar por ahora»). La gráfica vacía era una caja deslizable inalcanzable con teclado (axe serio en Ventas mayoristas y Café Origen): ya no desliza (`block-chart.test.tsx`). Verificado: axe limpio. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/agent-ventas-light-1280.png` |
| Partner | Agente › ciclo de vida | OK | — | Pausar (inmediato, «Pausado · a mano»), reanudar, hacer por defecto, archivar el de por defecto (pide antes otro por defecto), restaurar (vuelve en pausa). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-life-archived.png` |
| Partner | Canal › página del canal | Arreglado | Baja | «Solo mi equipo» sin número de prueba se rechaza; con número, guarda; «A todos» + 1 excepción + 3 personas; historial con antes/después; «Deshacer». El historial decía «console:luis@…»: se quita el origen (`channel-page.test.tsx`). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-channel-saved.png` |
| Partner | Canal › enlace del dueño | OK (frontera) | — | Crear, copiar (portapapeles), pendiente con «Crear otro enlace» y «Revocar». El enlace en un teléfono real es de staging. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-owner-link.png` |
| Partner | Canal › pasar un número a otro agente | Arreglado (semilla) | Media | No aparecía: la semilla dejaba los agentes en `draft` y sin agente por defecto. Ahora como la 0190 (pytest `test_dev_seed_fabrica`). Pasar y devolver un número: OK. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-move-number.png` |
| Partner | Dinero › Consumo y bolsas | OK + decisión | Media | Asignar 20 USD desde EUR con recibo BCE (18,52 €), mover, relleno mensual, moneda de la bolsa, partidas y CSV. Decisión: un cliente sin bolsa (Panadería Prueba) no sale en «Saldo por cliente». | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/flow-money-assign.png` |
| Partner | Dinero › Asistente de reparto | OK | — | «No hay nada que repartir» (las bolsas ya mandan). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/usage-repartir-light-1280.png` |
| Partner | Dinero › Facturación | Hueco conocido | Media | «Comprar saldo · Importe en dólares» con la cuenta en euros: es el hueco anotado (`billing/credit` solo USD). Tarjeta y Stripe: frontera. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/billing-light-1280.png` |
| Partner | Campana y avisos | Arreglado | Alta | Avisaba «Flor y Encanto se ha quedado sin saldo» con la bolsa llena: el cron de la consola de hoy no miraba las bolsas (pytest `test_wallet_alerts`). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/notifications-light-1280.png` |
| Partner | Auditoría | Arreglado | Media | Filtros y filas. La categoría decía «Integraciones» y tres frases «una integración»: «Conectores» y migración 0203 (pytest `test_audit_047`). También «Integraciones que pide» → «Conectores que pide». | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/audit-light-1280.png` |
| Partner | Equipo y roles | OK | — | Miembros, «Qué puede hacer cada rol», invitar (rol por su descripción). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/team-light-1280.png` |
| Partner | ⌘K | OK | — | «Recep» → los dos Recepción con su cliente; flechas e Intro abren el agente. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/cmdk-recep.png` |
| Partner | Bandeja del partner | OK por diseño | — | `/inbox` lleva al Panel: el partner solo ve metadatos (`/clients/{ref}/conversations`). «Corregir esta respuesta» está en la lite. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/luis/inbox-light-1280.png` |
| Partner | Roles: Ana (admin) | OK | — | Asigna saldo y topes, edita agentes. Facturación no está (redirige). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/ana/usage-light-1280.png` |
| Partner | Roles: Lucía (builder) | OK | — | «Pedir saldo» en vez de asignar, sin «Guardar el tope», edita agentes. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/lucia/usage-light-1280.png` |
| Partner | Roles: Pablo (analyst) | OK | — | Solo lectura del agente; «Pedir saldo» y el copiloto piden solo lectura en la API (por diseño). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/pablo/agent-light-1280.png` |
| Partner | Roles: Irene (billing) | Decisión pendiente | Alta | Sin `clients:read` no recibe el bloque `panel` y cae al Panel de hoy: «Saldo disponible 100,03 US$» con la cuenta en euros. Además axe `aria-prohibited-attr` en la cifra (componente anterior a la 047). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/irene/panel-light-1280.png` |
| Partner | Demo USD (consola de hoy) | OK (historia 13) | — | Panel, clientes, alta de antes, Consumo, Facturación, Auditoría, Equipo y avisos. Consumo dice «Tokens de entrada…» desde la v1 (anterior a la 047). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/demousd/panel-light-1280.png` |
| Lite | Inicio | OK | — | Barrido claro/oscuro/375 sin hallazgos. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/marta/inicio-light-375.png` |
| Lite | Bandeja | Abierto (anterior) | Media | Hilo con «Atiende: Recepción». Un mensaje fallido enseña el error técnico crudo «No se envió: LookupError: no Meta credentials…» (texto de la spec 030, 8-oct). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/marta/inbox-light-1280.png` |
| Lite | Corregir esta respuesta | Arreglado | Baja | Tres pasos, tipo «Es un dato», paráfrasis. «Escribe lo que preguntó el cliente» salía dos veces (campo y abajo): solo bajo su campo (`correction-dialog.test.tsx`). Sin modelo local no hay paráfrasis automática (frontera). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/marta/flow-correct-dato-3.png` |
| Lite | Agentes: pausar y reanudar (375 px) | OK + decisión | Baja | Confirmación con el número de conversaciones, «Lo pausó Marta Vidal desde la web», reanudar. Coherencia: la lite dice «Principal» y la consola «Por defecto». | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/marta/lite-pause-375.png` |
| Lite | Negocio | OK | — | Mismas secciones que el partner (los arreglos de horario, fechas y servicios aplican aquí; los servicios siguen con 2 botones). | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/marta/negocio-light-375.png` |
| Lite | Consumo | OK | — | Barrido claro/oscuro/375. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/marta/usage-light-375.png` |
| Lite | Campana | Parcial | — | «Notificaciones — 2 sin leer». Los enlaces a la lite (`LITE_LINKS`) se cubren en pruebas; no se capturó el desplegable. | — |
| Lite | Cliente archivado | OK + observación | Baja | Marta va a «No puedes entrar»; la página dice «CONSOLA DE PARTNERS» a una persona del cliente (marco de acceso anterior a la 047). Restaurar devuelve cada agente a su estado. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/marta/lite-archived.png` |
| Lite | 375 px, teclado, movimiento y oscuro | OK | — | Sin desbordamiento a 375 en las seis vistas; tabulando, todo con foco visible (el buscador por `focus-within`); con «reducir movimiento» 0 transiciones; axe en oscuro sin contraste. | `/private/tmp/claude-501/-Users-matos-workspace-Auphere-auphere-admin--claude-worktrees-047-recorrido-ui-9dd3dd/96b90021-1452-42f1-b89c-74036c885bdb/scratchpad/shots/console/marta/lite-agentes-375.png` |

## Arreglos (cada uno con su prueba, en rojo primero)

| # | Qué estaba mal | Dónde | Prueba |
|---|---|---|---|
| 1 | **Bloqueante.** La puerta exige que una persona decida el aviso de IA y la pantalla del agente no tenía dónde: ningún agente nuevo podía guardarse para atender. Bloque «Aviso de IA» (en el primer mensaje o si le preguntan, con sus palabras), y «Arreglar en el borrador» lo abre | `components/builder/block-editor.tsx`, `block-view.tsx`, `agent-builder.tsx`, `builder-model.ts`, `builder-types.ts`, `i18n/lanes/builder.ts` | `agent-builder.test.tsx` (2), `builder-model.test.ts` |
| 2 | 500 al guardar una respuesta de negocio del constructor en un cliente sin ficha (`NoBusinessProfile`) | `services/business/profile_edits.py` (`update_policies` estrena la ficha como `update_basics`) | `test_agent_draft_job.py::test_a_business_answer_for_a_client_without_ficha_opens_its_ficha` |
| 3 | La campana avisaba «se ha quedado sin saldo» de clientes con la bolsa llena: la red de seguridad del cron seguía el cupo de la consola de hoy | `services/wallet_alerts.py` | `test_wallet_alerts.py::test_with_bags_the_safety_net_of_today_says_nothing` |
| 4 | Negocio a 375 px medía 435 px (estado `sr-only` absoluto fuera de la tira) | `business/sections/business-sections.tsx` | `business-page.test.tsx` |
| 5 | Conectores del agente listaba WhatsApp y TikTok como «Sin conectar» (son canales; logos 404) | `api/console/agent_integrations.py` (`channel_only`) | `test_activations.py::test_the_agent_catalog_leaves_out_the_channels` |
| 6 | «Integraciones» en Auditoría (categoría y tres frases) y «Integraciones que pide» | `api/console/audit.py`, `agent_publish.py`, migración `0203_audit_vocab_connectors` | `test_audit_047.py` (2) |
| 7 | Las migas del cliente decían la referencia («flor-y-encanto») | `clients/v2/client-header-v2.tsx` | `client-header-v2.test.tsx` |
| 8 | La cabecera del agente seguía «Borrador» tras guardar | `builder/agent-builder.tsx` (relee `agentHeaderAction`) | `agent-builder.test.tsx` |
| 9 | Error de hidratación del editor de turnos (ids con un contador de módulo) | `business/sections/shift-editor.tsx` | `shift-editor.test.tsx` |
| 10 | Error de hidratación de la beta «WhatsApp login» (nombres de país distintos en Node y en el navegador) | `admin/…/whatsapp-login/{countries.ts,login-beta-view.tsx,page.tsx}` | `login-beta.test.tsx` |
| 11 | Servicios: 4 iconos por fila (regla de los tres puntos) | `business/sections/services-section.tsx`, `i18n/lanes/business.ts` | `services-section.test.tsx` (3) |
| 12 | Fecha especial sin «Desde»: «La fecha final no puede ser anterior a la inicial» | `business/sections/special-dates-section.tsx`, ES/EN | `special-dates-section.test.tsx` (3, la prueba de interacción que faltaba) |
| 13 | Historial: «Cambió: … mode, schema_version, test_suite» | `builder/agent-history.tsx` | `agent-history.test.tsx` |
| 14 | Historial del canal: «console:luis@…» | `builder/channel-page.tsx` (`cleanActor` compartido) | `channel-page.test.tsx` (el fixture ya lleva la forma real de la API) |
| 15 | Calidad: «En el borrador: nexus/current-binding» como si cambiara algo | `builder/model-quality-model.ts` | `model-quality-model.test.ts` |
| 16 | «Corregir esta respuesta»: el aviso de la paráfrasis salía dos veces | `inbox/correction-dialog.tsx` | `correction-dialog.test.tsx` |
| 17 | Vacíos de solo lectura sin `readonly` (el aviso de desarrollo del sistema de diseño, lo que axe marcaba como contraste) | admin: certificaciones, modelos, router, anomalías · consola: lista de clientes | `router-screens.test.tsx` |
| 18 | Punto y coma y «integración» en textos de la 047 del admin | ficha del conector, soberana, tope y moneda, pruebas del sector | `copy-047.test.ts` |
| 19 | La gráfica de bloques vacía era una caja deslizable sin nada enfocable (axe `scrollable-region-focusable`, serio, en la pantalla de un agente con poco uso) | `packages/ui/src/components/block-chart.tsx` | `block-chart.test.tsx` |
| 20 | La semilla dejaba los agentes en `draft` y sin agente por defecto (no se podía pasar un número ni probar el por defecto) | `scripts/dev_seed_fabrica.py` (como la 0190; repetible) | `test_dev_seed_fabrica.py` |

Documentación al día: `docs/agentes.md` (el aviso de IA), `docs/console.md`
(Conectores sin canales; vocabulario 0203) y `docs/billing.md` (la red de seguridad
con bolsas).

## Defectos abiertos (no arreglados aquí)

- **Contraste en oscuro de `text-primary-deep`** (admin: «Ver todas», «Abrir» en la
  ficha del cliente, 2,26:1). El token oscuro tiene el mismo valor desde antes de la
  047; cambiarlo es global. Propuesta: los enlaces usan `text-primary-text` (8:1 en
  oscuro). Media.
- **Bandeja de la lite: error técnico crudo** en un mensaje no enviado («No se envió:
  LookupError: no Meta credentials…»). Texto de la spec 030 (8-oct). Media.
- **Admin `/connectors`**: axe `list` y contraste del icono de Amigable Venta;
  término «Capacidades» en la ficha del conector; login del panel con nombres por
  placeholder. Anteriores a la 047. Baja.
- **Marco de acceso**: «CONSOLA DE PARTNERS» en «No puedes entrar» a una persona
  del cliente. Anterior a la 047. Baja.
- **Panel de hoy**: `aria-label` sobre un `<p>` en la cifra grande (axe
  `aria-prohibited-attr`), visible para el rol de facturación. Anterior a la 047. Baja.
- **Router (admin)**: valores de razonamiento crudos (`none/low/medium/high`). Baja.
- **Huecos de la API ya anotados en `progreso.md`** que se vieron: comprar saldo en
  dólares con la cuenta en euros (`billing/credit` solo USD); conectores sin estados
  «Pendiente»/«Próximamente».

## Fronteras externas (hasta donde se llega en local)

Conectar WhatsApp (Embedded Signup, coexistencia, enlace del dueño en un teléfono),
enviar a Meta (los envíos quedan «No se envió»), OAuth y claves de conectores
(Composio), Stripe (tarjeta y cobro), modelos reales (borrador en < 30 s, juez,
calibración, evaluación del constructor, paráfrasis, sugerencias semanales, precios
de Calidad: ningún despliegue certificado en local, D44).

## Ruido de desarrollo (no son defectos del producto)

- La CSP bloquea el chunk de `loading.tsx` en `next dev` (anterior a la 047). Con él
  bloqueado, una redirección por permisos (Facturación como admin/builder/analyst, API
  como analyst o billing) pinta en consola «Rendered more hooks than during the
  previous render» dentro del `Router` de Next; el destino final es el correcto.
- El indicador «N» de Next tapa el avatar del menú en la esquina.

## Decisiones que esperan a Andrés

1. **Facturación ve el Panel de hoy.** Sin `clients:read` no recibe el bloque `panel`
   y ve «Saldo disponible 100,03 US$» con la cuenta en euros. ¿Qué Panel ve ese rol
   con la consola nueva? (Alta)
2. **«N agentes sin canal».** La regla 7.2 junta «Listo · sin canal» y «En prueba»: un
   número conectado con la audiencia sin elegir sale como «sin canal» y el arreglo
   dice «Conectar un canal». ¿Otra palabra o acción («Elegir a quién responde»)? (Media)
3. **«Resueltas sin persona»** cuenta conversaciones fuera de la audiencia que el
   agente nunca respondió. ¿Se excluyen? (Media)
4. **Moneda de la bolsa por defecto**: siempre USD (`deduce_settings` no recibe la
   moneda de la cuenta y los partners no tienen país). Un cliente español de una
   cuenta en euros nace con la bolsa en dólares. ¿La de la cuenta? (Media)
5. **«Quién lo ofrece»**: si todos los agentes atienden todos los servicios, «Solo
   algunos agentes» no deja quitar a ninguno ni explica dónde se cambia. (Media)
6. **El aviso de IA nuevo** ofrece «en el primer mensaje» y «solo si le preguntan».
   ¿Se ofrece también «No lo dice» (el esquema lo permite; la revisión solo avisa en
   la UE por «si le preguntan»)? ¿Las palabras del bloque valen? (Media)
7. **Clientes sin bolsa** (Panadería Prueba) no salen en «Saldo por cliente» de
   Consumo; solo su Panel ofrece «Asignar saldo». (Baja)
8. **Coherencia**: la lite dice «Principal» y la consola «Por defecto». (Baja)
9. **Datos básicos**: el país se escribe en ISO de dos letras (el alta usa un
   selector); el ejemplo de teléfono de la sede es +34 en un negocio de Chile;
   «Enseñado · 68 B» enseña bytes. (Baja)

## Qué bloquea darlo por listo

- Con los arreglos de esta rama, nada de lo recorrido en local impide terminar los
  flujos de la 047. Sin el arreglo 1 (aviso de IA), ningún agente nuevo de la consola
  nueva podía publicarse.
- Quedan las decisiones 1 a 6 y lo que solo se ve en staging (fronteras externas).

## Pruebas corridas (verify.sh de lo tocado)

- **API**: `ruff check` y `ruff format --check` en verde; `mypy --strict` de los cinco
  módulos tocados, sin errores. Pytest de lo tocado (`builder/test_agent_draft_job`,
  `test_publish_gate`, `connectors/`, `clients/test_audit_047`, `business/`,
  `wallet/`, `test_wallet_alerts`, `test_dev_seed_fabrica`,
  `unit/test_console_audit_vocab_016`): 189 en verde y 2 errores de preparación por
  tiempo agotado con la máquina cargada (`test_admin_catalog`), en verde a solas (9).
  Migración: una sola cabeza, `0203_audit_vocab_connectors`.
- **Aislamiento**: la suite completa no cabe en esta máquina con el stack arriba (16 %
  en 50 min) y se paró. Se corrió lo ligado a lo tocado (`test_45*`,
  `test_console_scope`): 1.630 en verde. **Falta la suite completa antes de
  fusionar.**
- **Consola**: `tsc` y `eslint` en verde, `check:no-admin-token` en verde. Vitest
  entera: 1.515 en verde y 38 en rojo con dos pytest a la vez (36 tiempos agotados de
  5 s, un error no controlado de Reservas, ajeno, y un `toBeEnabled`). Los 18
  archivos repetidos a solas: en verde.
- **Panel**: `eslint --max-warnings 0` en verde. `tsc` y la vitest de
  `components/qa/__tests__/resume.test.tsx` fallan por los paquetes
  `@nexus/ucm-preview-whatsapp` y `@nexus/ucm-render-web`, que no están en este
  worktree (ajeno a estos cambios). Vitest: 322 en verde; los 4 archivos que agotaron
  tiempo, en verde a solas.
- **@nexus/ui**: `typecheck`, `lint` y `block-chart.test.tsx` en verde.
- `apps/admin/tsconfig.tsbuildinfo` y `next-env.d.ts` revertidos.
