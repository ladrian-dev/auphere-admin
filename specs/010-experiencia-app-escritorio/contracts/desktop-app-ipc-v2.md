# Contrato — el canal de la pantalla, enmendado (spec 010)

**Enmienda de** `specs/003-teammates-app-escritorio/contracts/desktop-app-ipc.md`.
Aquel contrato sigue siendo la base: **nada se retira**, se añaden los canales que
el armazón necesita y los que llegan del puesto de trabajo al absorberse
(`specs/002-*/contracts/desktop-bar.md`).

Las tres reglas que **no** cambian, y sus tests:

1. La lista es cerrada y el `preload` expone **una función por canal**, nada
   genérico (`app-ipc.test.ts`).
2. La entrada **se valida, no se adivina**: canal desconocido, identificador mal
   formado o valor fuera del juego lanzan antes de tocar la red.
3. Nada de lo que sale lleva sesión, cookie, token, credencial ni autorización, a
   ninguna profundidad (`no-credentials-over-ipc.test.ts`).

---

## Invocaciones que se añaden

| Canal | Entrada | Salida | Qué hace el principal |
|---|---|---|---|
| `app:shell.showSection` | `{section}` — una de la lista canónica (§ Secciones) | `void` | Si es de administrar, muestra la consola en la ruta que corresponde; si es de operar, oculta la vista de la consola |
| `app:shell.contentBounds` | `{x, y, width, height}` en píxeles lógicos, enteros ≥0 | `void` | Coloca la vista de la consola exactamente en ese rectángulo. **Solo números**; el principal lo acota al tamaño de la ventana y **nunca** permite invadir la franja superior |
| `app:shell.prefs` | `{theme?: "system"\|"light"\|"dark", sidebarWidth?: number, silenceAviso?: boolean}` | el estado resultante | Escribe en las preferencias locales y aplica el tema con el mecanismo del sistema, que arrastra también a la consola |
| `app:signIn.start` | — | `{state}` | Arranca la entrada por navegador ya existente (oyente efímero en bucle local + PKCE, spec 009) y abre el navegador |
| `app:signIn.cancel` | — | `void` | Cierra el oyente y deja la espera en `cancelada` |
| `app:workstation.state` | — | `WorkstationState` (§ Puesto) | El estado del puesto, con su causa y sus acciones |
| `app:workstation.pair` | `{code}` — 8 símbolos del alfabeto de emparejamiento | `{ok}` \| `{error}` | Canjea el código **con la sesión de la partición humana**. El código lo teclea la persona; no se guarda |
| `app:workstation.unpair` | — | `{ok}` | Desempareja esta máquina |
| `app:workstation.pickDirectory` | `{client_ref}` | `{path_shown}` \| `{error: "invalid"\|"cancelled", reason?}` | Abre el selector nativo y declara el directorio. **El motivo del rechazo se devuelve**: hoy se pierde |
| `app:setup.status` | — | `SetupChecklist` (§ Puesta en marcha) | Pasos pendientes del partner y de esta máquina, derivados de lo que ya existe |
| `app:update.install` | — | `void` \| `{error: "busy"}` | Instala la versión descargada. **Si hay trabajo vivo, no instala y lo dice** |
| `app:handoff.done` | `{kind: "sign_in"\|"payment"}` | `{plan, usage}` refrescados | La persona vuelve del navegador: se relee lo que pudo cambiar, sin reiniciar |

## Suscripciones que se añaden

| Canal | Payload | Cuándo |
|---|---|---|
| `app:console.location` | `{section, path}` — la ruta **de la propia consola**, acotada a rutas conocidas | Cada vez que la vista de la consola navega, para que la lista lateral marque dónde está |
| `app:workstation` | `WorkstationState` | Cada cambio de estado del puesto (sustituye al empuje de la barra) |
| `app:signIn` | `SignInState` (§ Entrada) | Cada cambio de la espera del navegador |
| `app:update` | `UpdateState` (§ Actualización) | Descargada, esperando a que termine el trabajo, no admitida |
| `app:waiting` | `Waiting` — el **derivado único** (§ Lo que te espera) | Cada cambio de lo que espera decisión. Sustituye a `app:inbox` como fuente del número |
| `app:connectivity` | `{state: "online"\|"offline"\|"unconfirmed", since}` | Cambios de conectividad, para que «sin red» deje de confundirse con «sin sesión» |
| `app:shell.toggleSidebar` | `{}` | La orden de menú «Mostrar u ocultar la lista lateral» (⌘B). El menú es del proceso principal y el estado de la lista es de la pantalla: éste es el único camino entre los dos |

