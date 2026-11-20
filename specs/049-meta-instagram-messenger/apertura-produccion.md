# Apertura de Instagram y Messenger en producción

Spec 049, fase 7 ([tasks.md](tasks.md), T060 a T066). Escrito el 2026-11-20.

**Decisiones del owner (2026-11-20):**
- Abrir los dos canales **a todos los partners a la vez**, no partner a partner.
- La prueba de Human Agent pasadas 24 horas **no bloquea** la apertura.

## Lo que aprobó Meta

Solicitud enviada el 2026-11-03, **aprobada el 2026-11-19**. La app está publicada.

| Permiso o función | Para qué lo usa Auphere | Configuración que lo pide |
|---|---|---|
| `instagram_basic` | Identificar la cuenta conectada y su usuario | Instagram |
| `instagram_manage_messages` | Recibir y responder DMs | Instagram |
| `instagram_manage_comments` | Respuesta pública bajo un comentario | Instagram |
| `pages_messaging` | Recibir y responder en Messenger, y la respuesta privada a un comentario de la Página | Las dos |
| `pages_manage_metadata` | Suscribir y desuscribir la Página a los webhooks | Las dos |
| `pages_show_list` | Elegir la Página al conectar | Las dos |
| `pages_read_engagement` | Nombre de la Página y la publicación comentada | Las dos |
| `pages_read_user_content` | Leer el texto de un comentario de la Página | Messenger |
| `pages_manage_engagement` | Respuesta pública bajo un comentario de la Página | Messenger |
| `business_management` | Activos del portfolio del negocio | Messenger |
| `catalog_management` | Catálogo de WhatsApp | WhatsApp + catálogo |
| Human Agent | Una persona responde hasta 7 días después | Función de la app |
| Business Asset User Profile Access | Nombre y foto del contacto en la Bandeja | Función de la app |

Configuraciones: Instagram `1157578836735566` y «Auphere Messenger» `2188508105420190`. Ninguna pide publicar contenido ni anuncios.

## Pasos, en orden

Terraform se lanza siempre desde el checkout principal, `/Users/lmatos/Workspace/nexus`: es el único iniciado con el backend S3 (el bloque `backend "s3"` de `versions.tf` solo lleva la clave). El worktree de esta rama no lo está.

### 1. Commits y subida a `develop`

Dos ramas, una detrás de otra: `049-apertura-meta-social` (sus tres commits ya están hechos) y `049-requisito-7`, sacada de la anterior, con el requisito 7 (T067 y T068). Se sube **solo desde la segunda**: lleva los seis commits.

```bash
bash /Users/lmatos/Workspace/nexus/.claude/commits/2026-11-20-049-requisito-7.sh
cd /Users/lmatos/Workspace/nexus/.claude/worktrees/049-requisito-7
git fetch origin && git rebase origin/develop && git push origin HEAD:develop
```

`develop` se mueve a menudo (la sesión de la 065 sube a la vez). Los commits que llegaron el 2026-11-20 por la tarde no tocan ningún fichero de estas dos ramas, así que el `rebase` es limpio. `deploy-staging` despliega los servicios y Vercel publica la consola de `develop` en `console.staging.auphere.com`. Las task definitions no cambian hasta el paso 2.

### 2. Staging: aplicar las variables

```bash
cd /Users/lmatos/Workspace/nexus
git switch develop && git pull
terraform -chdir=infra/terraform/20-services workspace select staging
terraform -chdir=infra/terraform/20-services plan -var-file=staging.tfvars -out=staging.plan
terraform -chdir=infra/terraform/20-services apply staging.plan
```

El plan solo debe cambiar las task definitions y los servicios que las usan. Si trae también `LITELLM_LOCAL_MODEL_COST_MAP`, es de la spec 065 y ya está en `taskdefs.tf`: avisar a quien lleve la 065 para no aplicar dos veces. Cualquier otra cosa, parar. El `apply` rueda los servicios: `services.tf` apunta cada uno a la última revisión de su task definition.

Comprobar:
- Panel de staging → Partners → cualquier partner → Módulos: «Meta ya aprobó Instagram y Messenger: todos los partners los tienen».
- Consola de staging → un canal de Instagram: los textos nuevos (sin modo de prueba, borrado a los 30 días al desconectar, «Pasar el canal», y que los avisos por WhatsApp no pueden salir si staging no tiene número de avisos de Auphere).

### 3. Staging: conectar con un Facebook sin rol

