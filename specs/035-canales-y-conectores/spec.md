# Especificación: Canales y Conectores, separados y ordenados como Chatwoot

**Rama**: `035-canales-y-conectores` · **Creada**: 2026-10-19 · **Estado**: Aprobada para plan

**Entrada**: owner, 2026-10-19 — «En el Admin necesitamos que en canales estén los
productos de mensajería y comunicación (Instagram, TikTok, WhatsApp, Telegram, X,
Threads) y en conectores irá todo lo demás. Analiza la vista de conectores y la de
canales de Chatwoot y mejoremos las de Auphere». Decisiones del mismo día: el catálogo de
Canales del admin muestra **los seis, con su estado**; la ronda lleva la estructura
**completa** (asistente, lista, detalle por pestañas, vista global; cuadrícula de
conectores con detalle).

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — panel de operador y API de admin. No se abre ningún canal nuevo: los que no existen se enseñan como «Próximamente» y no se pueden conectar |
| **Garantías de aislamiento tocadas** | **1** — las vistas globales leen `channels` y `tenant_connectors` (RLS por tenant) **cliente a cliente con su GUC** (`tenant_scoped_session`), nunca levantando la RLS. Prueba en `tests/integration/test_admin_channels_and_connectors.py` (cada fila sale etiquetada con su propio cliente) |
| **Nota de KB que la justifica** | `[[ADR-046-canales-y-conectores]]` · `[[ADR-029-tiktok-business-messaging-channel]]` · `[[whatsapp-connector/ADR-030-instagram-connector]]` |
| **Qué se mide** | Nada nuevo |

## Origen

Medido el 2026-10-19:
- La pestaña del cliente «Canales e integraciones» mezcla en 495 líneas los números de
  WhatsApp, TikTok, los conectores instalados y los disponibles. WhatsApp y TikTok viven
  en el catálogo de conectores (`channel_only`), lo que la consola ya separa y el admin no.
- El catálogo global de conectores es de solo lectura, agrupado por categorías con
  etiquetas en crudo (`billing`, `catalog`, `ecommerce`).
- Las excepciones por herramienta (`tool overrides`) existen en la API y en acciones del
  panel, pero **no tienen pantalla**.
- No hay una vista de todos los canales de todos los clientes.
- Canales en el backend: WhatsApp por Meta en producción; TikTok construido y apagado
  (`tiktok_enabled`, pendiente de la revisión de TikTok); Instagram con ADR y plan, sin
  código; Telegram, X y Threads sin nada.

Referencia: Chatwoot (`/Users/matos/workspace/chatwoot`): asistente «Elegir canal →
Crear bandeja → Añadir agentes → ¡Listo!» con rejilla de canales (Beta y «¡Muy
pronto!»), lista de bandejas con detalle por pestañas, e Integraciones como rejilla con
buscador, estado «Activado/Deshabilitado» y «Configurar».

## Clarifications

### Session 2026-10-19

- Q: ¿Cómo se muestran los canales que no existen? → A: **Todos, con estado** (owner). Solo en el panel interno: la consola de partners y la lite siguen sin enseñar lo que no existe. Se enmienda §V de la constitución para el panel de operador.
- Q: ¿Alcance? → A: **Completo** (owner): asistente, lista, detalle por pestañas y vista global en Canales; rejilla con buscador, estado y detalle en Conectores.
- Q: ¿Y los números de Auphere (backchannel)? → A: Son de la plataforma, no de un cliente: se quedan en Plataforma como «Números de Auphere».

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Conectar un canal a un cliente con el asistente (P1)

1. **Dado** un cliente, **cuando** el operador pulsa «Añadir canal», **entonces** ve el asistente con cuatro pasos (Elegir canal · Conectar · Asignar agente · ¡Listo!) y la rejilla de canales: WhatsApp disponible; TikTok «Beta» (o «Pendiente de TikTok» si está apagado); Instagram, Telegram, X y Threads «Próximamente», sin poder pulsarlos.
2. **Dado** WhatsApp, **cuando** lo elige, **entonces** elige el proveedor (registro integrado de Meta o número propio con System User) y conecta con los flujos que ya existen.
3. **Dado** un número conectado, **cuando** asigna el agente que lo atiende y termina, **entonces** ve «¡Listo!» con «Más ajustes» (detalle del canal) y «Probar envío».

