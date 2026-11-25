# Especificación: Dónde estás (el marco de la consola)

**Rama**: `069-donde-estas` (fusionada en el PR #44; la spec pasó a 070 el 2026-11-21 porque el 069 ya era de `069-la-app-con-el-diseno-nuevo`) · **Creada**: 2026-11-21 · **Estado**: Borrador, pendiente de la revisión de Luis

**Entrada**: el owner (Andrés, 2026-11-21): «Sí, empieza» el lote 2 del roadmap de la consola (`[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`).

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `1`: solo el aspecto del marco de la consola de partners. No toca la API, los permisos, las rutas ni `@nexus/ui`. |
| **Garantías de aislamiento tocadas** | **Ninguna.** |
| **Nota de KB que la justifica** | `[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`, lote 2. |
| **Qué se mide** | **Nada.** |

## Qué había ya en staging

Gran parte del lote ya estaba en staging, y se mantiene tal cual:
- la barra superior fuera del panel, con plegar, migas, ⌘K, tema y campana;
- el plegado del lateral a 64 px, animado;
- el menú del perfil que se abre hacia arriba, con Equipo, Facturación y API, el idioma y cerrar sesión;
- el botón redondo de volver;
- las pestañas del cliente y del agente como cápsula de vidrio, cada una con su dirección.

Lo que faltaba era el movimiento y tres detalles.

## Requisitos

1. **La lente de vidrio.** El elemento activo del lateral, de las pestañas del cliente y de las del agente lleva debajo una lente que **viaja** al nuevo activo, en vez de que el resalte salte de sitio (0,32 s, la curva de entrada de la consola).
   - Con Reducir movimiento, aparece en su sitio sin viajar.
   - En el lateral es vidrio (translúcido, borde de luz y desenfoque). Con Reducir transparencia pasa a sólido.
   - En las pestañas es la misma pastilla blanca de antes.
   - **Nunca hay un instante sin resalte**: hasta que la lente está colocada, el activo conserva su fondo.
   - Sigue al lateral cuando se pliega.
   - Es decoración (`aria-hidden`). El estado lo siguen diciendo `aria-current` y `aria-selected`.
   - Componente: `components/shell/sliding-lens.tsx`. Estilos en `app/globals.css`.
2. **Sin trazo lateral ni verde plano en el activo del lateral.** Lo marca la lente. El texto del lateral baja a 14 px (la escala compacta).
3. **«Beta» neutro.** Gris con borde, no ámbar: el ámbar es solo de los avisos.
4. **Un chevron hacia arriba** en el botón del perfil del lateral, que dice hacia dónde se abre el menú. Plegado se desvanece con el nombre.

## Comprobado

- Lateral: la lente coincide con el activo (`[12, 177, 232, 36]`) y viaja de «Consumo» a «Clientes». Se ve bien en claro, en oscuro y plegado.
- Pestañas del cliente: viaja de «Agentes» a «Negocio».
- Pestañas del agente: viaja de «Rendimiento» a «Configuración».
- Vitest: `sliding-lens.test.tsx` (se coloca, viaja, sin activo no quita el resalte). Suite de la consola: 2.477 + 3 en verde, con lint y typecheck.

## Fuera de alcance: `e2e/shell.spec.ts` ya falla en `develop`

Seis de sus nueve pruebas fallan igual en `develop` que en esta rama (comprobado el 2026-11-21). Esperan cosas que el marco ya no hace:
- «Equipo» y «API» en el lateral, cuando se movieron al menú del perfil el 2026-10-28;
- un vidrio de `blur(20px)`, cuando el token es de 22.

Además hay una violación de axe en `/notifications`. Hay que ponerlas al día aparte.