Con una cuenta de Facebook que no sea administradora, desarrolladora ni evaluadora de la app, conectar una cuenta de Instagram profesional y una Página desde la consola de staging. Antes, una vez: abrir la conexión, pulsar «Cancelar» en la consola sin cerrar la ventana de Meta, y volver a conectar hasta el final (requisito 7.2: el SDK de Meta real todavía tiene abierto el primer intento, y eso solo se ve en vivo). La app de Meta y sus dos configuraciones son las mismas que usa producción, así que es la prueba de que el acceso avanzado funciona, y la puerta del paso 6. Si Meta no muestra los permisos o la conexión acaba sin cuentas, mirar `meta_social.connect.source` en los registros.

### 4. Meta: webhooks de Página e Instagram a producción

Lo hace el owner, porque pide el **verify token de producción** (`NEXUS_META_WEBHOOK_VERIFY_TOKEN` del secreto `nexus/prod/app`). No se pega en el chat.

App Dashboard → «Conectar en WhatsApp» → Webhooks:
1. Objeto **Page** → URL `https://webhooks.auphere.com/webhook/meta`, el token de producción, «Verificar y guardar». Los 9 campos siguen suscritos.
2. Objeto **Instagram** → lo mismo. Los 8 campos siguen suscritos.
3. **No tocar** el objeto WhatsApp Business Account.

Por qué: hoy apuntan a `https://api.staging.auphere.com/webhook/meta` ([07-webhooks-a-staging.md](../../docs/qa-canales-meta-2026-10-30/07-webhooks-a-staging.md)). Producción solo recibe lo que staging le reenvía, y deja de recibirlo si staging está aparcado o caído.

Comprobar: un DM a la cuenta de staging sigue llegando a staging, ahora reenviado por producción (`webhook.meta_social.forwarded` en los registros de la API de producción).

### 5. Los textos a producción: `develop` → `main`

Un PR de `develop` a `main` con los textos (T065) y las enmiendas T067 y T068. Al fusionar, `deploy-prod` rueda los servicios y Vercel publica la consola de `main` en `console.auphere.com`: son dos despliegues distintos, y hacen falta los dos. Puerta del paso 6: `deploy-prod` en verde y, en `console.auphere.com`, el diálogo de desconectar de un canal de Instagram o Messenger dice que los mensajes se borran a los 30 días.

### 6. Producción: aplicar las variables

Con el paso 3 bien, el paso 5 publicado y **ningún despliegue en marcha**:

```bash
cd /Users/lmatos/Workspace/nexus
git switch main && git pull
terraform -chdir=infra/terraform/20-services workspace select prod
terraform -chdir=infra/terraform/20-services plan -var-file=prod.tfvars -out=prod.plan
terraform -chdir=infra/terraform/20-services apply prod.plan
```

El plan debe cambiar solo las task definitions y sus servicios, con las dos variables de este guion (y `LITELLM_LOCAL_MODEL_COST_MAP` si la 065 aún no la aplicó: coordinarlo). Que `image_tag` siga siendo `prod`. Cualquier otra cosa, parar. El `apply` rueda los cinco servicios, y en ese momento Instagram y Messenger quedan abiertos a todos.

**Todo `apply` posterior en prod tiene que salir de un checkout con este cambio.** Uno sin él quita las dos variables: vuelve a esconder los canales y a cerrar Human Agent a 24 horas.

### 7. Human Agent

Primero en staging y después en producción. Hace falta una conversación cuyo último mensaje del contacto tenga entre 24 horas y 7 días: un DM hoy desde una cuenta de prueba a la cuenta y la Página de staging deja la prueba lista para después del paso 2. Antes de tomarla, el compositor dice que el agente ya no puede responder y que tú sí, con la fecha límite (requisito 7.3). «Tomar el control», responder y ver que llega. Si sale «No se envió: Meta todavía no permite responder pasadas 24 horas…», la bandera `NEXUS_META_HUMAN_AGENT_APPROVED` no está aplicada en el servicio que envía. En producción, igual, después del paso 6.

## Vuelta atrás

- **Cerrar los canales:** quitar las dos variables de `taskdefs.tf` y aplicar en el workspace afectado. Los canales ya conectados siguen funcionando: la bandera solo decide quién ve el botón de conectar.
- **Webhooks:** volver a poner la URL anterior con su token. Mientras tanto, cada entorno reenvía al otro lo que no es suyo.

## Enmiendas que van en el paso 5

Requisito 7 de [spec.md](spec.md), hecho el 2026-11-20 en la rama `049-requisito-7` (T067 y T068 en [tasks.md](tasks.md)). Llega a `main` con los textos:

- **T067 (7.1):** la página no promete avisos por WhatsApp si Auphere no tiene número de avisos. Enmienda también la 047 (requisito 33.3).
- **T068 (7.2 a 7.4):** «Cancelar» mientras la ventana de Meta está abierta, la Bandeja entre 24 horas y 7 días con Human Agent, y «Pasar el canal».

Las respuestas rápidas de Instagram se mantienen (decisión del owner, T066): queda actualizar su descripción en Meta.
