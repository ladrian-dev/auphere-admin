# Implementation Plan: la aplicación se instala, y se arregla sola

**Branch**: `008-empaquetado-firma-y-canal` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-empaquetado-firma-y-canal/spec.md`

## Summary

Construir la cadena que empaqueta, firma, notariza y publica la aplicación de
escritorio, y el sitio donde publicarla. El **cliente ya está escrito**: el
commit `e100564` trae entitlements, la política de actualización (pura y con 117
líneas de test), el actualizador que verifica su propia firma y la configuración
de empaquetado. Lo que falta es la mitad que no es código de cliente — el trabajo
de integración continua sobre un runner de macOS, sus secretos, el canal en AWS y
su nombre— más tres piezas pequeñas que la spec destapó: **un estado de barra que
no existía**, la **puerta de versión mínima** en el latido, y el **número de
aprobaciones pendientes**, que la política ya pide y nadie le pasa.

**Hay un bloqueante que no se resuelve programando** (research D2): la clave
privada del certificado vive sólo en el llavero de una máquina y **no hay copia**.
Sin un `.p12` exportado, R5.1 —firmar sin depender del llavero de nadie— no se
puede cumplir. Es la primera tarea y detiene el resto.

## Technical Context

**Language/Version**: TypeScript / Electron 44 (`apps/desktop`, pnpm) · Python
3.11 (`apps/api`, la puerta de versión mínima) · HCL (Terraform) · YAML (GitHub
Actions)

**Primary Dependencies**: `electron-builder` 26 y `electron-updater` 6.8, **ya
instaladas** (MIT). `codesign`, `notarytool` y `stapler` vienen con Xcode.
`aws-actions/configure-aws-credentials`, ya usada por `deploy-prod.yml`.
**Ninguna nueva.**

**Storage**: un bucket S3 privado tras CloudFront para el canal. En base de
datos, sólo la configuración de la versión mínima admisible — de plataforma, sin
`tenant_id`.

**Testing**: `vitest` (`apps/desktop`) · `pytest` (la puerta del latido) ·
`terraform validate` · y el paso que **no se puede automatizar**: abrir el
artefacto en un Mac limpio.

**Target Platform**: macOS, Apple Silicon e Intel. **Windows queda fuera** y no
por falta de tiempo: la contención de escrituras no está portada, y empaquetar
allí prometería una garantía que no se cumple.

**Project Type**: aplicación de escritorio + cadena de distribución

**Performance Goals**: no aplica. El canal sirve unas pocas descargas; el
actualizador comprueba cada cuatro horas.

**Constraints**: **el runner de macOS es el primero del repo** — todos los
trabajos actuales corren en `ubuntu-latest` y éste cuesta más por minuto, así que
corre sólo al publicar. AWS por **OIDC**, como el resto. El certificado de
CloudFront va en `us-east-1` aunque todo lo demás esté en `eu-south-2`.

**Scale/Scope**: tres partners, pocas instalaciones. Es lo que hace defendible
un canal único sin publicación gradual (spec, R3.6).

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | **Ninguna de las 7 garantías se toca**: no hay tenant, ni RLS, ni herramienta nueva. La versión mínima es configuración de plataforma sin `tenant_id`, como `model_profiles`. La prueba que esta superficie sí exige es de **integridad de artefacto** y está en R1.5, R3.4 y R3.5 |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Se abre **una nueva y se declara**: el canal puede reemplazar el binario que ejecuta comandos en la máquina del partner. No cabe dentro de la actual —la alternativa es reinstalar a mano cada corrección, que es no tenerlo— y se abre **por su mitad barata**: sólo macOS, sólo lectura, publicando sólo desde la cadena |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | **No aplica**: ningún contenido nuevo llega a un modelo. Lo que el canal entrega es un binario, y lo que decide si se aplica es una firma, no un texto |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Instalar una actualización **no** es una acción de agente y no entra en la lista cerrada. Pero la política **respeta** las que sí lo son: mientras haya una aprobación pendiente, no se instala (R3.2). Y publicar deja rastro de quién disparó la cadena (R2.4, R2.6) |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Es la puerta que `/speckit-clarify` destapó. La barra gana **un** estado que distingue «lista» de «esperando, y por esto»; sin versión esperando **no muestra nada** — ni indicador apagado ni explicación de lo que no hay |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | **No aplica**: no interviene ningún agente |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | El cliente rescatado trae sus pruebas y **corren antes de construir nada** (R6.2). Lo que no se puede automatizar —abrir el artefacto en un Mac limpio— se declara como paso manual del quickstart en vez de fingirse con un test |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ☑ | **Ninguna dependencia nueva.** `electron-builder` y `electron-updater` ya están (MIT); las herramientas de firma vienen con Xcode; la acción de credenciales ya se usa |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[teammates/14-mvp-y-fases]]` §1 más el assessment `empaquetado-firma-y-actualizacion` (veredicto *go*). La memoria de firma de macOS queda reflejada en los supuestos de la spec |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | **Ninguna de las 7.** Pero la superficie nueva exige su propia prueba, de otra naturaleza: **un artefacto manipulado no se instala** y **un binario sin firma de distribución no consulta el canal**. No va en `tests/isolation/` porque no es aislamiento entre tenants; va donde vive la política, y es igual de bloqueante | tareas de integridad en `apps/desktop/tests/` |
| **Licencias** — ¿qué dependencia nueva entra? | **Ninguna** | — |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Nada que se mida.** No consume modelo, reloj de máquina ni herramienta de pago. El coste del canal es de infraestructura y se ve donde ya se ven los demás | — |

