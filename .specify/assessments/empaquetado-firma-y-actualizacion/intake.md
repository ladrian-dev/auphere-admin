# Idea Intake: empaquetar, firmar y actualizar la aplicación de escritorio

- **Slug**: empaquetado-firma-y-actualizacion
- **Created**: 2026-09-11
- **Source**: conversación con Luis al cerrar la spec 003 («¿qué necesito para
  obtener las firmas y certificados de Apple para poder instalarla en otros
  computadores Mac? ¿y cómo es el proceso de update?») · punteros al repositorio:
  `apps/desktop/package.json` (bloque `build`), `apps/desktop/src/electron/`,
  `.github/workflows/` · specs previas: `001-puesto-trabajo-partner` (§R9, la
  distribución), `002-identidad-app-escritorio`, `003-teammates-app-escritorio`
- **Type**: new-capability

## Idea (as captured)

> Ya tengo cuenta de Developer Program de Apple ya que tenemos apps móviles ahí,
> así que tendría todo… ¿qué necesito para obtener las firmas y certificados
> para poder instalarla en otros computadores Mac? ¿Y cómo es el proceso de
> update de las app desktop?

Dicho con la spec 003 terminada: la aplicación funciona en la máquina de Luis y
no hay forma de ponerla en la máquina de nadie más.

## Restated

La aplicación de escritorio existe y está probada, pero **solo se ejecuta desde
el repositorio**. Para que un partner la instale hace falta empaquetarla,
firmarla con una identidad que macOS acepte, notarizarla, y tener una manera de
que la versión que ya instaló se actualice sola. Nada de eso existe hoy.

La evaluación decide el alcance de esa pieza: qué se firma, por dónde se
distribuye, cómo se actualiza sin interrumpir trabajo en marcha, y qué de todo
esto es superficie de confianza nueva.

## Lo que hay hoy, verificado en el repositorio

| Pieza | Estado el 2026-09-11 |
|---|---|
| `build` de `electron-builder` | Mínimo: `appId`, `productName`, `files`, `mac.category`, `mac.hardenedRuntime: true`. Sin `entitlements`, sin `notarize`, sin `publish`, sin icono de aplicación |
| `electron-updater` 6.8.9 | **Instalado y sin usar**: ninguna línea del código lo importa |
| Integración continua | `ci.yml` no construye ni empaqueta `apps/desktop` |
| Icono | Solo el de bandeja (`assets/trayTemplate.png`, generado en la 003). No hay icono de aplicación ni `.icns` |
| Versión | `0.1.0`, sin canal ni releases |
| Windows | `win: null` — apagado a propósito |
| Identificación de versión | La app ya se anuncia: `AuphereDesktop/<version>` en el agente de usuario de la vista de consola, y `app_version` en el latido del puente |

## Lo que Luis ya tiene, y lo que **no** se sigue de eso

Tiene **Apple Developer Program como organización**, con apps móviles
publicadas. Eso resuelve lo que suele ser el trámite largo: el alta, el número
D-U-N-S y la verificación de la entidad.

Lo que **no** se sigue: los certificados de las apps móviles (`Apple
Distribution` / `iOS Distribution`) **no sirven** para distribuir fuera de la
App Store. Hace falta uno de tipo **Developer ID Application**, que es otra
cosa, solo lo puede crear el titular de la cuenta o un administrador, y es
probable que no exista todavía en ese equipo. Conviene comprobarlo antes de
planificar: es la única dependencia externa que queda.

## Preguntas que abre

1. ¿Por dónde se distribuye y por dónde se actualiza? (almacenamiento propio en
   AWS, releases de GitHub, otra cosa)
2. ¿Qué pasa con una actualización cuando hay una tarea esperando una decisión o
   un comando corriendo en la máquina?
3. ¿Entra Windows en esta pieza o va después?
4. ¿Puede la plataforma exigir una versión mínima, y qué ve quien no la tiene?
5. ¿Quién firma: una persona con su llavero o la integración continua con una
   clave guardada como secreto?
