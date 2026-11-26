# Especificación: Instagram con su Página, para que lleguen los mensajes directos

**Rama**: `hotfix/081-instagram-con-pagina` · **Creada**: 2026-11-26 · **Estado**: Hotfix P0, spec retroactiva (excepción §2 de `docs/spec-driven-development.md`). Enmienda el requisito 8 de la spec 049.

**Entrada**: Gali Artist (partner ventas-argentina), cliente real en producción. Conectó Instagram el 2026-11-26 a las 19:00 UTC: el agente contesta los comentarios, pero no los mensajes directos. Luis, 2026-11-26: «Súbelo como hotfix porque es un cliente real». Antes había dicho: «No quiero quitar el inicio de sesión con Instagram, es requerido por los usuarios».

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | La conexión de Instagram de la consola de partners: la oferta de `GET /console/clients/{ref}/channels` (`meta_social`) y la ventana de Facebook Login for Business que abre la consola. No se abre ninguna ruta nueva. |
| **Garantías de aislamiento tocadas** | **Ninguna de las 7.** La conexión sigue igual: el token se canjea en el servidor y la cuenta se resuelve contra el tenant del ámbito. Solo cambia qué configuración de Meta abre la consola. |
| **Nota de KB que la justifica** | Ninguna: hotfix P0. |
| **Qué se mide** | Que llegue el evento `messages` de una cuenta conectada con la configuración nueva (`webhook.meta_social.enqueued` con `comment=false`). |

## Por qué

En producción, la cuenta de Gali recibe los eventos de `comments` y **ningún** evento de `messages`, ni siquiera el eco de nuestras respuestas privadas. Lo comprobado el 2026-11-26 con el token del canal:

- El token solo lleva `instagram_basic`, `instagram_manage_comments`, `instagram_manage_messages` y `public_profile`. La cuenta de Auphere, que sí recibe DMs, lleva además los permisos de Páginas.
- La suscripción de la cuenta (`subscribed_apps`) es idéntica en las dos e incluye `messages`.
- La API de conversaciones de Gali responde y muestra hilos de las 19:10 y las 19:20 UTC. «Permitir acceso a los mensajes» está encendido y los DMs existen en Meta.

La guía oficial de Meta, «Set up Instagram Webhooks», en su parte de Unified Login, lo explica:

- Si el negocio comparte la cuenta de Instagram **pero no la Página de Facebook vinculada**, pueden no llegar `messages`.
- La salida es una segunda configuración que pida la Página vinculada y `pages_show_list`. Esa configuración solo admite entrar con Facebook.
- Las cuentas sin Página vinculada no se ven afectadas.

«Auphere Instagram» (`29353122964304011`, requisito 8 de la 049) no puede pedir Páginas sin perder «entrar con Instagram». La 049 la dejó así a propósito, y su prueba de un DM con esa configuración (T072, paso 4) no se hizo.

El 2026-11-26 se creó en Meta «Auphere Instagram + Página» (`1468805387916611`):

- Token de usuario del sistema que no caduca.
- Activos obligatorios: Páginas y cuentas de Instagram.
- Permisos: `instagram_basic`, `instagram_manage_comments`, `instagram_manage_messages` y `pages_show_list`. Este último tiene acceso avanzado desde el 2026-11-19 (049, T051).

## Requisitos

### 1. Dos maneras de conectar Instagram

1.1 WHEN la API devuelve la oferta de Instagram THEN el sistema DEBE incluir la configuración de siempre (`config_id`, la que admite entrar con Instagram) y, si está configurada, la de la Página (`page_config_id`).

1.2 WHEN el negocio pulsa «Conectar Instagram» y la oferta trae `page_config_id` THEN la consola DEBE preguntar cómo entra, antes de abrir la ventana de Meta:
- **Con Facebook y la Página vinculada**, para la cuenta vinculada a una Página de Facebook. Es la que recibe los mensajes directos en ese caso.
- **Con Instagram**, para la cuenta que no tiene Página vinculada.

1.3 WHEN elige «Con Facebook y la Página» THEN la consola DEBE abrir la ventana con `page_config_id` y sin `prompt=login`.

1.4 WHEN elige «Con Instagram» THEN la consola DEBE abrir la ventana con `config_id` y `prompt=login`, como hasta ahora (049, R8).

1.5 WHEN la oferta no trae `page_config_id` THEN la consola DEBE abrir la ventana directamente con `config_id`, sin preguntar.

1.6 WHEN la conexión falla y el negocio pulsa «Intentar de nuevo» THEN la consola DEBE repetir la misma manera de entrar que eligió.

### 2. La conexión no cambia

2.1 El canje del código, la elección de cuenta, la suscripción de la cuenta (`POST /{ig-id}/subscribed_apps`) y la fila del canal son los de la 049. **No se suscribe la Página**: la de Auphere no tiene ninguna app suscrita y recibe DMs.

2.2 WHEN se reconecta una cuenta ya conectada en el mismo cliente THEN se actualiza su canal y su token, como en la 049.

## Fuera

- Saber de antemano si la cuenta de Instagram tiene Página vinculada. Meta no lo documenta, así que lo dice el negocio al elegir cómo entra.
- Comprobar con un DM de prueba, al terminar de conectar, que llega `messages`. Va en la enmienda de la 049.
- Avisar de una cuenta que recibe comentarios pero nunca mensajes. Va en la enmienda de la 049.
- Registrar los eventos `standby` (INC-23).
