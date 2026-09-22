# Problem Definition: la máquina se registra con la sesión, sin código

- **Slug**: maquina-sin-emparejar
- **Fecha**: 2026-09-22
- **Entrada**: [`intake.md`](./intake.md) · [`research.md`](./research.md)

---

## Problem Statement

**Se hacen dos actos para probar una sola cosa, y el segundo no prueba nada.**

El research lo cerró sin margen: para poder teclear el código, la aplicación
**ya tiene una sesión de consola confirmada** — `pair()` aborta sin `userId`
(`app-runtime.ts:291-295`) y `userId` solo llega de un `whoami` con éxito
(`:272`). El código de ocho símbolos se teclea desde una aplicación que ya
demostró quién es, en esa máquina, con esa cuenta.

No es redundancia inofensiva. Cuesta tres cosas:

1. **Un viaje a otra aplicación.** Pedir el código es en la consola del
   navegador; teclearlo es en la app. La persona tiene que cruzar, copiar, y
   volver antes de que caduquen los diez minutos.
2. **El acto deliberado está en el sitio equivocado.** Claude y Grok tienen
   exactamente uno y es sobre **archivos**: «confía este directorio». Aquí la
   ceremonia está sobre la caja y los directorios están enterrados.
3. **El patrón es un vector conocido.** «Teclea este código» es lo que
   Storm-2372 explotó contra el device code flow. Retirarlo no acepta un riesgo
   a cambio de comodidad: **retira uno**.

Debajo hay un problema que el intake no tenía y que agrava el primero: **la
fricción de pedir el código es hoy el único límite de máquinas que existe**. No
hay tope por persona ni por partner, desemparejar no llama al servidor
(`app-runtime.ts:368-376`, la credencial sigue viva hasta 12 h), y
`device.unpaired` está en el vocabulario de auditoría **sin que nadie lo
escriba**. Retirar la ceremonia sin mirar eso quita el único freno que había.

---

## Affected Users & Stakeholders

| Quién | Cómo le pega |
|---|---|
| **El partner que instala por primera vez** | Doce pasos hasta el primer trabajo útil, frente a 3-4 de Claude Desktop. El código es dos de ellos, y dos de los más frágiles: caducan |
| **El partner que cambia de máquina** | Repite la ceremonia entera por algo que la sesión ya sabe |
| **El partner que desempareja porque perdió el control de una máquina** | **Peor servido de todos.** Cree que revocó y no revocó nada: la fila sigue viva y el JWT vale hasta 12 h |
| **Auphere, al auditar** | Emparejar deja cinco asientos distintos; desemparejar no deja ninguno. La mitad de la historia |
| **Auphere, al vender** | «¿Por qué tu app me pide un código y Claude no?» es una pregunta que no tiene buena respuesta |

---

## Goals

1. **Que entrar deje la máquina lista**, sin diálogo ni pantalla intermedia.
2. **Que el acto deliberado suba de sitio**: de «qué Mac es éste» a «qué carpeta
   toca un teammate». La pieza ya existe —`POST /device/links` con sus asientos
   de auditoría— y está enterrada.
3. **Que desemparejar revoque de verdad**, no solo localmente.
4. **Que registrar y desregistrar dejen asiento**, los dos. Hoy solo uno.
5. **Que exista un límite de máquinas**, ahora que la fricción deja de serlo.
6. **Conservar lo que la spec 009 ya dijo que se conserva** al retirar el otro
   código: uso único, hash, rechazo indistinguible y límite de intentos
   (`specs/009-…/spec.md:64-65`).

---

## Non-Goals

- **Mover la ejecución del agente a la máquina.** Es la otra diferencia con
  Claude y Grok, es mucho más grande, y no hace falta para esto. Vive en
  [`teammate-que-trabaja-en-la-terminal`](../teammate-que-trabaja-en-la-terminal/).
- **Rediseñar la credencial de máquina.** El JWT de 12 h con generación y gracia
  de 60 s funciona y no se toca.
- **Tocar el inicio de sesión.** La 009 ya lo resolvió con RFC 8252 + PKCE.
- **Segundo factor para registrar.** Si se quisiera, se pide sobre la sesión, no
  sobre la máquina.

---

## Success Metrics

- **Pasos desde instalar hasta el primer trabajo útil**: de 12 a los 4 que marca
  el listón externo (instalar → entrar → carpeta → escribir).
- **Diálogos que caducan en el primer uso**: de uno a cero.
- **Asientos de auditoría por ciclo de vida de una máquina**: de «cinco al
  registrar, cero al retirar» a **los dos extremos cubiertos**.
- **Desemparejar deja la credencial viva**: de hasta 12 h a cero.

Ninguna métrica nueva de runtime. Son hechos observables.

---

## Cost of Inaction

El coste no es que el producto sea peor: es que **es peor exactamente en el
minuto en el que se decide si vale la pena**. El primer uso es donde un partner
forma su opinión, y ahí la comparación con Claude Desktop y Grok es directa y
desfavorable por un paso que no protege nada.

Y hay un coste que no es de experiencia, y que el research destapó: **la
revocación está rota y nadie lo sabe.** La copia de la aplicación dice «tus
teammates dejarán de poder leer y ejecutar aquí» y lo que ocurre es que dejan de
poder *desde esa app*; la credencial no. Mientras esto no se mire, cada
desemparejado es una promesa que el sistema no cumple — y eso no mejora con el
tiempo, porque no hay nadie observándolo.

---

## Open Questions

1. **¿Qué es «sesión recién confirmada»** para el canje, y si hace falta. Es la
   **única** diferencia real que queda entre el código y la cookie: la cookie
   puede estar ahí de antes. Su respuesta es un umbral de frescura, no una
   ceremonia.
2. ~~**¿Existe el caso de emparejar una máquina que no es la tuya?**~~ →
   **contestada por Luis el 2026-09-22: no existe.** El código se retira entero;
   ver [`decision.md`](./decision.md) D-5.
3. **¿El registro silencioso trae consigo los tres huecos** — revocación real,
   asiento en los dos extremos, límite de máquinas? Recomendación: sí, los tres,
   porque la fricción que se retira **era** el límite.
4. **¿Qué pasa al desemparejar y volver a entrar?** Con registro por sesión, por
   defecto se registra sola otra vez. Hay que decidir si desemparejar debe ser
   pegajoso.
5. ~~**¿Restablecer la contraseña invalida las credenciales de máquina?**~~ →
   **contestada por Luis el 2026-09-22: sí.** Ver [`decision.md`](./decision.md)
   D-6. Aparece una pieza común con la 011 —«retirar todo el acceso de esta
   persona»— que se construye una vez, y esta spec pasa a ir **antes** que
   aquélla.
