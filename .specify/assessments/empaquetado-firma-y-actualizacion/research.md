# Research: empaquetar, firmar y actualizar la aplicación de escritorio

- **Slug**: empaquetado-firma-y-actualizacion
- **Fecha**: 2026-09-11
- **Alcance**: lo que hace falta para que la aplicación se instale y se
  actualice en la máquina de un partner. Se recoge aquí para que la sesión que
  escriba la spec no vuelva a derivarlo.

> **Aviso de procedencia.** Lo de §1 y §2 es conocimiento del ecosistema de
> Apple y de `electron-builder`, no algo leído en el repositorio ni verificado
> contra la documentación de Apple **en esta sesión**. Los nombres de los
> certificados, de las herramientas y de los permisos son estables desde hace
> años, pero antes de escribir la spec conviene contrastar contra la
> documentación vigente y, sobre todo, **mirar qué hay ya en el equipo de Apple
> de Auphere**. Lo de §4 sí está verificado en el repositorio.

## 1. La cadena de Apple, pieza a pieza

Cuatro cosas distintas que se confunden con facilidad:

| Pieza | Qué es | Cuándo se toca |
|---|---|---|
| **Membresía** | La cuenta del Developer Program | Ya la hay |
| **Certificado Developer ID Application** | La identidad con la que se firma una app que se distribuye **fuera** de la App Store | Una vez; vale cinco años |
| **Notarización** | Apple analiza el binario y devuelve un ticket | En **cada** versión |
| **Grapado** (`stapler`) | Pegar ese ticket al artefacto para que funcione sin red | En cada versión |

Sin lo segundo, macOS no deja abrir la app. Sin lo tercero, Gatekeeper la
bloquea con el aviso de «no se puede comprobar que no contenga malware». Sin lo
cuarto, la primera apertura exige conexión a Apple.

**El *Developer ID Installer* solo hace falta para distribuir un `.pkg`.** Con
DMG o ZIP no entra en juego.

## 2. Lo que esta aplicación necesita de más

No es un Electron cualquiera: ejecuta comandos en la máquina de la persona.

- **Permisos (`entitlements`) del *hardened runtime*.** El motor de JavaScript
  necesita compilar en memoria, así que hacen falta al menos los de JIT y
  memoria ejecutable sin firmar; los binarios auxiliares de Electron necesitan
  heredarlos. Si algún día entra un módulo nativo, puede hacer falta relajar la
  validación de librerías — y eso sí conviene pensarlo dos veces, porque es
  exactamente la protección que impide cargar código ajeno en el proceso.
- **Consentimiento del sistema (TCC).** Los comandos que la app lanza corren
  **como la app**, así que heredan sus permisos de acceso a carpetas. La primera
  vez que un teammate trabaje en un directorio, macOS lo preguntará. Eso no es
  un fallo: es el momento en que la 002 ya pide declarar el directorio, y la
  spec tiene que decidir si esa pantalla explica lo que va a pasar o deja que
  aparezca un diálogo del sistema sin contexto.
- **La App Store no es el canal.** Su caja de arena impide ejecutar programas
  arbitrarios, que es justamente lo que la 001 y la 003 construyeron. Developer
  ID es el camino correcto, y conviene escribirlo para que nadie lo reabra.

## 3. La actualización

`electron-updater` sobre el mecanismo de actualización de macOS exige dos cosas:

1. **que la app esté firmada** — el actualizador comprueba que la versión nueva
   está firmada por la misma identidad antes de aplicarla; sin firma no hay
   actualización automática, y esto es lo que hace que §2 sea requisito previo y
   no un paso paralelo;
2. **un canal que sirva un manifiesto y un ZIP.** El DMG es para la primera
   instalación; la actualización se descarga como ZIP.

Tres decisiones que la spec tiene que tomar y que no son técnicas:

- **Dónde vive el canal.** El resto de la plataforma está en AWS, así que
  almacenamiento con CDN delante encaja. Los releases de GitHub obligan, en
  repositorio privado, a incrustar un token en el cliente.
- **Cuándo se aplica.** Descargar en segundo plano y aplicar **al salir**. Esta
  aplicación no puede reiniciarse sola: puede haber una tarea `esperandote` o un
  comando corriendo en la máquina del partner. Hay estados diseñados para
  decirlo; la actualización tiene que usarlos, no inventar un diálogo.
- **A cuánta gente a la vez.** Despliegue por porcentaje. Una versión que rompa
  el puente deja a todo el mundo sin teammates, y el puente es saliente: no hay
  forma de empujar un arreglo.

Y una que es de la plataforma, no de la app: **versión mínima exigible**. La app
ya envía su versión en cada latido y en el agente de usuario, así que la API
puede rechazar una demasiado vieja. Añadirlo ahora es barato; añadirlo cuando
haya versiones viejas en la calle, no.

## 4. Lo verificado en el repositorio

- `apps/desktop/package.json` → `build` sin `entitlements`, sin `afterSign`, sin
  `publish`; `mac.hardenedRuntime: true` ya está puesto (y sin permisos
  declarados, el JIT fallaría al arrancar una vez firmada: es el primer síntoma
  que se verá).
- `electron-updater` está en `devDependencies` y **no lo importa nadie**. Para
  usarse tendría que pasar a `dependencies`: va dentro del binario.
- `ci.yml` no construye `apps/desktop`.
- La app ya se identifica con su versión en dos sitios
  (`app-runtime.ts` → `app_version` del latido; `main.ts` → agente de usuario).
- `apps/edition/` existe con su `THIRD-PARTY-LICENSES.md`: la edición sobre
  KiroCrew es **otro** empaquetado y no entra aquí salvo que se decida lo
  contrario.

## 5. Windows

Está en el alcance del producto según la KB, pero es otra cadena entera:
certificado con almacenamiento en hardware o en un servicio de firma, y otro
instalador. Meterlo en la misma spec duplica el alcance; dejarlo fuera obliga a
decir cuándo entra.
