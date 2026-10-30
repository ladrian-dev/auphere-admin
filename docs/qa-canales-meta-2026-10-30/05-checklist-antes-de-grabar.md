# Checklist antes de grabar

Marca cada punto con evidencia (enlace, captura o ID de caso). Si un punto no se cumple, ese vídeo no se graba.

## Comunes

| ID | Punto | Estado 2026-10-30 | Evidencia o bloqueo |
|---|---|---|---|
| C-01 | El entorno donde se graba está decidido (staging o producción) y es el mismo que el de las instrucciones del revisor | ❌ Abierto | Las instrucciones montan el revisor en producción (`app-review-reviewer-setup.md`); este QA cubre staging |
| C-02 | Se sabe qué versión hay en ese entorno | ✅ Staging | `9e7c71b5` (huella de OpenAPI idéntica y despliegue con éxito a las 12:27 UTC). Hay que repetirlo el día que se grabe |
| C-03 | Consola y API del mismo commit | ✅ Hoy | Desde las 12:27 UTC. Comprobarlo de nuevo antes de grabar (INC-05: Vercel no espera a CI) |
| C-04 | Las pruebas que el vídeo necesita están en PASS E2E | ❌ No | Ninguna prueba E2E de los cuatro canales en PASS (`01-matriz-de-pruebas.md`) |
| C-05 | Cuentas y activos de prueba listos y con rol en la app | ❌ No | 0 evaluadores de Instagram y Facebook (auditoría 2026-10-29); T050 sin hacer |
| C-06 | Datos de demostración preparados | ⚠️ Parcial | Productos de demo en `catalog-demo-images/` sin versionar; catálogo de demo en el portfolio del owner, no en el del cliente de demo (INC-04) |
| C-07 | Ningún secreto ni dato personal en pantalla | ⬜ Por revisar en cada toma | Ojo con el correo personal del owner y los números `+34…` en el cliente de demo |
| C-08 | La interfaz no tiene errores que corten el flujo | ⚠️ | La consola de staging carga sin errores propios. Solo aparece el aviso de CSP de `vercel.live` (la barra de previsualización de Vercel; no sale en producción) |
| C-09 | La secuencia es reproducible (ensayada dos veces sin cortes) | ❌ No | — |
| C-10 | Requisitos de revisión contrastados el mismo día del envío | ⚠️ Parcial | Grabaciones: guía oficial leída el 2026-10-30. Regla de las «llamadas en 30 días»: sin volver a leer |
| C-11 | Interfaz de Meta y de la consola en inglés | ⬜ | — |
| C-12 | Consola en inglés con los mismos textos que las instrucciones del revisor | ⬜ | Las instrucciones citan «Connect a catalogue», «Asking Meta for the catalogues…»: comprobar las cadenas en inglés |

## Por vídeo

| Vídeo | Bloqueos antes de grabar |
|---|---|
| V-WA-1 | C-01…C-05; número dedicado para Cloud API; WA-01…WA-08 E2E |
| V-CAT-1 | INC-01 (DELETE), INC-02 (coexistencia sin lista), INC-04 (catálogo no concedido a la integración); CAT-01…CAT-06 E2E |
| V-IG-1/2/3 | INC-03 (staging no recibe eventos de Instagram), `beta_channels` del partner, evaluador de Instagram, cuenta profesional real en un portfolio |
| V-HA-1 | Confirmar `HUMAN_AGENT` con login unificado; preparar una conversación de más de 24 h |
| V-MS-1/2 | INC-03, T050 (`pages_read_engagement`, `messaging_policy_enforcement`), Página publicada |
| V-PROF-1 | Decisión del owner sobre Business Asset User Profile Access |