## Project Structure

### Documentation (this feature)

```text
specs/008-empaquetado-firma-y-canal/
├── plan.md · spec.md · research.md · data-model.md · quickstart.md
├── checklists/requirements.md
├── contracts/release-channel.md
└── tasks.md                      # lo genera /speckit-tasks
```

### Source Code (repository root)

```text
apps/desktop/                     # RESCATADO de e100564, no reescrito
├── build/entitlements.mac.plist
├── package.json                  # dmg + zip, arm64 + x64, notarize, publish
└── src/
    ├── update-policy.ts          # pura y probada — se le pasa el dato que le falta
    ├── electron/updater.ts
    ├── bar-state.ts              # + el estado nuevo (§V)
    └── stream-hub.ts             # liveCount, ya añadido

.github/workflows/
└── release-desktop.yml           # NUEVO — el primer trabajo en macos-latest

infra/terraform/40-releases/      # NUEVO: hoy no hay ni un .tf
├── main.tf                       # bucket privado + CloudFront con OAC
├── iam.tf                        # el rol OIDC que publica, distinto del que despliega
└── (prod.tfplan se BORRA — plan binario huérfano)

apps/api/src/nexus_api/
├── api/device_bridge.py          # la puerta de versión mínima, en el latido
└── config.py                     # el mínimo admisible, ausente por defecto

docs/desktop-workstation.md       # spec viva: cadena, canal y estado nuevo
specs/001-puesto-trabajo-partner/tasks.md   # T057 dejó de estar bloqueada
```

**Structure Decision**: la mayor parte del trabajo **no cae en código de
producto**, sino en integración continua e infraestructura — y eso es lo que hace
que esta spec sea de superficie y no de funcionalidad. El código de cliente se
**rescata** con un cherry-pick, no se reescribe (R6.1), y sólo se le añaden las
tres piezas que le faltan.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **Un runner de `macos-latest`**, el primero del repo, más caro por minuto | Firmar y notarizar para macOS **sólo se puede hacer en macOS**. No hay alternativa técnica | **Firmar desde el portátil**: hace que la cadena dependa de una máquina y de un llavero — y research D2 demuestra que ese riesgo ya es real, no hipotético. Se acota corriendo sólo al publicar, nunca en cada `push` |
| **Un rol de AWS distinto del de despliegue** | Es lo que hace **comprobable** R2.2: el rol que despliega no puede publicar versiones y el que publica no puede tocar ECS | **Reutilizar el rol de despliegue**: un solo rol con los dos permisos convierte cualquier compromiso del despliegue en la capacidad de poner un binario en la máquina de un partner |
| **Tres piezas de producto que la spec destapó** (estado de barra, puerta de versión mínima, aprobaciones pendientes hacia la política) | Sin el estado, §V se incumple y la persona no sabe por qué la app no se actualiza. Sin la puerta, cuando haga falta ya habrá versiones viejas instaladas. Sin las aprobaciones, la política decide con medio dato | Ninguna es opcional; las tres son pequeñas y están acotadas |

> Ninguna añade dependencias. La primera añade coste, y las otras dos reducen
> riesgo.

## Re-evaluación del Constitution Check tras el diseño

Las nueve filas siguen en verde, y **el diseño movió una a mejor**: §V pasó de
apoyarse en «los estados que la pantalla ya tiene» —que no existían— a declarar
el estado que falta y su ausencia diseñada.

Lo que el diseño **no** cambió: sigue sin tocar ninguna garantía de aislamiento
entre tenants (§I), sin dependencias nuevas (§VIII) y sin acciones `mutates`
nuevas (§IV). La superficie nueva sigue siendo una sola y sigue abriéndose por su
mitad barata (§II).
