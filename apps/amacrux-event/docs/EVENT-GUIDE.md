# Guía de prueba rápida para el evento

## Antes de abrir puertas (5 minutos)
1. Abre `https://<dominio>/api/health`: debe responder `{"status":"ok","mode":"live"}` (o `demo` si así se decidió).
2. Escanea el QR con un celular real: la bienvenida carga en menos de 3 s y se ve la marca.
3. Recorre el perfil A (abajo): tras la pregunta 12 aparece el formulario (nombre y apellido, empresa, correo, teléfono opcional, consentimiento); envíalo con tu propio correo y comprueba que llega al buzón `LEADS_TO` y que después se muestra el resultado.
4. Pulsa **Reiniciar** → confirma → vuelve a la bienvenida limpia (2 toques).

## URL del QR
`https://<dominio>/eventos/ia-empresas-2026?utm_source=qr&utm_medium=evento`
(cambia `ia-empresas-2026` por el identificador acordado: minúsculas, números y guiones).

## Perfiles de prueba (respuestas a marcar)
| Perfil | Rol | Empresa | Cómo trabajan | Fricciones | Objetivos | Contexto | Resultado esperado |
|---|---|---|---|---|---|---|---|
| **A · Gerente de pyme** | Dirección | Comercio y retail · 11–50 · Consumidores (B2C) | Explorando · Todavía no · Hojas de cálculo | Tareas manuales · Copiar datos · Correos y solicitudes | Ahorrar tiempo | Próximos meses · Sin equipo técnico · Para una prueba | Automatización operativa / solicitudes / integración sencilla; CTA "Solicita una DEMO" |
| **B · Operaciones** | Operaciones | Industria y logística · 51–200 · Empresas (B2B) | Adoptando · Alguna herramienta · Varios sistemas sueltos | Logística · Informes · Copiar datos | Escalar · Aprovechar datos | Ya, es prioritario · Apoyo limitado · Para un proyecto | Operaciones, integración y reporting; nivel Alta; CTA "Solicita una DEMO" |
| **C · Ingeniería** | Ingeniería de software | Tecnología y software · 11–50 · Empresas (B2B) | Avanzado · Integrada en procesos · Centralizada | Desarrollo · Testing y calidad · Documentación | Desarrollar más rápido · Mejor producto | Próximos meses · Equipo especializado · Para un proyecto | IA para desarrollo, testing, documentación o producto |
| **D · Exploratorio** | Dirección | Otro · 1–10 · Mixto | Inicial · Todavía no · Papel, correos y chats | Otro | Decidir mejor | Sin urgencia · Sin equipo técnico · Solo explorar | Tres recomendaciones "Orientativo", nivel Explorando, CTA "Solicita una DEMO" |

## Qué hacer si…
- **El envío del lead falla**: el visitante ve un aviso con "Reintentar"; el resultado no se pierde. Revisa `/api/health` y las variables en Vercel.
- **Alguien recarga a mitad**: vuelve al mismo paso con sus respuestas (misma pestaña).
- **Otra persona toma el celular**: Reiniciar → confirmar. No queda ningún dato del anterior.
- **No hay conexión**: el diagnóstico y el resultado funcionan igual; solo el envío del lead necesita red.
- **Quieres ver el embudo en directo**: con `NEXT_PUBLIC_ANALYTICS=console` los eventos salen en la consola del navegador; con Plausible, en su panel.

## Modo demo
Con `NEXT_PUBLIC_DEMO_MODE=true` (o sin `RESEND_API_KEY`) todo funciona igual, pero la confirmación dice "modo demostración" y no se envía correo. Útil para ensayar sin llenar el buzón.
