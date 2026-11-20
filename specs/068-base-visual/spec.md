# Especificación: La base visual de la consola de partners

**Rama**: `068-base-visual` · **Creada**: 2026-11-21 · **Estado**: Borrador, pendiente de la revisión de Luis

**Entrada**: el owner (Andrés, 2026-11-21), tras dar por listo el lote de Entrar: «Empecemos con el siguiente paso». Es el lote 0 del roadmap de la consola (`[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`).

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `1`: solo el aspecto de la consola de partners (`apps/console`). No toca la API, ni datos, ni `@nexus/ui`, ni el Super Admin. |
| **Garantías de aislamiento tocadas** | **Ninguna.** |
| **Nota de KB que la justifica** | `[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`. Reglas visuales del owner del 2026-11-20 (estudio y demo de la consola). |
| **Qué se mide** | **Nada.** |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| `tokens.css` (owner, 2026-09-26) | Inter es la familia del producto. Helvena queda para la web y lo impreso. | **En la consola de partners**, Helvena (owner, 2026-11-20: «solo Helvena, nunca Inter», de 400 a 600). El Super Admin sigue en Inter. |
| Escala de `tokens.css` | Título de página 40 px (`text-display`), 44 (`3xl`), 32 (`2xl`), filas 14. | **En la consola**: título de página 26, `3xl` 28, cifras 22, títulos de tarjeta 15–16, filas 13,5, ayuda 12. Cuerpo 15 en escritorio y 16 en el teléfono. |
| `Button` de `@nexus/ui` | Al pulsar, baja 1 px. | **En la consola**: al pulsar baja al 97 % en 80 ms. Los que abren un menú no se mueven. Con Reducir movimiento, nada. |

## Por qué

La consola en staging se ve grande y pesada al lado de la demo aprobada:
- el título de página va a 40 px;
- el «Inicia sesión.» va a 44 px;
- las cifras van a 32 px;
- y la letra es Inter, no la de la marca.

El owner fijó una escala compacta de escritorio y Helvena de 400 a 600. Es la base que los lotes siguientes (barra superior, Panel, Consumo, Auditoría) dan por hecha.

Se hace **solo con tokens, en la consola**. Un `@theme` de `apps/console/src/app/globals.css` pisa las medidas del paquete, y cada `text-sm`, `text-display` o `font-semibold` existente sale con el valor nuevo. No se toca ningún componente ni el Super Admin.

## Requisitos

1. **Letra.** Toda la consola usa Helvena, el archivo variable de `public/fonts`. Se precarga con `next/font/local`, y la letra de reserva se ajusta para que nada salte al llegar. Ni Inter ni otra familia.
1b. **Sin las variantes de Inter.** `@nexus/ui` enciende `ss01` y `cv11` en el `body`. Son de Inter, y en Helvena `ss01` cambia la «m» y la «n» por una forma decorativa (lo vio el owner el 2026-11-21). En la consola van apagadas (`font-feature-settings: normal`).
2. **Pesos.** Nada más grueso que 600. `font-bold`, `font-extrabold` y `font-black` salen a 600.
3. **Escala.**
   - `text-display` 26 px (interletrado −0,015 em);
   - `3xl` 28;
   - `2xl` 22;
   - `xl` 18;
   - `lg` 16;
   - `md` 15;
   - `sm` 13,5;
   - `xs` 12;
   - `base` 15 en escritorio y 16 por debajo de 768 px. Por debajo de 16, iOS amplía la página al tocar un campo.
4. **Interletrado.** Helvena es estrecha, así que los ajustes negativos pensados para Inter se suavizan: `tight` −0,01, `tighter` −0,015 y `tightest` −0,02 em.
5. **Pulsar.** Un botón baja al 97 % al pulsarlo, en 80 ms. Los que abren un menú (`aria-haspopup`) no se mueven. Con Reducir movimiento no hay escala.
6. **Sin cambios de estructura.** Las mismas pantallas, en los mismos sitios, con los mismos componentes. El Super Admin no cambia.

## Comprobado

- Capturas antes y después a 1440 px, en claro y en oscuro, con la API simulada del dinero: Panel, Clientes, Consumo, Facturación, Avisos y Entrar.
- La fuente de la página es Helvena. El `h1` mide 26 px y su peso es 600. Pulsar da `scale: 0.97`.
- Suite de la consola: 2.477 tests en verde, más typecheck y lint.

## Abierto

- **Licencia web de Helvena.** El archivo ya viajaba en la consola, pero hay que confirmar que la licencia cubre servirla en la web. Si no la cubre, basta con revertir el `@theme` y el `layout.tsx` para volver a Inter.
