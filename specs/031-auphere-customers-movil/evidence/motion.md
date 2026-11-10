# Evidencia de movimiento — spec 031 (T108, D24)

## Inventario de animaciones (del código, 2026-10-20)

Duraciones de los tokens de la consola (`tokens.css` → `tokens.gen.ts`); el
módulo `src/motion/durations.ts` falla al cargar si alguna pasa de 300 ms.

| Dónde | Qué | Duración | Con «Reducir movimiento» |
|---|---|---|---|
| «Tomar el control» (`conversacion/[id]/index.tsx`) | la tarjeta sale, el cuadro entra, los vecinos se recolocan; vibración de éxito; el cursor va al cuadro | salida 120 ms · entrada 200 ms · recolocación 240 ms | solo fundidos (160 ms), sin recolocación |
| Un mensaje que sale (`PendingBubble`) | entra desde abajo; vibración ligera al enviar y de éxito al confirmarse | 200 ms | fundido |
| Un aviso en la conversación (conflicto, resuelta) | entra y sale | 200 / 120 ms | fundido |
| Pantallas de entrada (`EntryFrame`) | la marca y el título entran una vez | 200 ms | fundido |
| Una imagen recibida | fundido al cargar | 120 ms | igual |
| «Reconectando…» | el punto late mientras no hay línea — **el único bucle** | 600 ms por medio ciclo | quieto |
| Navegación, hojas, menús, pestañas | los del sistema (pila nativa, `formSheet`, hoja de acciones) | del sistema | los del sistema |

Ningún resorte rebota (`overshootClamping`). Vibraciones con significado: éxito
(control tomado, mensaje enviado, nota guardada), ligera (enviar, cambiar de
filtro), aviso (conflicto, fallo).

## Lo que comprueban las pruebas

- `states.test.tsx`: todas las duraciones ≤ 300 ms; con movimiento reducido las
  entradas son fundidos y no hay recolocación; «Reconectando» no anima.
- `atender.test.tsx`: tomar el control vibra con éxito y pide el foco del
  cuadro; un 412 vibra con aviso.

## Pendiente en dispositivo

- [ ] Vídeo de «Tomar el control» en iOS y Android.
- [ ] La misma pantalla con «Reducir movimiento».
- [ ] Entradas de mensajes y recolocación de la Bandeja.
- [ ] Monitor de rendimiento a 60 fps en un teléfono medio (Android de gama
      media) al desplazar la Bandeja y el hilo.
