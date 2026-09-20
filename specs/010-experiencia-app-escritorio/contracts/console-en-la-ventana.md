# Contrato — la consola dentro de la ventana (spec 010)

> **Este contrato se reescribió el 2026-09-18.** Se llamaba «la consola en modo
> embebido» y fijaba qué partes de su armazón se ocultaba la consola al
> detectar la aplicación de escritorio por user-agent. Ese modo **se retiró**:
> ver `decision.md`, «D1-A se revierte a medias». Lo que sigue es lo que rige.

La consola es la misma aplicación web de siempre, y dentro de la ventana de
escritorio **se pinta entera y tal cual es**: su barra lateral, su búsqueda, sus
avisos y su identidad. No se le pide nada.

## La regla

**`apps/console` no sabe que la aplicación de escritorio existe.** No hay modo,
no hay bifurcación de armazón, no hay despliegue acoplado. La única detección
por user-agent que queda en la consola es la de la spec 002 —el control de
conectar canales de Meta, que dentro de la ventana no funciona— y su test
afirma que `isDesktopShell` se importa **exactamente una vez** fuera de su
módulo: una segunda bifurcación exige su propia spec.

## Cómo se coloca

| | |
|---|---|
| **Dónde** | Desde `STRIP_HEIGHT` hacia abajo, a todo lo ancho de la ventana |
| **Qué queda encima** | La franja, siempre. La ventana no tiene barra de título nativa: ahí viven los semáforos, la región de arrastre y la vuelta |
| **Apilado** | La vista de la consola se añade **después** de la del armazón, o queda debajo de una vista opaca de pantalla completa y el panel se ve negro. `tests/view-stacking.test.ts` lo vigila |
| **Visibilidad** | Aparece y desaparece; el armazón no se oculta nunca |

## Cómo se entra y cómo se vuelve

**Una sola puerta.** «Abrir la consola» al pie de la lista lateral, o cualquier
sección desde la búsqueda (⌘K) — que es lo que hace que un tope lleve a
`/billing` y no a «búscalo tú». La lista canónica de `sections.ts` sirve para
eso y sólo para eso: **por qué ruta abrir la consola**.

**Una sola vuelta.** «Volver al equipo», en la franja, alcanzable con el
teclado. Vive ahí porque con la consola delante la franja es la única superficie
de la aplicación que queda a la vista.

## Lo que la consola sigue sin tener

**`preload`.** La vista de la consola no tiene ninguna vía de hablarle a la
cáscara (002 R12.1), y eso no cambia. El canal entre las dos sigue siendo la
persona.

## Por qué se retiró el modo embebido

Se construyó y se miró funcionando. En la misma ventana había **dos barras
laterales, dos buscadores, dos campanas y dos identidades**, y el glosario ya
había empezado a separarse: `nav.knowledge` decía «Playbook» donde la aplicación
decía «Conocimiento». Dos navegaciones son dos vocabularios que divergen.

El modo existía para quitarle a la consola su armazón y que cupiera dentro del
otro: un cambio en `apps/console` **que existía sólo para servir a la aplicación
de escritorio**, y que obligaba a desplegar las dos a la vez. Acoplamiento entre
dos aplicaciones para conseguir algo que la consola ya hacía bien sola.
