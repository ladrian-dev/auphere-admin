# Iteración 3 — la tarjeta enseña lo pendiente y reintenta

**Consola cerrada el 2026-09-29.**

## Lo que cambió el diseño al escribirlo

- **Reintentar es el mismo verbo.** El endpoint de desvincular ya sabe qué
  quedó y no repite lo hecho; un segundo endpoint sería un segundo verbo que
  el partner tendría que aprender. `reintentar()` llama a
  `disconnectChannelAction` y lee `unlink_pending` de la respuesta.
- **Lo pendiente es estado; reintentar es escritura.** El aviso lo ve todo
  el mundo (constitución §V); el botón, solo `channels:write`.
- **El diálogo de desvincular mentía por defecto.** Decía «sigue registrado
  en Meta», que era verdad en la spec 019 y deja de serlo aquí. Ahora dice
  que se da de baja de nuestra aplicación, que sacarlo de la cuenta se hace
  en el Business Manager, y —en coexistencia— que seguirá chateando desde su
  teléfono (R2.5). Dos claves, no una con condicionales.
- **Dos costuras puras** (`disconnectBodyKey`, `signupFailureKey`) porque ni
  el menú ni el diálogo de Base UI se abren bajo jsdom. Lo que hay que fijar
  es qué frase sale, y eso es una función.

## Visto en local (2026-09-29, 19:55)

Fila sembrada `disconnected` con `unlink_pending = [deregister, unsubscribe]`
en Panadería La Espiga:

| Paso | Resultado |
|---|---|
| Tarjeta | insignia «Desconectado» · aviso «Falta terminar en Meta» con «…no respondió al darlo de baja y desuscribir nuestra aplicación» · botón **Reintentar** |
| Reintentar | toast «Terminado en Meta.» · el aviso desaparece · la tarjeta queda limpia |
| Auditoría | `after.meta = {"done": [], "pending": [], "skipped": ["deregister", "unsubscribe"]}` — el canal sembrado no tenía credencial, así que los pasos se anotan `skipped` (regla de la iteración 2) |

## Suites

| Suite | Resultado |
|---|---|
| `channel-card` (17) · `whatsapp-connect` (6) · `same-in-three` · i18n (39) | ✅ |
| `tsc --noEmit` · eslint | limpios |

## Queda para staging (T025)

Que Meta devuelva de verdad `number_held_by_previous_owner` con un número
retenido, y ver la frase en la consola. Lo demás de esta iteración no depende
de Meta.
