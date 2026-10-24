# Especificación: un alta que termina en un agente que responde

**Rama**: `030-alta-de-clientes` → PR a `develop` (staging) · **Creada**: 2026-10-24 · **Estado**: Aprobada (decisiones del owner del 2026-10-24)

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola y worker. Nada nuevo entra de fuera |
| **Garantías de aislamiento tocadas** | **1** (RLS): el endpoint de agente por canal y el catálogo leen solo el cliente del partner (`client_scope`). Sin regla nueva |
| **Nota de KB que la justifica** | Doc «QA del alta de clientes» (https://claude.ai/artifact/FALFnWJWrifpxYDME724hK) · `[[sessions/2026-10-24-qa-alta-de-clientes]]` |
| **Qué se mide** | Nada nuevo. Se mide el resultado: % de mensajes respondidos de clientes activos (hoy 2,6 %) |

## Origen

QA del 2026-10-24 sobre producción. En 21 días llegaron 11.526 mensajes a
números conectados y el agente respondió 299 (2,6 %). Cuatro bloqueos que la
consola no enseña explican el 93 % del silencio (línea «solo avisos» 39,9 %,
cliente sin agente 25,5 %, sin saldo 15,1 %, «solo responde a N números»
13,0 %). El asistente promete «tres pasos» y quedan siete en cinco pantallas.
El owner pide un alta que un joven de 15 y un adulto de 65 completen con una
guía corta, y conectar canales en la consola como en el panel de Admin.

## Decisiones del owner (2026-10-24)

1. **Saldo**: como hoy. El cliente nace en 0 y se asigna en Consumo. Sí se
   arregla que el camino no pierda el cliente y que el silencio se vea.
2. **Modo prueba**: sí. Durante el alta el agente responde solo al número del
   partner hasta pulsar «Encender».
3. **Plantillas**: 6 grupos con nombres de negocio y «Otro».
4. **Catálogo de canales**: la consola enseña también «Próximamente» y
   «Pendiente», sin poder iniciarse (enmienda 1.2.0 de la constitución, §V).
5. **Flujo**: rama + PR a `develop`; staging antes de producción.

## Escenarios *(obligatorio)*

1. **Conectar un canal como en Admin** (P1): en la ficha, «Añadir canal» abre un
   asistente de cuatro pasos (Elegir canal → Conectar → Asignar agente →
   ¡Listo!). Paso 1: tarjetas de canal con su logo; WhatsApp se puede iniciar,
   TikTok, Instagram, Telegram, X y Threads se ven con su estado y no se pueden
   iniciar. Paso 2: conectar WhatsApp uno mismo o mandar el enlace al dueño, con
   una pregunta en vez de «Cloud API / Coexistencia». Paso 3: qué agente
   atiende el canal y si conversa o solo envía avisos. Paso 4: listo, con
   «escríbele desde tu teléfono» y los pasos que falten para que responda.
2. **Ningún cliente mudo sin saberlo** (P1): todo mensaje que no se responde se
   guarda con su motivo; la ficha dice «Por qué no responde» con el arreglo; no
   se puede activar un cliente que no puede responder.
3. **Encender tu agente** (P2): un recorrido de cinco pasos (Tu negocio → Lo que
   sabe → Pruébalo → WhatsApp → Encender) con modo prueba, reanudable desde la
   ficha.
4. **El Companion lo hace contigo** (P3): propone encender, mandar el enlace de
   WhatsApp y elegir a quién responde.

## Requisitos *(obligatorio)*

1. `GET /console/channel-catalog` devuelve el catálogo con textos para el
   partner (sin referencias internas como ADRs o «API de Meta»).
2. `PUT /console/clients/{ref}/channels/{id}/agent` asigna el agente que
   atiende un canal, dentro del cliente del partner (404 opaco fuera).
3. Ningún motivo de silencio deja de guardar el mensaje entrante; todos dejan
   `skipped_reason`.
4. Activar exige agente publicado (también desde Archivado), un canal que
   conversa y saldo; el error lleva un `code` que la consola traduce.
5. Un canal con calidad amarilla o roja sigue recibiendo mensajes.
6. Reconectar un número conserva su rol, si conversa y su catálogo.
7. Nada en la consola enseña créditos; los plurales son correctos; una pestaña
   no marca incidencia sin incidencia.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un partner conecta WhatsApp desde la consola sin ayuda en menos de
  5 minutos (sin contar los pasos de Meta).
- **CE-002**: cero mensajes entrantes sin guardar por falta de saldo.
- **CE-003**: un joven y un adulto mayor completan el alta con una guía de una
  página en menos de 15 minutos sin preguntar (iteración 2).
- **CE-004**: el % de mensajes respondidos de clientes activos sube semana a
  semana desde el 2,6 %.

## Fuera de alcance

- Construir Instagram, Telegram, X o Threads: solo se enseñan como «Próximamente».
- Cambiar quién asigna el saldo (decisión 1).