`app:inbox`, `app:inbox.focus`, `app:inbox.changed`, `app:event`, `app:task.state`,
`app:session` y `app:presence` **siguen igual**.

## Secciones canónicas

`app:shell.showSection` y `app:console.location` hablan el mismo vocabulario
cerrado. Cualquier otro valor se rechaza en la validación de entrada.

| Sección | Dónde vive | Ruta de consola | Permiso (el de la consola) |
|---|---|---|---|
| `hoy` · `pendientes` · `teammate` · `cuenta` · `puesta_en_marcha` | pantalla de la aplicación | — | — |
| `inicio` | consola | `/` | — |
| `clientes` | consola | `/clients` | `clients:read` |
| `conocimiento` | consola | `/knowledge` | `playbook:read` |
| `puesto` | consola | `/workstation` | `workstation:read` |
| `consumo` | consola | `/usage` | `usage:read` |
| `auditoria` | consola | `/audit` | `audit:read` |
| `notificaciones` | consola | `/notifications` | `partner:read` |
| `equipo` | consola | `/team` | `team:read` |
| `claves` | consola | `/keys` | `keys:read` |
| `facturacion` | consola | `/billing` | `billing:read` |

**La lista de secciones de consola es exactamente la navegación que la consola ya
declara**, con sus mismos permisos: integrar la consola **no puede** dejar
ninguna sección fuera de alcance. Si la consola añade una entrada, esta lista se
amplía en el mismo cambio; un test de la consola lo afirma.

Regla: **la aplicación pide secciones, no URLs**. `app:openConsole` (que sí acepta
una ruta) se conserva para los enlaces contextuales que ya existen, con su
validación actual —ruta que empieza por `/` y no por `//`—, y ahora además emite
`app:console.location`.

## Formas nuevas

### Puesto (`WorkstationState`)

```
{
  status: "comprobando" | "sin_sesion" | "sin_emparejar" | "emparejando"
        | "conectada" | "reconectando" | "volver_a_emparejar"
        | "archivada_desde_consola" | "version_no_admitida",
  machine_name?: string,
  since: string,                 // ISO-8601: desde cuándo está en este estado
  required_version?: string,     // solo en `version_no_admitida`
  cause?: "sin_red" | "sin_ejecutor" | "sesion_perdida" | "desconocida",
  missing_directories?: number,
  last_error?: { code, message_key },
  actions: ("emparejar" | "desemparejar" | "directorios" | "actualizar")[]
}
```

- `comprobando` es **nuevo** y resuelve la mentira del primer pintado: hasta el
  primer veredicto no se dice «no emparejada».
- `cause` es **nuevo** y resuelve el `reconectando` perpetuo: cuando en la máquina
  no hay quien ejecute, se dice (`sin_ejecutor`), no se deja «reconectando» sin fin.
- Los ocho estados heredados y sus transiciones no cambian de significado.

### Entrada por navegador (`SignInState`)

```
{ state: "idle" | "esperando" | "vuelto" | "cancelada" | "caducada" | "error",
  since?: string, error_key?: string }
```

### Actualización (`UpdateState`)

```
{ state: "idle" | "descargando" | "lista" | "esperando_trabajo",
  version?: string }
```

**Un hecho, una fuente**: «esta versión ya no se admite» **no** está aquí. Es un
estado del puesto (`version_no_admitida`, heredado del contrato de la 002),
porque lo que describe es que **la máquina no puede trabajar**, y lleva su
`required_version`. `UpdateState` solo describe el ciclo de la descarga.

### Lo que te espera (`Waiting`)

```
{ count: number,                 // el MISMO número en todas las superficies
  items: { action_id, teammate_id, level, since }[] }
```

### Puesta en marcha (`SetupChecklist`)

```
{ steps: { key, state: "hecho" | "pendiente" | "no_aplica",
           section?: Section, blocked_reason_key?: string }[] }
```

## Lo que no existe y no existirá aquí

Sigue vigente la lista del contrato de la 003 —`fs`, `shell`, `child_process`,
URLs arbitrarias, lectura de cookies o tokens— y se añade:

- **Ningún canal desde la consola.** La consola no tiene `preload`: todo lo que
  el armazón sabe de ella lo observa el proceso principal.
- **`app:shell.contentBounds` no acepta nada que no sean cuatro números**, y el
  principal impone el mínimo: la franja superior nunca se cubre.
- **`app:workstation.pair` no devuelve el código ni lo persiste**, y su entrada se
  valida contra el alfabeto de emparejamiento antes de salir a la red.
- **Ningún canal aprueba nada**: decidir sigue siendo `app:inbox.decide`.
