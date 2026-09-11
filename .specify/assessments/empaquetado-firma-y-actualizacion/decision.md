# Decision Gate: empaquetar, firmar y actualizar la aplicación de escritorio

- **Slug**: empaquetado-firma-y-actualizacion
- **Decided**: 2026-09-11
- **Verdict**: **go**, y se construye en una sesión dedicada con su spec
- **Artifacts reviewed**: [`intake.md`](./intake.md) · [`research.md`](./research.md)
  · [`problem.md`](./problem.md) · [`concept.md`](./concept.md)
- **Superficie de confianza (§II)**: se abre **una nueva**, y hay que decirlo con
  todas las letras. El canal de actualización puede reemplazar el binario que
  ejecuta comandos en la máquina del partner. Es de la misma clase que la
  superficie `3a` de la 001, y la spec tiene que tratarla igual: firma
  verificada antes de aplicar, canal de solo lectura para todo el mundo menos la
  cadena, y publicar solo desde integración continua.

## Scorecard

| Criterio | Nota | Evidencia |
|---|---|---|
| Demanda | 5/5 | Sin esto no hay beta: la app solo se abre desde el repositorio |
| Encaje con lo construido | 4/5 | `electron-builder` ya está; la app ya se identifica con su versión en dos sitios; el despliegue a AWS ya guarda secretos de producción |
| Riesgo | 3/5 | Superficie de confianza nueva (el canal) y un secreto de producción nuevo (el certificado) |
| Coste | 3/5 | `medium`: una spec, sin frontend nuevo. Lo caro es la cadena y sus secretos, no el código |
| Reversibilidad | 4/5 | Una versión mala se contiene con despliegue por porcentaje; el certificado se revoca y se reemite |
| Dependencias externas | 4/5 | La cuenta ya existe. Falta **comprobar si hay certificado Developer ID**, que es otro tipo que el de las apps móviles |
| Licencias | 5/5 | Nada nuevo: `electron-builder` y `electron-updater` ya están instalados (MIT) |

## Verdict & Rationale

**Go.** Es lo único que separa la 003 de estar en manos de alguien. No hay nada
que investigar antes: lo que falta es decidir tres cosas (canal, momento de
aplicar, quién firma) y construir la cadena.

Lo que **no** se hace en esta evaluación es empezar. Se documenta y se abre en
una sesión dedicada, con `/speckit-specify` sobre estos cuatro documentos, por
la misma razón de siempre: toca secretos y una superficie de confianza, y eso no
se improvisa al final de otra tarea.

## El orden de la próxima sesión

1. **Poner las dos suites que faltan en integración continua** (`apps/desktop`,
   `packages/companion-ui`). Va antes que todo lo demás y casi no cuesta: la
   cadena de firma se cuelga del mismo fichero, y firmar una aplicación cuyas
   pruebas nadie corre al fusionar es firmar a ciegas.
2. **Mirar qué hay ya en el equipo de Apple de Auphere**: tener el Developer
   Program no implica tener un certificado *Developer ID Application*, porque
   las apps móviles usan otro tipo. Si no existe, lo crea el titular de la
   cuenta o un administrador en minutos, pero es la única pieza que no depende
   de nosotros.
3. `/speckit-specify` sobre estos cuatro documentos.

## Preguntas para `/speckit-clarify`

1. **Canal**: ¿almacenamiento en AWS con CDN, como recomienda el concepto, o
   hay alguna razón para otra cosa?
2. **Windows**: ¿entra en esta spec o se dice explícitamente en qué fase entra?
3. **Versión mínima**: ¿la plataforma rechaza versiones viejas desde el primer
   día, o solo se prepara la cañería y se activa cuando haga falta?
4. **Quién publica**: ¿solo integración continua desde un tag, o también a mano
   en una emergencia? (Si lo segundo, hay que decir cómo queda registrado.)
5. **Canales de versión**: ¿hace falta un canal de pruebas separado para la
   beta, o todo el mundo va por el mismo?

## Lo que la spec tendrá que probar, no solo hacer

- Un artefacto firmado **se abre** en un Mac limpio: prueba de humo en la cadena
  antes de publicar, porque `hardenedRuntime` sin permisos declarados no falla
  al construir, falla al abrir.
- Un artefacto manipulado **no** se instala.
- Una actualización **no** se aplica con una tarea esperando ni con un comando
  corriendo.
- Una versión por debajo del mínimo recibe una respuesta legible, no un error de
  red.

## Una mina que hay que desactivar, aunque no sea de esta spec

`infra/terraform/20-services/variables.tf` ya nombra
`NEXUS_DEVICE_TOKEN_SECRET`. Terraform no se aplica en el despliegue
automático, así que hoy no molesta; el día que alguien aplique infraestructura,
esa clave tiene que existir **antes** en el secreto o ECS aborta el arranque de
la tarea. Comprobarlo cuesta un minuto y descubrirlo en mitad de un despliegue
cuesta una tarde.

## Estado del repositorio al abrir esto

`develop` contiene ya las specs 002 y 003 (avance rápido el 2026-09-11; la rama
001 quedó absorbida con otros identificadores tras un rebase anterior). La
aplicación está completa y verificada; lo que falta es exactamente esto.
