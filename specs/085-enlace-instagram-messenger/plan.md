# Plan de implementación: el enlace para que el cliente conecte Instagram y Messenger

**Rama**: `085-enlace-instagram-messenger` | **Fecha**: 2026-11-27 | **Spec**: [spec.md](spec.md)

**Entrada**: `specs/085-enlace-instagram-messenger/spec.md`, aclarada el 2026-11-27. Diseño en [research.md](research.md), [data-model.md](data-model.md), [contracts/owner-link-meta-social.md](contracts/owner-link-meta-social.md) y [quickstart.md](quickstart.md).

## Resumen

El enlace de WhatsApp (spec 040) se generaliza por canal y la página pública sirve también Instagram y Messenger, con la misma conexión que la consola (spec 049). Hay tres piezas nuevas pequeñas:
- dos llamadas públicas: conectar y completar la elección;
- `origin` en la elección pendiente, para que solo la complete quien la inició;
- una ruta de consola `connect/[kind]` para los dos canales.

Además se arreglan dos fallos que destapa el cambio:
- crear un enlace anula los de otros canales;
- un enlace de agente caducado sin anular rompe el siguiente.

## Contexto técnico

- **Lenguaje:** Python 3.11 (API y `apps/channels`, `uv`, `mypy --strict`) y TypeScript estricto (consola, Next.js 16 y React 19).
- **Dependencias:** FastAPI, SQLAlchemy async, Alembic, Redis y Fernet (las que ya existen). Ninguna nueva.
- **Almacenamiento:** Postgres, una migración (`0244`); Redis, el valor de la elección pendiente gana `origin`.
- **Pruebas:** pytest (unit, integration e isolation) con base propia; vitest en la consola. No hay e2e nueva: la validación con Meta real es manual en staging ([quickstart.md](quickstart.md)).
- **Plataforma:** la API en AWS (ECS) y la consola en Vercel.
- **Rendimiento:** no aplica. Conectar son unas 3 llamadas por token, dentro del límite de 10 por minuto.
- **Restricciones:** la página pública nunca pone el token en su dirección (040). La consola no guarda credenciales del backend (CLAUDE.md).

## Comprobación contra la constitución

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto | ☑ | El cliente lo decide el token y todo corre bajo `tenant_scoped_session`. Prueba nueva `tests/isolation/test_085_owner_link_meta_social_scope.py`; `test_console_scope.py` cubre solas las rutas nuevas. |
| II | Superficie de confianza | ☑ | `1`, la página pública de la 040. No se abre ninguna superficie: se añaden dos llamadas protegidas por el mismo token. |
| III | Lo leído es dato | ☑ | Los nombres de cuenta y Página que da Meta se muestran como texto y nunca se interpretan. |
| IV | Acción consecuente con humano | ☑ | El dueño decide en la ventana de Meta y en el diálogo. La auditoría nombra al enlace (`link:{id}`), como la 040. |
| V | La pantalla no miente; la ausencia se diseña | ☑ | Estados del enlace, motivos de Meta y «la elección caducó». Sin disponibilidad, la tarjeta no ofrece el enlace. |
| VI | Por API | ☑ | No aplica: no hay agente operando la consola. |
| VII | Test primero | ☑ | Cada requisito nace como prueba, y se ve en rojo antes de implementar (tasks.md). |
| VIII | Licencias | ☑ | Ninguna dependencia nueva. |
| IX | La KB es dueña del porqué | ☑ | `research/2026-11-26-beta-jemma-p0-p1.md`, «Enlace de conexión para Instagram y Messenger». |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantía 1 (separación entre negocios): el enlace solo conecta en su cliente, y una elección solo la completa quien la inició. | Prueba en `tests/isolation/test_085_owner_link_meta_social_scope.py` (tasks.md, fase de pruebas) |
| **Licencias** | Ninguna dependencia nueva | — |
| **Medidor** | Nada: no gasta modelo ni herramientas de pago | — |

## Estructura

### Documentación

```text
specs/085-enlace-instagram-messenger/
├── spec.md, plan.md, research.md, data-model.md, quickstart.md
├── contracts/owner-link-meta-social.md
├── checklists/requirements.md
└── tasks.md            (/speckit-tasks)
```

### Código que cambia

```text
apps/api/alembic/versions/0244_owner_links_meta_social.py           nueva
apps/api/src/nexus_api/db/models/channel_signup_link.py             modos y canales
apps/api/src/nexus_api/services/channel_signup_links.py             mint por canal, link_url por canal,
                                                                   connect_meta_social_with_link (conectar y completar)
apps/api/src/nexus_api/api/console/channel_signup.py                info por canal, dos rutas públicas nuevas,
                                                                   409 link_channel_mismatch en la de WhatsApp
apps/api/src/nexus_api/api/console/meta_social.py                   POST /{kind}/signup-link
apps/api/src/nexus_api/api/console/whatsapp.py                      la lista de enlaces devuelve channel
apps/api/src/nexus_api/api/console/channel_config.py                OwnerLinkIn.channel, pending_links
apps/api/src/nexus_api/services/meta_social_service.py              (si hace falta) la conexión con origin
apps/channels/src/nexus_channels/meta_social/connect.py             origin en begin y complete
(el servicio de colocar un canal en un agente)                       extraer la parte que trabaja con la sesión
                                                                   si depende del ClientScope (R6)

apps/console/src/app/connect/[kind]/page.tsx                        nueva: Instagram y Messenger
apps/console/src/app/connect/[kind]/[token]/route.ts                nueva: cookie por canal y redirección
apps/console/src/app/connect/[kind]/actions.ts                      nueva: acciones del enlace
apps/console/src/app/connect/whatsapp/link-cookie.ts                nombre de cookie por canal
apps/console/src/components/channels/meta-social-connect.tsx        acciones inyectadas (R9)
apps/console/src/components/channels/whatsapp-share-link.tsx        panel por canal (R10)
apps/console/src/components/channels/pending-signup-links.tsx       canal de cada enlace
apps/console/src/components/builder/owner-link-panel.tsx            channel
apps/console/src/app/(console)/clients/[ref]/channels/*             botón en Instagram y Messenger, acciones nuevas
apps/console/src/lib/backend.ts                                     las dos llamadas públicas y el mint por canal
apps/console/src/i18n/lanes/channels.ts                             connect.social.*, ch.link.* por canal
docs/                                                              el documento del enlace del dueño
```

## Complejidad que hay que justificar

| Qué | Por qué | Lo más sencillo, descartado |
|---|---|---|
| `origin` en la elección pendiente (paquete `apps/channels`) | El requisito 7.3: la elección solo la completa quien la inició | Una clave de Redis aparte por enlace: un segundo sitio que mantener |
| El índice de pendientes por agente y canal, y anular caducados | Sin esto, un agente no puede tener WhatsApp e Instagram pendientes, y un enlace caducado hace fallar el siguiente con un 500 (ya pasa) | Dejarlo: rompería el requisito 1.2 en el agente |
| Crear un enlace solo anula los de su canal | Un enlace de Instagram mataría uno de WhatsApp pendiente | — |
