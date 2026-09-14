# Fase 0 — investigación: empaquetado, firma y canal

**Spec**: [spec.md](./spec.md) · **Fecha**: 2026-09-14

Siete decisiones. La **D2 es un bloqueante externo** que no depende de escribir
código, y conviene verla antes que ninguna otra.

---

## D1 · El canal: S3 privado detrás de CloudFront, y Cloudflare para el nombre

**Decisión**: bucket privado + distribución de CloudFront con *Origin Access
Control* + certificado en ACM (`us-east-1`, que es donde CloudFront los exige) +
`updates.auphere.com` como CNAME desde Cloudflare, que es quien ya lleva el DNS
del dominio.

**Razón**: R2.1 pide HTTPS y solo lectura; R2.2, que nadie salvo la cadena
escriba; R2.3, que el cliente no lleve ningún secreto dentro. Con OAC el bucket
**no es público** y aun así el contenido se sirve sin credenciales: la
distribución es el único que puede leerlo, y la cadena el único que puede
escribir. Es el patrón estándar y no inventa nada.

**Alternativas consideradas**:

- **Releases de GitHub.** Ya descartada en el assessment y por la razón correcta:
  en un repositorio privado obliga a incrustar un token **dentro del binario de
  cada partner**. Un secreto en la máquina de un cliente, para leer un canal
  público. No es el precio, es el token.
- **Bucket público directo, con Cloudflare delante.** Más simple —y Cloudflare ya
  está ahí, así que es tentador—. Rechazada: un bucket público es una política
  que alguien puede aflojar sin querer, y la diferencia entre «público» y
  «servido por una distribución» es justo la que R2.2 pide poder comprobar.
- **Servir desde la API.** Mezcla el plano de datos con la distribución de
  binarios y el ALB no es un CDN. Ya descartada en el assessment.

**Lo que hay que mirar al aplicar**: el certificado de CloudFront va en
`us-east-1` aunque todo lo demás viva en `eu-south-2`. Es la trampa clásica y
cuesta un `terraform apply` fallido descubrirla.

---

## D2 · La identidad de firma todavía no puede salir de una máquina

> **Bloqueante externo. No lo resuelve escribir código.**

**El hecho**: el certificado `Developer ID Application: FACELAD SpA
(CBSWMG766P)` existe y está probado, pero **su clave privada vive sólo en el
llavero `login` de la máquina de Luis y no hay copia**. Exportar un `.p12` sigue
pendiente.

**Consecuencia**: la cadena no puede firmar hasta que exista ese `.p12`, porque
R5.1 exige firmar **sin depender del llavero de ninguna persona**. Y hay un
segundo riesgo del mismo hecho: si esa máquina se pierde hoy, hay que emitir
otro certificado — y **emitir un Developer ID sólo lo puede hacer el Account
Holder**, que es Daniel Marquez, de Facelad, no alguien de Auphere.

**Decisión**: la primera tarea de la implementación es exportar el `.p12` y
guardarlo como secreto, **y hasta que exista no se construye la cadena**. Se
declara como dependencia externa en el plan para que no se descubra a mitad.

**Y lo que esta spec no puede arreglar, pero sí escribir**: quien puede revocar
la identidad es Facelad. Apple es explícito en que una app firmada con un
certificado **revocado** no arranca ni aunque ya esté instalada —caducar no
rompe nada, revocar sí—. Eso va en la documentación de R5.5, no en un comentario.

---

## D3 · Firmar y notarizar en un runner de macOS, con llavero temporal

**Decisión**: un trabajo nuevo sobre `macos-latest`, que importa el `.p12` a un
**llavero temporal creado para esa ejecución** y lo destruye al terminar.
Notarización con `notarytool` y la clave de App Store Connect que ya existe.

**Razón**: R5.1 y R5.2. Un llavero temporal por ejecución es lo que hace que «no
depende del llavero de nadie» y «no queda accesible después» sean lo mismo.

**Lo que cambia respecto del repo de hoy**: **todos los trabajos actuales corren
en `ubuntu-latest`**. Éste es el primer runner de macOS, y cuesta más por minuto.
Se acota corriendo sólo cuando se publica, no en cada `push`.

**Alternativa considerada**: firmar desde el portátil y publicar desde ahí.
Rechazada por el assessment y por R5.1 — hace que la cadena dependa de una
máquina y de un llavero, que es el problema que D2 ya demuestra que es real.

---

## D4 · Credenciales de AWS por OIDC, como el resto del repo

