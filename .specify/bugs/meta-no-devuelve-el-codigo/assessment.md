# Bug Assessment: Meta no devuelve el código

- **Slug**: meta-no-devuelve-el-codigo
- **Created**: 2026-09-23
- **Source**: recorrido de la spec 016 en staging con el owner (cliente
  `prueba-whatsapp-016`, partner Demo (staging))
- **Verdict**: valid
- **Severity**: high — bloquea la historia 1 de la spec 016 en cualquier entorno
  con CSP (staging y producción); el panel de operador no lo sufre porque no
  envía CSP.

## Symptom

El partner pulsa «Conectar WhatsApp» → «Abrir Meta», completa **todos** los pasos
de la ventana de Meta (empresa, número, verificación, permisos, Finalizar) y al
volver la consola muestra «Meta no devolvió el código de autorización». Canales
sigue en «0 de 1 canales». Reproducido dos veces por el owner (Cloud API y
Coexistencia) y una vez de forma instrumentada: `impression.php … action=
client_login_denied_response` llega **3 segundos** después de abrir la ventana,
antes de tocar nada en ella.

## Root cause

El SDK de JavaScript de Facebook no devuelve el código por la ventana: lo
devuelve por un **iframe oculto** montado en `https://staticxx.facebook.com/x/
connect/xd_arbiter/` (es el `redirect_uri` y el `channel_url` que la propia URL
del diálogo declara). La CSP de la consola (`apps/console/src/proxy.ts`) limita
`frame-src` a `www.facebook.com` y `web.facebook.com`, así que el navegador se
niega a montar ese frame, el SDK nunca recibe la respuesta y `FB.login`
responde `status: "unknown"` sin `authResponse.code` → `SignupError("no_code")`.

El panel de operador (`apps/admin`) usa el mismo protocolo y funciona porque no
envía cabecera CSP. La spec 016 probó el botón (render, permisos, acción) y la
API (signup, activación, 409, transacción) y la nota de ausencia; lo que nadie
probó fue **la vuelta** del código en un entorno con CSP, porque en local no hay
claves de Meta y en tests el SDK es un doble.

## Fix

Añadir `https://staticxx.facebook.com` a `frame-src`. Guardarlo con un test
sobre las directivas de la CSP para que el host no desaparezca en una limpieza.
