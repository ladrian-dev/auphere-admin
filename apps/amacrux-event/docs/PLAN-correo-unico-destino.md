# Plan · Correo como único destino, listo para clientes

Decisión del usuario (2026-09-17): **solo Resend**. Sin Supabase y sin webhook.
Todo llega a `contacto+event@auphere.com` y el equipo mapea a mano. El código de
Supabase y del webhook se queda donde está, inerte y probado, por si se enciende
después; nadie lo configura hoy.

Con esa decisión se aplican además las correcciones detectadas en la revisión,
porque la app pasa de "demo de evento" a algo que usan clientes.

## Cambios

1. **El correo lleva todo lo que se podría haber almacenado** — `lib/leads/email.ts`.
   Contacto, origen, las 12 respuestas, cualificación con el desglose de los 7
   componentes de la puntuación, las 3 recomendaciones, y un **bloque CSV de una
   línea** con las mismas columnas que la fila de base de datos, listo para pegar
   en una hoja. `flattenLeadRow` se completa con lo que le faltaba (`interes`,
   `consentimiento_marketing`, UTM desglosada, desglose de puntuación).

2. **El límite por IP no puede tumbar un evento** — `api/leads/route.ts`.
   5 envíos por IP / 10 min es letal detrás del NAT de un recinto: a partir del
   sexto asistente, 429. Sube a 60. La defensa real es el honeypot + Zod + la
   idempotencia.

3. **El diagnóstico deja de ser rehén de la entrega** — `components/lead/LeadForm.tsx`.
   Si el envío falla por nuestro lado, el visitante puede ver su resultado igual.
   El formulario sigue siendo la puerta en el camino feliz.

4. **En producción, el modo demo es explícito o no es** — `lib/env.server.ts`.
   Hoy, si falta `RESEND_API_KEY`, la app cae en demo en silencio y contesta
   `ok:true` tirando el lead. En producción, sin destinos y sin la bandera
   explícita, `503` y `/api/health` lo canta.

5. **Texto honesto del modo demo** — `components/result/ResultView.tsx`.
   Decía "tu contacto se ha registrado sin enviar correo" cuando no se registra
   nada en ninguna parte.

6. **La política de privacidad dice la verdad** — `app/privacidad/page.tsx`.
   Afirmaba que las respuestas se quedan en el navegador y que el resultado no
   se envía a ningún servidor. Con el envío del formulario viajan las 12
   respuestas, la puntuación, el segmento, la etiqueta interna y las
   recomendaciones. Se dice, se dice a dónde (correo + registro de Resend) y se
   da dirección para ejercer derechos.

7. **Documentación al día** — `.env.example`, `docs/CONFIG.md`,
   `docs/PUBLISH-CHECKLIST.md`, `docs/TODO-COMERCIAL.md`, `docs/DECISIONS.md`
   (D19), `docs/leads-sheet-headers.csv`.

## Fuera de alcance, y por qué

- **Registro de diagnósticos anónimos** (quien no deja el correo): necesita un
  sitio donde guardar. Sin base de datos no hay dónde ponerlo; el correo no
  sirve para eso. Queda pendiente para cuando haya destino persistente.
- **Sector inmobiliario** en la pregunta 2: no se pidió.
- **Quitar el código de Supabase y del webhook**: no estorba y está cubierto por
  tests; borrarlo sería perder trabajo hecho.
