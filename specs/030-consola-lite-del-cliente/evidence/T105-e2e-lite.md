# T105 — E2E y axe de la consola lite

**Fecha:** 2026-10-19 · **Base:** `main@28a5b562`, la misma que corre en
producción ([T110-produccion.md](T110-produccion.md)), más el cambio de
cierre.

## Dónde se corrió

En local, no en staging: la persona de cliente de staging
(`contacto+lite@ladrian.dev`) tiene una contraseña que la sesión no conoce.

- **API** en `127.0.0.1:8030` con una base propia (`nexus_dev_s030`), migrada
  hasta 0157, y su propia base de Redis.
- **Consola** en `localhost:3130`, primero con `next dev` y al final con
  `next build` + `next start`, que es lo que se sirve en producción.
- **Datos:** un partner `demo` (por la API del admin), tres clientes de
  `dev_seed_console_volume.py` y el acceso lite de `vol-01` (Panel, Bandeja y
  Consumo) con `dev_seed_client_access.py`. La persona aceptó la invitación
  por `/invite/{token}`.
- **Bandeja:** tres conversaciones abiertas con mensajes. Una la atiende el
  agente; otra espera a una persona y su contacto tiene un nombre de 51
  caracteres; en la tercera la ventana de 24 h está cerrada. Sin ellas la
  Bandeja solo enseña su estado vacío: el volumen sembrado son conversaciones
  cerradas y sin mensajes, y el `dev_inbound_message.py` que cita el
  quickstart no existe.

## Lo que comprueba la suite (`--project=lite`, 24 pruebas)

- La barra es la del cliente: insignia «lite», sus tres módulos, nada del
  partner.
- Frontera: `/clients`, `/audit`, `/team`, `/keys`, `/billing`,
  `/notifications`, `/usage/alerts` y `/workstation` llevan a un módulo del
  cliente **sin ningún error de página** por el camino.
- `/`, `/inbox` y `/usage` en **ES y EN** × **claro y oscuro** (12 vistas): axe
  sin incidencias graves ni críticas (WCAG 2.0/2.1/2.2 A+AA y buenas
  prácticas), sin desbordes a 360 y 1920 px, y sin desbordes a 360 px con
  todo el texto un 30 % más largo. Cada prueba comprueba antes que
  `<html lang>` y `data-theme` son los pedidos: una cookie ignorada o un tema
  que no cambiara pasarían en silencio.
- La Bandeja abre una conversación, ofrece exactamente un modo del compositor
  y el hilo abierto pasa la misma auditoría.
- ⌘K desde el Panel busca en la Bandeja.

## Lo que encontró (en rojo primero) y cómo quedó

| Hallazgo | Dónde | Arreglo |
|---|---|---|
| La suite no podía pasar: entraba antes de cada prueba y el login admite 10 intentos por minuto y correo | `e2e/lite.spec.ts` | `client.setup.ts` entra una vez y guarda la sesión; proyecto `lite` propio en `playwright.config.ts` |
| `aria-prohibited-attr` (grave): un `<p aria-label>` con el gasto del mes | `components/lite/lite-spend-card.tsx` | la cifra se lee de un texto oculto; las partes con estilo, ocultas al lector |
| `aria-prohibited-attr` (grave): cada barra del gasto por día era un `<div tabIndex aria-label>` sin rol | `components/charts/day-bars.tsx` (compartido con el partner) | `role="img"` |
| Desborde a 360 px: diez etiquetas «20 sept» no caben y ensanchaban sus columnas | `day-bars.tsx`, `day-bars-model.ts` | columnas del ancho de su barra, etiqueta encima, la última pegada al borde y una de cada dos si el gráfico es estrecho (`keepDayLabelWhenNarrow`) |
| Desborde a 360 px con texto +30 %: la cabecera de la tarjeta de gasto no podía partir línea | `lite-spend-card.tsx` | `flex-wrap` |
| Desborde a 360 px con texto +30 %: el selector de días del gasto | `@nexus/ui` `Section` (acciones) y `spend-controls.tsx` | las acciones no pasan del ancho de la sección y el grupo parte línea |
| `color-contrast` (grave), en claro y en oscuro: iniciales y etiquetas de la Bandeja, `accent-deep` sobre `accent-soft` a 4,21:1 | `@nexus/ui` `tokens.css` | `accent-deep` pasa a `forest` (5,0:1); el par queda medido en `contrast.test.ts` |
| Frontera: un segundo de «This page couldn't load», sin traducir, antes del Panel (React #310 en el Router de Next) | `(console)/layout.tsx`, `proxy.ts` | **T111** |
| Carrera de la prueba: contaba filas antes de que la lista cargara | `e2e/lite.spec.ts` | espera filas o estado vacío |

Cada arreglo de componente tiene su prueba unitaria escrita antes y vista en
rojo: `lite-panel.test.tsx`, `lite-usage.test.tsx`,
`charts/__tests__/day-bars-model.test.ts` y `@nexus/ui contrast.test.ts`.

## Resultado

| Corrida | Resultado |
|---|---|
| Primera, con `next dev` | 12 de 22 en rojo (axe y desbordes en `/` y `/usage`, cuatro pantallas de la frontera) |
| Con hilos en la Bandeja | 5 en rojo (contraste en `/inbox` y en el hilo) |
| Frontera sin T111 / con T111 | 4 de 7 en rojo / 7 de 7 |
| Final, `next dev` | **24 de 24** |
| Final, `next build` + `next start` | **24 de 24** |

Con el build de producción, la frontera es un 307 del servidor: con la sesión de la persona de cliente, `/team` y `/usage/alerts` responden `307 → /`, y `/inbox` responde 200. Sin T111 pasaban por la pantalla de error de Next durante ~1 s (medido muestreando la página cada 150 ms).

## La auditoría del partner (`a11y.spec.ts`), por los componentes compartidos

Como el cambio toca `DayBars`, `Section` y un token, se corrió también la
auditoría CP-30 como owner del partner local: **24 de 27**. Los tres rojos
están en ficheros que este cambio no toca y vienen de `main`:

- `/`: `aria-prohibited-attr` en `components/home/spend-card.tsx`, el mismo
  `<p aria-label>` que se arregló en la tarjeta lite, que salió de ahí.
- `/audit`: el grupo de filtros de `audit/filters.tsx` se desborda a 360 px con
  el texto +30 %.
- `/clients/{ref}/channels`: un botón se desborda a 360 px con el texto +30 %.

Quedan para un arreglo aparte, fuera de la spec 030.

## Cómo correrla en staging

```bash
E2E_BASE_URL=https://console.staging.auphere.com \
E2E_CLIENT_EMAIL=contacto+lite@ladrian.dev E2E_CLIENT_PASSWORD=… \
  pnpm --dir apps/console exec playwright test --project=lite
```

No envía mensajes: en un entorno con contactos reales, enviar escribiría a una
persona real.
