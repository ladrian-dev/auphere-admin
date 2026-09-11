# Problem: la aplicación solo existe en la máquina de quien la construye

- **Slug**: empaquetado-firma-y-actualizacion
- **Fecha**: 2026-09-11

## A quién le duele

- **Al partner que va a probar la beta**: no hay nada que instalar. La spec 003
  entregó la pantalla entera y el único sitio donde se abre es un repositorio
  con `pnpm` y `electron` a mano.
- **A Auphere**: la beta 1 y la beta 2 de la KB son inalcanzables. El corte por
  superficie de confianza de `[[14-mvp-y-fases]]` §1 supone gente con la app
  instalada.
- **A quien tenga que arreglar un fallo**: hoy no hay manera de hacer llegar una
  corrección. El puente es **saliente** por diseño (001): la plataforma no puede
  empujar nada a la máquina del partner. Si una versión rompe el puente, esa
  máquina se queda fuera hasta que alguien reinstale a mano.

## Qué duele exactamente

1. **No hay identidad de firma.** macOS bloquea lo que no está firmado y
   notarizado. Un DMG sin firmar no se abre; y el rodeo de «botón derecho,
   abrir» no es algo que se le pida a un cliente.
2. **`hardenedRuntime` está activado sin permisos declarados.** En cuanto se
   firme, el motor de JavaScript no podrá compilar y la app no arrancará. Está
   escrito para que no se descubra el día del empaquetado.
3. **No hay actualización.** `electron-updater` está instalado y no se usa. Una
   versión instalada se queda donde está para siempre.
4. **La actualización es una superficie de confianza** y todavía no está
   tratada como tal. Quien controle el canal de actualización puede reemplazar
   el binario que **ejecuta comandos en la máquina del partner**. Es de la misma
   clase que la ejecución local de la 001, y merece el mismo cuidado: firma
   verificada antes de aplicar, canal sobre HTTPS, y nadie pudiendo publicar a
   mano sin dejar rastro.
5. **No hay versión mínima exigible.** Cuando la haya que exigir, ya habrá
   versiones viejas fuera.
6. **La integración continua no prueba la aplicación.** `ci.yml` no ejecuta ni
   las 307 pruebas de `apps/desktop` ni las 144 de `packages/companion-ui`
   (comprobado el 2026-09-11: ninguna de las dos aparece en el fichero). Hoy
   «CI en verde» **no** quiere decir «todo verde», y el paquete compartido lo
   usan las dos superficies: alguien puede romper la aplicación desde la
   consola y no enterarse. Es lo más barato de arreglar de esta lista y lo que
   más caro sale dejarlo.
7. **«Verde en local» y «verde en la tubería» no quieren decir lo mismo.** No
   hay un comando único que corra lo que corre la integración continua. Quien
   trabaja en la API verifica la API; el worker, los canales, el MCP, la
   consola, el paquete compartido y la aplicación se quedan fuera sin que nadie
   lo note hasta que la tubería se pone roja.

   **Pasó el 2026-09-11 y costó un despliegue.** La spec 003 añadió un cron al
   worker (`teammate-task-expiry-cron`) y lo registró, pero no lo declaró en el
   contrato de nombres de `bootstrap.py`. El test que existe justo para eso
   —`tests/unit/test_bootstrap_split.py`— falló en la tubería. En local se
   habían corrido 3103 pruebas de la API y **ninguna** del worker. El
   despliegue a staging abortó en su primer paso, que es esperar a la
   integración continua; no llegó a tocar la base de datos, así que el contrato
   de despliegue funcionó. Lo que no funcionó fue la verificación previa.

   El arreglo no es «acordarse»: es un comando que corra lo mismo que la
   tubería, y que la tubería use ese mismo comando para que no puedan
   divergir.
8. **Una mina en la infraestructura.** `infra/terraform/20-services/variables.tf`
   ya nombra `NEXUS_DEVICE_TOKEN_SECRET`, pero Terraform no se aplica en el
   despliegue. El día que alguien aplique infraestructura, esa clave tiene que
   existir **antes** en el secreto o ECS aborta el arranque de la tarea. No
   rompe nada hoy; rompe el día que menos se espera.

## Objetivos

- Un artefacto instalable para macOS, firmado, notarizado y grapado, que se abra
  con doble clic en una máquina que nunca ha visto el proyecto.
- Actualización automática que **no interrumpe trabajo**: descarga en segundo
  plano, aplica al salir, y lo dice con los estados que la pantalla ya tiene.
- La cadena entera reproducible desde integración continua, sin depender del
  llavero de una persona.
- La plataforma puede exigir una versión mínima y decirlo de forma legible.

## No objetivos

- **Windows.** Otra cadena de firma y otro instalador. Se decide cuándo, no se
  hace aquí.
- **La App Store.** Su caja de arena rompe la ejecución local.
- **La edición empaquetada sobre KiroCrew** (`apps/edition`): es otro artefacto
  y otra decisión.
- **Telemetría de instalación.** Si hace falta, es una spec con su propia
  conversación sobre qué se recoge.

## Cómo se sabrá que está resuelto

1. Una persona ajena al equipo abre el DMG en un Mac limpio, arrastra, abre y
   entra sin tocar la terminal y sin ver ningún aviso de Gatekeeper.
2. Se publica una versión nueva y la app instalada la coge sola; se aplica al
   salir, nunca en medio de una tarea que espera o un comando que corre.
3. La cadena corre en integración continua desde un tag, sin nadie delante.
4. Una versión por debajo del mínimo exigido recibe una respuesta legible de la
   plataforma, no un error de red.
5. Un artefacto manipulado **no** se instala: el actualizador lo rechaza por la
   firma.
