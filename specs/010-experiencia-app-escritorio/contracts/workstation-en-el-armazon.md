# Contrato — el puesto de trabajo, dentro del armazón (spec 010)

**Enmienda de** `specs/002-identidad-app-escritorio/contracts/desktop-bar.md`.
La barra de 44 px y su `preload` de siete funciones **se retiran**. Lo que la
barra hacía pasa al armazón; lo que la barra **decidía** —sus ocho estados y sus
transiciones— se conserva íntegro como lógica pura con test.

## Por qué se puede hacer sin debilitar nada

La barra fue la superficie **mínima** de la spec 002 *porque la pantalla de
operar no existía todavía*. Desde la 003 existe, con las mismas garantías:
partición no persistente, `sandbox`, aislamiento de contexto, `preload` de lista
cerrada con validación de entrada y redacción de credenciales a la salida.

Absorberla **reduce** superficie:

| Antes | Después |
|---|---|
| 4 particiones | **3** |
| 2 `preload` (pantalla + puesto) | **1** |
| 2 catálogos de textos, 2 sistemas de botones | **1** |
| Emparejar solo con ratón, en una hoja que no cabe | Alcanzable con teclado, en un diálogo con sitio |

Y las prohibiciones que protegían a la barra **viajan con ella**: la vista de la
aplicación no contiene ningún formulario de credenciales, y su `preload` no
menciona sesión, cookie, token ni contraseña. El test que lo afirmaba se traslada,
no se borra.

## Dónde vive ahora cada cosa

| Qué | Antes | Ahora |
|---|---|---|
| Estado de la máquina | etiqueta en la barra | **pie de la lista lateral** (siempre visible) y tarjeta en «Hoy» |
| Introducir el código de emparejamiento | hoja dentro de 44 px (no cabía) | **diálogo** de la aplicación, con el código pedido desde la misma pantalla |
| Declarar directorios | hoja dentro de 44 px | **sección de puesta en marcha** y diálogo por cliente |
| Desemparejar | confirmación nativa del navegador | **diálogo** de la aplicación, que explica qué deja de funcionar |
| «Volver al equipo» con la consola delante | acción de la barra | **innecesaria**: ya no hay dos superficies que turnarse |
| Aviso de versión no admitida | etiqueta + acción | **estado del armazón** con acción que lleva a un sitio útil |

## Lo que se conserva, palabra por palabra

- Los **ocho estados** (`sin_sesion`, `sin_emparejar`, `emparejando`,
  `conectada`, `reconectando`, `volver_a_emparejar`, `archivada_desde_consola`,
  `version_no_admitida`) y sus transiciones: el módulo puro se renombra, no se
  reescribe, y sus tests siguen siendo la verdad.
- La regla de que **ningún estado se pinta como fallo**: la máquina apagada es un
  estado, no un error.
- Que el estado **no lleva cifras de consumo** ni de qué va lo que espera.
- Que sin cifrado de disco **no se ofrece emparejar**.
- Que el emparejamiento se canjea con la sesión de la partición humana, en el
  proceso principal, y el código **no se guarda**.

## Lo que se añade

| Añadido | Por qué |
|---|---|
| Estado `comprobando`, antes del primer veredicto | Hoy la primera pintura dice «no emparejada» sin saberlo |
| `since` en todos los estados | Para poder decir «desde hace cuánto» |
| `cause` cuando se conoce (`sin_red`, `sin_ejecutor`, `sesion_perdida`) | Para que `reconectando` deje de ser perpetuo y mudo: si en la máquina no hay quien ejecute, se dice |
| Motivo del directorio rechazado | Hoy se pierde en silencio |
| Alcance por teclado y orden de menú | Hoy la barra solo se alcanza con ratón |

## Qué exige de los tests existentes

- `bar-state.test.ts` → se conserva íntegro sobre el módulo renombrado, más los
  casos de `comprobando`, `since` y `cause`.
- `bar-update-state.test.ts` → se conserva: la actualización sigue siendo
  ortogonal al estado del puesto.
- `no-own-auth.test.ts` → **se traslada** a la vista de la aplicación y a su
  `preload`, con las mismas prohibiciones.
- `bar-tokens.test.ts` → pasa a ser el test de tokens del armazón: sin colores
  sueltos, sin CSS remoto, fuentes servidas localmente.
- `session-isolation.test.ts` → de cuatro particiones a **tres**, y sigue
  abortando el arranque si dos se igualan.
