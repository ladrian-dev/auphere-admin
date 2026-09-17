# Contrato — el armazón de la ventana (spec 010)

Qué compone la ventana, quién manda en cada píxel y qué invariantes no se pueden
romper en un refactor. Verificado con el spike de la Fase 0
([research.md §D1](../research.md)).

## Las vistas

| Vista | Partición | `preload` | Qué carga | Rectángulo |
|---|---|---|---|---|
| **Armazón** (`app`) | `auphere-app`, no persistente | `app-preload.cjs`, lista cerrada | la pantalla local | **toda la ventana** |
| **Consola** | `persist:auphere-console` | **ninguno** | la consola, en modo embebido | solo el **panel de contenido**, cuando la sección activa es de administrar |
| ~~Puesto~~ | — | — | — | **se retira** (absorbida) |

La partición del ambiente del agente (`auphere-agent`) sigue existiendo, sin
vista, y sin alcanzar a ninguna de las otras. **Tres particiones**, comprobadas
al arrancar: si alguien las iguala en un refactor, la aplicación **no arranca**.

## Geometría e invariantes

```
        0                    SIDEBAR                                 ancho
        ├────────────────────┬──────────────────────────────────────────┤
   0    │  franja superior (STRIP) — arrastra la ventana                │
  STRIP ├────────────────────┼──────────────────────────────────────────┤
        │  lista lateral     │  panel de contenido                      │
        │  (redimensionable) │  (pantalla local  ·o·  vista consola)    │
 alto   └────────────────────┴──────────────────────────────────────────┘
```

**Invariantes** (cada una con test):

1. **Una sola vista posee las regiones de arrastre**: la del armazón, y solo en
   la franja superior. Ninguna otra vista declara `drag`.
2. **Ninguna vista puede solaparse con la franja superior.** El rectángulo del
   panel siempre empieza en `y ≥ STRIP`. Es lo que evita el fallo conocido de
   Electron con regiones de arrastre en vistas apiladas.
3. Los controles dentro de la franja (búsqueda, estado) se marcan como **no
   arrastrables**.
4. La franja reserva a su izquierda el hueco de los controles de ventana del
   sistema, y su posición se fija explícitamente.
5. Las vistas se ocultan **por visibilidad**, nunca moviéndolas fuera de la
   pantalla.
6. La ventana se crea con un **color de fondo** tomado del tema activo y **no se
   muestra hasta que la vista del armazón está lista**: sin destello.
7. El tamaño mínimo garantiza que ninguna acción quede inalcanzable; por debajo
   de un ancho umbral la lista lateral se colapsa.
8. `titleBarStyle` oculto: el título de la ventana es el objeto en el que se está
   (teammate o sección), **nunca** «Auphere» a secas.

## Ciclo de vida

| Evento | Comportamiento |
|---|---|
| Arranque | La ventana aparece pintada. **La carga de la consola no bloquea** la puesta en marcha: el veredicto de sesión, el vigilante de pendientes y el latido arrancan en paralelo, y un fallo de red no aborta nada |
| Cerrar la ventana | **Oculta**, no sale. El icono de la barra del sistema y los avisos siguen vivos |
| Reabrir desde el icono o el Dock | Muestra la ventana donde estaba, en la última sección |
| Salir | Orden explícita del menú o del icono. **Advierte si hay trabajo vivo** |
| Segunda instancia | Trae la primera al frente |
| Cambio de tema del sistema | Una sola fuente decide, y arrastra a la consola embebida |

## Menú y teclado

**Menú de aplicación completo**, con todo lo del armazón representado:

| Menú | Contenido mínimo |
|---|---|
| Aplicación | Acerca de (con la versión), Ajustes (⌘,), Buscar actualizaciones, Ocultar, **Salir** |
| Archivo | Nuevo teammate (⌘N) |
| Edición | Deshacer, rehacer, cortar, copiar, pegar, seleccionar todo, **Buscar (⌘F)** |
| Ver | Hoy, Pendientes, Cuenta, secciones de administrar, Mostrar/ocultar lista lateral (⌘B), **Zoom ⌘+ / ⌘− / ⌘0**, Pantalla completa, Recargar la sección |
| Ir | Atrás (⌘[), Adelante (⌘]), Ir a la lista lateral / al panel / al puesto (F6 y ⇧F6) |
| Ventana | Minimizar, Zoom, traer al frente |
| Ayuda | Ayuda de Auphere, notas de la versión |

- **⌘K**: una sola búsqueda de acciones y objetos, que muestra el atajo de cada
  acción que lo tenga.
- Los atajos reservados por el sistema operativo **no se reutilizan**.
- Todo lo que el armazón hace **existe como orden del menú**, incluido lo que
  antes solo vivía en la barra del puesto.

## Qué se retira

- La vista del puesto, su partición y su `preload` de siete funciones.
- El menú «Ver → Equipo / Consola» y los atajos de cambio de superficie: esa
  distinción deja de existir para la persona.
- La recarga de la consola al volver a ella: se muestra donde estaba.
