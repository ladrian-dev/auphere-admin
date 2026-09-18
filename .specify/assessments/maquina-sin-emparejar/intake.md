# Idea Intake: la máquina se registra con la sesión, sin código

- **Slug**: maquina-sin-emparejar
- **Created**: 2026-09-18
- **Source**: sesión del 2026-09-18. Luis, probando la 0.1.5: «las apps como
  Claude y Grok nunca hice un paso de emparejar la máquina, solo me pidieron
  acceso a los archivos y ya» · puntero al repositorio: `apps/desktop`
  (`app-runtime.ts`, `credential-store.ts`, `http-transport.ts`),
  `apps/api/src/nexus_api/api/device_bridge.py`,
  `apps/console/src/components/workstation/pairing-dialog.tsx` · specs de origen:
  `001-puesto-trabajo-partner`, `002-identidad-app-escritorio`
- **Type**: improvement (retirar un paso que ya no prueba nada)

## La idea

Retirar el **código de emparejamiento de 8 símbolos**. La aplicación pide su
credencial de máquina contra el BFF con la sesión que ya tiene, igual que
`/api/desktop/redeem` canjea el código de entrada.

## Lo que hacen los referentes (investigado el 2026-09-18)

| | Identidad de la máquina | Acceso a archivos | Dónde corre el agente |
|---|---|---|---|
| **Claude Code Remote Control** | `/login` por navegador, **y nada más** | Servidores MCP con directorios en lista blanca | En la máquina |
| **Grok** | La sesión de la app | «Selecciona y **confía** tu directorio» + Ask · Allow once · Allow for session · YOLO | En la máquina, por su CLI |
| **Auphere hoy** | Entrar por navegador (spec 009) **+ teclear un código** | Directorio por cliente, en una hoja que casi no se veía | En la plataforma |

El caso que más se parece es **Remote Control**, y es el que cierra el
argumento: tiene la misma arquitectura que el puente de Auphere —proceso local
que hace **solo peticiones salientes y no abre ningún puerto entrante**,
coordinado desde la nube, con credenciales cortas de un solo propósito— y para
enlazar la máquina con la cuenta su documentación dice exactamente esto:

> **Authentication**: run `claude` and use `/login` to sign in through claude.ai
> if you haven't already.

Fuentes: <https://code.claude.com/docs/en/remote-control> ·
<https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop> ·
<https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/22-permissions-and-safety.md>

## El argumento

**Se hacen dos actos para probar una sola cosa.** Entrar por el navegador ya
demuestra que eres tú, de ese partner, en esta máquina. El código vuelve a
demostrar lo mismo, con una vuelta por la consola, un copiar y pegar y una
caducidad de diez minutos.

**Que el agente corra en la plataforma no lo justifica.** Es la diferencia real
con Claude y Grok, pero Remote Control demuestra que un puente saliente
coordinado desde la nube se enlaza igual: con la sesión.

**Y hay precedente en este repo.** La spec 009 retiró un código tecleado —el de
iniciar sesión, «un RFC 8628 hecho a mano y al revés»— y lo sustituyó por el
flujo de navegador (`ADR-039`). El de emparejar es la misma forma de cosa y
nadie lo ha revisado desde entonces.

**El acto deliberado está en el sitio equivocado.** Claude y Grok tienen
exactamente uno, y es sobre **archivos**: «confía este directorio». Auphere tiene
la ceremonia sobre la caja y los directorios enterrados. Debería ser al revés —
la decisión que importa es qué carpeta toca un teammate, no qué Mac es éste.

**La mitad buena ya está construida**: la política de ejecución local
(Preguntar · Permitir siempre · Nunca, por ejecutable) **es** el sistema de
niveles de Grok, y el selector nativo por cliente es su «trust this directory».

## Forma propuesta

1. La app, con sesión confirmada, pide la credencial al BFF con la cookie de la
   partición humana (el camino que `/api/desktop/redeem` ya usa).
2. El BFF comprueba `workstation:pair` en el principal —la misma garantía que
   hoy da el permiso para **pedir** el código— y devuelve la credencial una vez.
3. Entrar deja la máquina lista. Sin diálogo y sin pantalla intermedia.
4. El momento deliberado sube de sitio: **declarar el directorio del cliente**.
5. Se conserva el código solo si existe el caso de emparejar una máquina que no
   es la tuya (servidor, máquina compartida). **Hay que confirmar si existe.**

## Lo que hay que decidir, no dar por hecho

- **Qué protege hoy el código que la sesión no proteja.** Es la pregunta
  central y no debe responderse por analogía: la cookie vive en la partición
  persistente y puede estar ahí de antes, mientras que teclear un código es
  siempre un acto del momento. Si esa diferencia importa, la respuesta no es el
  código: es exigir una sesión **recién confirmada** para el canje.
- Si una persona con `workstation:pair` puede registrar una máquina ajena.
- Qué pasa al desemparejar y volver a entrar: ¿se registra sola otra vez?
- Si el registro silencioso necesita quedar en auditoría (probablemente sí).
- Cuántas máquinas por persona, y qué se hace al pasar del límite.

## Superficie de confianza

`3a` (el puente) y la API. **Abre superficie**: un endpoint que emite una
credencial de máquina a partir de una sesión web. Modelo de amenaza escrito
antes del código, y test de aislamiento por cada garantía tocada.

## Fuera de alcance

Mover la ejecución del agente a la máquina. Es la otra diferencia con Claude y
Grok, es mucho más grande, y **no hace falta** para esto.
