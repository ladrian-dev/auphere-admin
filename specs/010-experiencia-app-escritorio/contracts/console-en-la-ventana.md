# Contrato — la consola en modo embebido (spec 010)

La consola es la misma aplicación web de siempre. Dentro de la ventana de
escritorio se pinta **sin su propio armazón**, porque el armazón ya lo pone la
aplicación. Este contrato fija qué cambia, cómo se detecta y qué **no** cambia.

## Cómo se detecta

Por el **user-agent** de la partición humana, que la cáscara ya marca con
`AuphereDesktop/<versión>`. Es la única señal disponible: la consola **no tiene
`preload`** y no puede recibir nada de la cáscara (002 R12.1).

- La detección ocurre **en el servidor**, al construir la página, para que no haya
  parpadeo de un armazón que se monta y se desmonta.
- La función de detección que ya existe se amplía y gana test propio.
- Si la detección falla, la consola se pinta **completa**: se ve un armazón
  duplicado (feo, no roto). Ese es el modo degradado aceptado.

## Qué oculta la consola en modo embebido

| Elemento | En navegador | En la ventana |
|---|---|---|
| Barra lateral de la consola | sí | **no** (la pone la aplicación) |
| Cabecera con buscador y campana | sí | **no** (la búsqueda es ⌘K de la aplicación; los avisos, del armazón) |
| Menú de usuario con avatar, idioma y tema | sí | **no** (la identidad y el tema son del armazón) |
| Migas de pan | sí | sí — son ubicación **dentro** de la sección, no navegación global; R1.3 prohíbe lo segundo |
| Contenido de la página, sus acciones y sus avisos efímeros | sí | sí |
| Tarjetas de puesta en marcha propias de la consola | sí | **no**: la puesta en marcha es una sola, la del armazón |

**Regla de oro**: en modo embebido la consola **no pinta navegación global ni
identidad**. Todo lo demás es idéntico — no se reimplementa ninguna página
(003 R12.6).

## Qué no cambia

- La consola **sigue sin `preload`**, sin canal y sin conocimiento de la cáscara
  más allá de ese user-agent.
- Su sesión sigue viviendo en la cookie de la partición humana.
- Sus permisos por rol siguen decidiendo qué se ve: si una sección no le
  corresponde a la persona, **la aplicación no la ofrece en la lista lateral**.
- Los enlaces externos (pago, proveedores) siguen saliendo al navegador del
  sistema; lo que cambia es que ahora **la ventana lo dice y espera**.

## Quién sabe dónde está la consola

El **proceso principal** observa la navegación de esa vista y empuja a la
aplicación `{section, path}`, acotado a la lista de secciones canónicas. Con eso
la lista lateral marca la sección activa, incluso cuando la navegación ocurrió
**dentro** de la consola (un enlace de una página a otra).

Si la consola navega a una ruta que no está en la lista canónica, la aplicación
marca la sección más cercana conocida y no inventa ninguna.

## Tema

El tema lo decide el armazón y se propaga a la vista de la consola por el
mecanismo del sistema. En modo embebido, la consola **no ofrece** su propio
selector: hoy es posible tener la consola en claro y el resto de la ventana en
oscuro, y eso desaparece.

## Tests que este contrato exige

1. La consola en modo embebido **no** renderiza su barra lateral, su cabecera ni
   su menú de usuario (test de la consola).
2. Sin la marca de la cáscara, la consola renderiza su armazón completo.
3. La detección no depende de nada más que del user-agent.
4. En la ventana, el humo del binario comprueba que en el panel hay contenido de
   consola y **una sola** navegación visible.
