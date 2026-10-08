# Research: la consola lite

Medido en el código de `develop` @ `6c7b9857` el 2026-10-08. Cada decisión del
[plan](plan.md) con su razón y lo que se descartó.

## R1 · ¿Dónde vive el usuario de cliente? → tablas propias (D1)

- **Hecho.** `partner_memberships` es única por `user_id` (una cuenta, un
  partner), sin columna de cliente, con CHECK de cinco roles. La consola
  recorre los miembros del partner en Equipo (`api/console/team.py`), en el
  envío de correos de avisos de severidad ≥ warning y en los límites de plazas
  por nivel.
- **Decisión.** `client_memberships` y `client_invitations`, hermanas de las
  del partner.
- **Por qué.** `require_console_principal` resuelve solo contra
  `partner_memberships`: un usuario de cliente recibe 403 en todas las rutas del
  partner **sin tocar ninguna**. Y los recorridos de miembros del partner no
  pueden incluirlo por error.
- **Descartado.** Rol `client` + `tenant_id` en `partner_memberships`: menos
  tablas, pero cada recorrido existente tendría que excluirlo, y la constitución
  §I ya cuenta qué pasa con el sitio que no se miró.

## R2 · ¿Cómo se autoriza? → dependencia propia y el mismo token (D2, D3)

- **Hecho.** `require_console_principal(*perms)` comprueba firma, `jti`,
  membresía activa, partner activo y `console_enabled`, y toma el rol de la
  fila. Sin permisos declarados, cualquier miembro pasa.
- **Decisión.** `require_client_principal(*modules)` con los mismos pasos
  criptográficos y su propia resolución; el token es el mismo
  (`role: "client"`).
- **Por qué.** El partner nunca alcanza una ruta lite (no está en
  `client_memberships`) y el cliente nunca una del partner (no está en
  `partner_memberships`). La frontera no depende de que alguien declare bien
  un permiso.
- **Descartado.** Permisos `lite:*` en el mapa `PERMISSIONS` de roles: mezcla
  los dos mundos en una tabla y deja la frontera a merced de una fila.

## R3 · ¿Qué pasa con C8? → rutas propias con excepción escrita (D5)

- **Hecho.** `tests/isolation/test_console_scope.py` recorre el OpenAPI de
  `/console/*` y falla si un esquema de respuesta tiene campos de cuerpo
  (`content`, `text`, `body`, `messages`…); el Companion tiene su excepción
  escrita (líneas 63-78).
- **Decisión.** La Bandeja vive bajo `/console/lite/inbox/*` y la excepción se
  escribe para ese prefijo, razonada como la del Companion. Un barrido nuevo
  comprueba que ninguna persona del partner alcanza esas rutas.

## R4 · Panel y Consumo con las mismas cifras (D8–D10)

- **Hecho.** `GET /console/home` carga todos los clientes del partner y llama a
  `tenant_snapshots(tenant_ids)`, `credit_burn(partner, tenant_ids, since)` y
  `allocations_for(...)`, que ya aceptan una lista. `/console/usage/spend`
  admite `client=` y excluye el gasto fuera de clientes al elegir uno.
  `/console/usage` calcula su bloque `month` sobre toda la cartera.
- **Decisión.** Servicios `lite_home` y `lite_usage` que llaman a esas mismas
  funciones con `[tenant_id]`; lo que hoy vive dentro del endpoint del partner
  se extrae sin cambiar su respuesta.
- **Riesgo.** Doble débito del tope por cliente (`debit_wallet` +
  `debit_allocation`; `credit_burn` suma ambos asientos). Propuesto aparte por
  el flujo de bug; bloquea abrir Consumo lite a un cliente real.

## R5 · El ciclo de vida de una conversación (D11–D13)

- **Hecho.** `upsert_conversation_for_customer` busca solo `OPEN`. El único que
  escribe `ESCALATED` es `escalate.escalate_to_human` (MCP), que no silencia al
  agente y deja el motivo solo en `audit_log`. `CLOSED` no lo escribe nadie.
  `agent_active = false` ya hace que el despachador guarde el mensaje y no
  invoque al agente; al reanudar, el `takeover_context` se convierte en un
  resumen para el modelo y se limpia.
- **Decisión.** El alta toma la última fila del contacto en ese número y
  reabre `CLOSED`. El escalado pasa por `mark_waiting`, que silencia al agente
  solo si el cliente tiene Bandeja (clarificación del owner).
- **Descartado.** Agrupar en la Bandeja las filas huérfanas por contacto: no
  arregla que el agente siga hablando en la fila nueva tras escalar.

## R6 · Tiempo real (D17)

- **Hecho.** `services/conversation_stream.py` publica `agent.toggled` y
  `message.new`, solo desde el admin; el worker no publica nada aunque su
  docstring diga lo contrario. Las SSE del admin y del Playground ya se pasan
  por la BFF.
- **Decisión.** Canal por tenant `inbox:{tenant_id}`; el worker publica al
  guardar mensajes; SSE lite con sondeo de respaldo.
- **Descartado.** Solo sondeo: más simple, pero 5 s (CE-004) a costa de
  consultas continuas por persona conectada.

## R7 · Archivos (D15, D16)

- **Hecho.** Los entrantes se guardan en S3 (`inbound/{tenant}/…`) y
  `MessageOut` oculta la clave. El adaptador de Meta envía archivos por enlace
  firmado. `OperatorSendIn` es solo texto y `MediaStorage.put_outbound` no tiene
  llamante. La ventana de 24 h no se comprueba antes de enviar: Meta responde
  131047 y la fila queda fallida.
- **Decisión.** Subida a S3 desde la API, envío por el despachador de siempre;
  la ventana se comprueba antes de aceptar el envío. Los archivos se sirven por
  streaming a través de la BFF.

## R8 · Varios agentes (D22–D27)

- **Hecho.** Diez supuestos de un agente por cliente: dos búsquedas
  independientes de la versión activa (webhook y despachador) más
  `get_active()` en el cargador; caché e invalidación por tenant; versiones
  contadas por tenant; ninguna relación número → agente
  (`agent_configs.channels` se copia y no se lee); sin agente en
  conversaciones, mensajes ni hilo de LangGraph; modelo, conocimiento y grafo
  por tenant; `usage_records.agent_config_id` como única dimensión, que es una
  versión; URLs de consola y admin sin agente; un solo borrador.
- **Decisión (owner).** Un número es de un solo agente y un agente puede tener
  varios números: el enrutado sale del número, sin clasificador ni traspaso
  entre agentes. Configuración con el editor de siempre.
- **Por qué así.** Resolver el agente por el número es una búsqueda por clave en
  el camino que ya existe; no añade llamadas al modelo ni decisiones que
  evaluar. El hilo de LangGraph (`tenant:channel:user`) queda naturalmente por
  agente porque el número lo es.
- **Descartado.** Agente de entrada con traspaso por herramienta, y
  clasificador por intención: el owner los descartó («un WhatsApp no va a tener
  más de un agente»).

## R9 · Admin e identidad del operador (D6)

- **Hecho.** El admin llama a la API con `NEXUS_ADMIN_TOKEN` estático; la
  auditoría de acciones de partner pone `admin:<8 primeros del token>`, que no
  identifica a nadie. La identidad del operador viaja en `X-Operator-Id`
  (ADR-034) para la suplantación. No hay pantallas de personas ni invitaciones.
  El admin no usa `@nexus/ui`: tiene su shadcn con `Checkbox` y sin `Switch`.
- **Decisión.** Endpoints nuevos que exigen operador identificado y auditan
  `operator:<correo>`; la pestaña usa los componentes del admin.