### Historia 2 — Lista y detalle de canales del cliente (P1)

1. **Dado** un cliente con dos números, **cuando** abre Canales, **entonces** ve una fila por canal (icono, nombre, tipo · identificador, estado) y su acción «Configurar».
2. **Dado** un canal, **cuando** abre su detalle, **entonces** tiene pestañas Ajustes (línea del agente o de avisos, agente encendido), Agente (qué agente lo atiende), Plantillas (WhatsApp) y Salud (estado, última comprobación, envío de prueba).

### Historia 3 — Conectores del cliente como Chatwoot (P1)

1. **Dado** un cliente, **cuando** abre Conectores, **entonces** ve una rejilla con buscador; cada tarjeta tiene logo, nombre, estado («Activado», «Deshabilitado», «Requiere atención», «En pausa») y «Configurar». WhatsApp y TikTok no están: son canales.
2. **Dado** un conector, **cuando** abre «Configurar», **entonces** ve su ficha: estado, alcance, conectar o reconectar con su flujo, sincronizar, pausar, reanudar, desconectar, y **las excepciones por herramienta** (siempre · con aprobación · bloqueada) editables.

### Historia 4 — Vistas globales (P2)

1. **Dado** el sidebar, **cuando** se lee Plataforma, **entonces** dice Canales · Conectores · Números de Auphere · Playground QA.
2. **Dado** Canales global, **cuando** se abre, **entonces** lista todos los canales de todos los clientes (cliente, partner, canal, identificador, estado, papel) con buscador y filtros, y el catálogo con el estado de cada canal.
3. **Dado** Conectores global, **cuando** se abre, **entonces** ve la rejilla del catálogo con buscador, categoría en palabras y cuántos clientes lo tienen; su ficha lista esos clientes.

## Requisitos *(obligatorio)*

### Requisito 1 — Catálogo de canales

1. La API DEBE exponer un catálogo de canales (`GET /admin/channel-catalog`): WhatsApp, TikTok, Instagram, Telegram, X, Threads, con nombre, descripción y disponibilidad (`available`, `beta`, `pending`, `coming_soon`) calculada en el servidor.
2. TikTok DEBE ser `beta` con `tiktok_enabled` y `pending` sin él.
3. WHERE un canal no es `available` ni `beta` EL panel NO DEBE permitir iniciarlo.

### Requisito 2 — Canales del cliente

1. La ficha del cliente DEBE tener las pestañas «Canales» y «Conectores» en lugar de «Canales e integraciones».
2. «Añadir canal» DEBE abrir un asistente de cuatro pasos con la rejilla del catálogo.
3. Cada canal DEBE tener un detalle con pestañas Ajustes, Agente, Plantillas (solo WhatsApp) y Salud.

### Requisito 3 — Conectores del cliente

1. La pestaña Conectores NO DEBE incluir conectores `channel_only`.
2. Cada tarjeta DEBE mostrar el estado en palabras y llevar a la ficha del conector.
3. La ficha DEBE permitir editar las excepciones por herramienta (siempre, con aprobación, bloqueada) y volver a lo heredado.

### Requisito 4 — Vistas globales

1. `GET /admin/channels` DEBE listar los canales de todos los clientes leyendo cada cliente con su GUC, sin los canales internos del Playground.
2. `GET /admin/connectors-installs` DEBE decir qué clientes tienen cada conector, leyendo igual.
3. El sidebar DEBE mostrar Plataforma: Canales, Conectores, Números de Auphere, Playground QA.

### Requisito 5 — Constitución

1. §V DEBE decir que el panel de operador puede enseñar en un catálogo lo que viene, marcado «Próximamente» y sin poder iniciarse, y que la consola de partners y la lite no.

## Criterios de éxito

- **CE-001**: conectar un WhatsApp a un cliente se hace desde un asistente de cuatro pasos, sin buscar en una página larga.
- **CE-002**: las excepciones por herramienta se editan desde el panel por primera vez.
- **CE-003**: desde Canales global se encuentra cualquier número de cualquier cliente en un buscador.

## Fuera de alcance

- Construir Instagram, Telegram, X o Threads — una spec por canal (Instagram tiene ADR y plan).
- Encender TikTok — depende de la revisión de TikTok.
- Cambiar la consola de partners — ya separa Canales y Conectores.