**Decisión**: el trabajo de publicación asume un rol por OIDC
(`id-token: write` + `role-to-assume`), con un rol **distinto** del de despliegue
y permisos acotados a escribir en el prefijo del canal.

**Razón**: es lo que `deploy-prod.yml` ya hace, y no hay motivo para introducir
claves estáticas justo en el trabajo que toca la superficie más delicada. Un rol
separado es lo que hace comprobable R2.2: el rol de despliegue no puede publicar
versiones, y el de publicación no puede tocar ECS.

---

## D5 · El formato del canal lo fija el actualizador, y ya está elegido

**Decisión**: canal «genérico» de `electron-updater` — un índice por plataforma
más los paquetes—, publicado bajo `/desktop`. No se inventa formato.

**Razón**: el commit `e100564` ya declara `publish: generic` contra
`https://updates.auphere.com/desktop`, y el cliente que lo lee ya está escrito y
probado. Cambiar el formato aquí sería rehacer trabajo bueno para no ganar nada.

**Consecuencia para R2.5** (la versión anterior sigue disponible): el índice
apunta a la última, pero **los paquetes anteriores no se borran**. Publicar es
añadir y mover un puntero, nunca sustituir.

---

## D6 · La puerta de versión mínima vive en el latido

**Decisión**: el mínimo se comprueba en `POST /device/heartbeat`, y responde con
el mismo idioma que las negativas que ese canal ya tiene (`403 device_archived`,
`403 pairing_required`).

**Razón**: es el único punto que **corre solo y cada poco**. Un gate en el
emparejamiento sólo alcanzaría a máquinas nuevas; uno en cada petición no
añadiría nada, porque el latido es el que va a llegar primero. Y la barra ya
sabe reaccionar a una negativa del latido cambiando de estado: el camino de
pintarlo existe.

Un detalle que conviene no perder: el latido **ya recibe** `app_version` y **la
ignora a propósito** — la versión se fija al emparejar y al renovar (`T072`).
Esta spec la lee para decidir, y **sigue sin persistirla**: el gate necesita
saber qué versión llama, no dejar constancia de cada latido.

**Alternativas**: un gate en `require_device` (alcanzaría a todas las rutas, pero
la mayoría no llevan versión y habría que añadirla a todas) · un gate en el
puente de eventos (no corre cuando la app está parada, que es justo cuando hay
que avisar).

---

## D7 · El estado de la barra es uno, y distingue dos cosas

**Decisión**: un estado nuevo, con dos formas: **«lista, se instala al cerrar»**
y **«esperando a que termine lo que hay vivo»**.

**Razón**: son dos situaciones que la persona vive distinto. La primera no pide
nada; la segunda explica por qué la aplicación *no* se está actualizando, que es
la pregunta que alguien se hace cuando le dijeron que había una versión nueva y
sigue viendo la vieja. Fundirlas en un estado ahorra una línea de código y
cuesta una llamada a soporte.

**Corregido el 2026-09-14, al implementarlo**: esta sección decía que faltaba
pasarle el número de aprobaciones pendientes. **No falta.** `e100564` ya cablea
las dos cifras en `main.ts`, y con un matiz que conviene no perder:

    readActivity: () => ({
      liveSessions: streams.liveCount,
      pendingApprovals: waitingNow.filter((w) => w.level !== "informativo").length,
    })

Las de nivel `informativo` **no cuentan**, porque no esperan a nadie — igual que
no marcan la bandeja. Es la segunda vez en esta spec que doy por pendiente algo
que el commit rescatado ya traía; lo que de verdad falta es sólo el estado de la
barra.

---

## Licencias (§VIII)

**Ninguna dependencia nueva.** `electron-builder` y `electron-updater` ya están
instalados (MIT). `notarytool` y `codesign` vienen con Xcode. Las acciones de
integración continua que se usan (`aws-actions/configure-aws-credentials`) ya se
usan en el repo. No hay nada que leer ni que citar.

## Lo que esta fase deja sin decidir a propósito

- **Cuándo se migra la identidad al equipo de Auphere.** Va aparte; esta spec
  deja escrito el coste (todos reinstalan y vuelven a emparejar).
- **Cuándo se pone el icono definitivo.** Que el icono queda **fuera** ya no es
  una decisión pendiente: está escrito en «Fuera de alcance» de la spec, con la
  razón. Lo que queda sin decidir es cuándo se hace, y eso es trabajo de diseño.
