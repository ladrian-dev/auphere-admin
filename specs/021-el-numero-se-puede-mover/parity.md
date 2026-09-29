# Paridad — el número se puede mover

Qué hacía desvincular en la spec 019 y qué le pasa a cada parte aquí.
**Nada se retira.** Todo lo de la 019 se conserva; se añade lo que faltaba.

| Lo que hacía (spec 019) | Aquí |
|---|---|
| Marca el canal `disconnected` | Igual — y ahora **antes** de cualquier llamada a Meta |
| Conserva la fila (historial, reconectar) | Igual — la fila se queda; lo que cambia es que **ya no ocupa el número** |
| No toca Meta | **Cambia**: da de baja el número; desuscribe la app solo si era el último de su WABA |
| Idempotente (dos clics no fallan) | Igual — y el segundo clic **reintenta** lo que quedó pendiente en Meta |
| Audita `console.channel.disconnect` | Igual — con `after.meta = {done, pending}` |
| Solo `channels:write` | Igual |
| El aviso: «sigue registrado en Meta» | **Cambia**: se da de baja de nuestra app; sacarlo de tu cuenta se hace en el Business Manager; en coexistencia sigue en tu teléfono |
| Un número ajeno vivo → 409 `number_in_use` (spec 016) | Igual. **Nuevo**: un número ajeno desvinculado ya no da 409 |
