# US1 · WhatsApp desde la consola — staging, 2026-09-23 ✅

Partner «Demo (staging)», owner en Brave, cliente `prueba-whatsapp-016` creado
ese mismo día con el wizard de cuatro etapas.

## Lo que hizo falta antes (dos bugs, `.specify/bugs/meta-no-devuelve-el-codigo`)

1. **CSP**: `frame-src` no admitía `staticxx.facebook.com`, el frame por el que el
   SDK devuelve el código → `be0833e`.
2. **COOP**: `Cross-Origin-Opener-Policy: same-origin` cortaba `window.opener` con
   la ventana de Meta y el SDK daba la respuesta por denegada a los 3 s, antes de
   tocar nada → `ed8d22d`. Reproducido de forma instrumentada antes y después
   (`client_login_denied_response` a los 2,9 s; tras el arreglo, solo
   `client_login_start` y el diálogo en «Conectando…» esperando).

También hicieron falta, fuera del repo: los dominios de la consola en «Dominios
permitidos para el SDK de JavaScript» de la app de Meta, y las tres variables
`NEXUS_META_*` en el entorno **Preview** de Vercel (estaban solo en Production).

## Recorrido

1. Canales → «Conectar WhatsApp» → modo **Coexistencia** → «Abrir Meta».
2. Ventana de Meta completada por el owner con un número real (`+34 653 321 693`,
   nombre verificado «Auphere»). El primer intento con el número de prueba de
   Meta (`+1 555 151 3702`) no puede verificarse: es solo para el sandbox.
3. Al volver: **«1 de 1 canales»**, tarjeta WhatsApp **Activo**, límite
   `TIER_250`, modo `coexistence`, calidad «Desconocida» (aún sin comprobación),
   botón «Conectar otro número», sección de plantillas activa («Nueva plantilla»).
4. Ficha: **«Listo para atender · Agente: Versión 1 activa · WhatsApp:
   Conectado»**; el número aparece bajo el nombre.
5. Auditoría del cliente, en orden: guardó un borrador (v1) → publicó la versión 1
   → cambió a active → **conectó WhatsApp** (`console.channel.connect`, actor
   `andresmatos.ui@gmail.com`).
6. Portada: 7 clientes activos; las incidencias siguen siendo solo los dos
   «sin cupo». El onboarding del partner ya tenía «Conecta un canal» hecho por
   un cliente anterior.

No hubo 409 `number_in_use` que probar en vivo (queda en `test_a_number_that_belongs_to_another_client_is_409_and_changes_nothing`).
