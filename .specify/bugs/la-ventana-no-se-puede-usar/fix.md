# Bug Fix: la ventana se puede usar

- **Slug**: la-ventana-no-se-puede-usar
- **Fixed**: 2026-09-20
- **Assessment**: ./assessment.md
- **Status**: applied (V1-V4)

## Summary

El chat pasa de **311 px a 684** a 1280, y de **32 px a 624** en la ventana mínima.
Los bordes vuelven a verse en oscuro, en la aplicación y de paso en la consola y el
panel de operador. Una excepción de render ya no deja la ventana en negro. Y sin
sesión, la lista lateral deja de prometer algo que no viene.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `app/routes/env.tsx` | modificado | **V1**: el panel es `w-80 shrink-0` y se retira por debajo de `xl` |
| `packages/ui/src/styles/tokens.css` | modificado | **V2**: `--color-border` y `--color-border-soft` declarados para el tema oscuro |
| `packages/ui/src/components/__tests__/contrast.test.ts` | modificado | **V2**: 6 guardas nuevas sobre el fichero de tokens |
| `app/feedback/error-boundary.tsx` | añadido | **V3**: la red de seguridad, sin `t()` y sin `@nexus/ui` |
| `app/main.tsx` | modificado | **V3**: el armazón envuelve a `App` desde fuera |
| `app/i18n.ts` | modificado | **V3**: `format()` registra y devuelve la clave en vez de lanzar |
| `app/routes/pair-errors.ts` | añadido | **V3**: la tabla de códigos conocidos, pura y probable sola |
| `app/routes/pair-dialog.tsx` | modificado | **V3**: usa esa tabla en vez de construir la clave |
| `tests/error-boundary.test.tsx` | añadido | **V3**: 8 casos, las tres capas |
| `app/App.tsx` | modificado | **V4**: sin sesión, el roster queda en estado terminal |

## Las cuatro decisiones que no son obvias

**1. El panel de entorno se retira, no se encoge.**

Por debajo de `xl` (1280) desaparece. Es una pérdida real —el directorio, la
máquina y la política de ejecución dejan de verse— y aun así es estrictamente mejor
que un chat de 32 px. Encogerlo no era opción: su contenido son rutas absolutas y
un panel de 120 px con rutas partidas no informa de nada.

El corte está en `xl` y no en `lg` porque a 1024 con panel el chat se quedaba en
**428 px**, que es estrecho para leer un bloque de código. Medido, no estimado:

| Ventana | Antes | Después |
|---|---|---|
| 1280×800 | 311 px | **684 px** |
| 1024×700 | — | **748 px** (sin panel) |
| 900×600 (mínima) | **32 px** | **624 px** |

El panel plegable **con su control**, que es lo correcto, es de la spec 013.

**2. El token de marca se declara por tema; el puente de shadcn ya lo hacía.**

`--border` y `--color-border` son dos cosas y se parecen demasiado. El fichero ya
explicaba por qué el segundo no puede espejar al primero (`var()` circular), y esa
nota correcta lo dejó sin bloque oscuro. Ahora los dos se declaran en los dos temas,
y hay seis tests que lo vigilan.

**No se le pide 3:1.** El test de contraste ya razonaba que un borde es decoración y
exigirle contraste de componente dejaría la interfaz cargada. Se le pide **existir
por tema** y **verse** (> 1,2:1).

**3. La red de seguridad no depende de nada que pueda estar roto.**

El `ErrorBoundary` no usa `t()` —los textos van literales en las dos lenguas— ni los
botones de `@nexus/ui`. Una red que depende de la pieza que puede haberse caído no
es una red. El precio es declarar a mano el anillo de foco, que el sistema de diseño
daría gratis: un botón sin foco visible en la única pantalla que queda no se puede
usar con el teclado.

**4. Tres capas para un fallo, y ninguna sobra.**

`format()` deja de lanzar, la pantalla de emparejamiento deja de inventar claves, y
el armazón sostiene lo que se escape. Arreglar solo la primera dejaría la ventana en
negro con el siguiente campo inesperado que llegue del servidor; arreglar solo la
tercera convertiría un texto que falta en una pantalla de error.

Y lo desconocido cae en «no se pudo emparejar; tu máquina sigue como estaba», que es
verdad en cualquier caso. Decir «el código ya no vale» sin saberlo mandaría a la
persona a pedir otro código que tampoco iba a funcionar.

## Lo que este arreglo NO hace

- **El markdown sigue en crudo**, los mensajes propios siguen sin volver al reabrir
  el hilo, y la primera pantalla sigue siendo un panel de estado. No son defectos:
  es capacidad que nunca se construyó, y va por la spec 013.
- **En el primer arranque sigue diciendo «Tu sesión terminó».** El esqueleto ya no
  se queda colgado, pero el texto sigue asumiendo una sesión anterior. Distinguir
  «nunca entró» de «caducó» pide un dato que hoy no existe — ver el assessment.
- **El panel de entorno no se puede abrir bajo 1280.** Sin control, se retira y ya.
