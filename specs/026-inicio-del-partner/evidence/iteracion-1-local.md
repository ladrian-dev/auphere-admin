# Iteración 1 · verificación en la consola local (2026-10-02)

Datos: partner `demo-audit` con `scripts/dev_seed_console_volume.py --clients 12 --conversations 1500 --usage-rows 8000` (15 clientes, 13 activos, 2 en alta).

## Lo que se vio

- **Necesita tu atención** arriba del todo, 8 filas en vez de 20. El crédito del partner está a 0, así que la primera fila dice «Tu crédito está agotado · Ningún agente puede responder hasta que haya crédito» con los 13 clientes nombrados y el botón «Ver crédito» a Consumo. Después: sin agente publicado, número desconectado, mensajes fallidos, cambios sin publicar y, plegadas, las dos altas sin terminar.
- **Tarjetas**: Conversaciones 1 500 con su línea de 7 días (sin variación porque no hay semana anterior, y lo dice), Clientes atendiendo 13 de 15, Crédito disponible 0 marcado en rojo, Mensajes del mes con su proyección.
- **Conversaciones por día** apiladas por los 5 clientes con más actividad más «Resto de clientes». Al lado, **Por revisar ahora** («Nada espera a una persona», el seed no crea escaladas).
- **Tus clientes**: primero los que tienen algo por resolver, con estado, conversaciones de 7 días y su línea, crédito («Quedan X de Y» o «Sin asignar») y última actividad.
- **Actividad reciente** desde la auditoría, en palabras.
- Fuera «Calculado en X ms».

## Comprobaciones

- Móvil 375 px: sin scroll horizontal, el texto del problema en su propia línea, la tabla cabe (sin la línea de tendencia por debajo de `sm`).
- `GET /console/home` 200 en todas las cargas, sin errores en la API.
- Vitest consola 603 · `@nexus/ui` 170 · API home 21 · tsc, eslint, ruff, mypy limpios.

## Ajustes hechos al verlo

1. Un problema compartido por 3 o más clientes es una fila.
2. Crédito del partner a cero: fila de partner, no 13 «Asignar crédito» que no lo arreglan.
3. «Última actividad» toma el último mensaje del cliente o el inicio de la conversación cuando escribió primero el negocio.
4. Sin semana anterior no se pinta variación.

## Pendiente

- Staging tras el push (CI y despliegue), con datos reales del partner interno.
- Ruido ajeno visto en la actividad: «cambió la capacidad ? de Lola Mento: ?.» viene del vocabulario de auditoría, no de esta spec.
