# Modelo de amenaza — superficie `3a`, spec 012

> **Este documento llega tarde, y conviene que se vea.** T005 decía «antes de
> tocar código», y se escribió **después** de entregar US3. No hubo un descuido
> de alcance —el trabajo que describe se hizo y se probó— pero el orden del
> método existe por algo: un modelo de amenaza escrito después corre el riesgo
> de ser una justificación de lo construido en vez de una comprobación de si
> debía construirse.
>
> Por eso está redactado al revés de como se suele: **busca dónde el cambio
> empeora las cosas**, no dónde las mejora. Si algo de aquí hubiera salido mal,
> lo entregado tendría que cambiar.

## Qué cambia, exactamente

| | Antes | Ahora |
|---|---|---|
| Qué autoriza emitir una credencial de máquina | Un código de 8 símbolos, tecleado | La cookie de sesión de la partición humana |
| Quién podía teclear ese código | Una aplicación que **ya tenía esa cookie** | — |
| Dónde se comprueba el permiso | Al **emitir** el código (consola) | Al **registrar** (BFF y API, dos veces) |
| Frescura exigida | Ninguna, salvo los 10 min del código | La sesión se abrió hace < 1 h |

**La autoridad no cambia de manos.** Era la sesión antes —porque `pair()`
abortaba sin `userId`, y `userId` solo llegaba de un `whoami` con éxito— y es la
sesión ahora. Eso es lo que sostiene la afirmación de «sustitución, no apertura»
del encabezado de la spec.

## Quién podría atacar esto, y qué consigue

### A-1 · Alguien con la cookie de la partición humana

**Antes**: abría la aplicación, pedía un código en la consola (misma cookie) y lo
tecleaba. Obtenía una credencial de máquina.

**Ahora**: abre la aplicación y obtiene una credencial de máquina.

**Veredicto: igual de malo, un paso más corto.** Quien tiene la cookie ya lo
tenía todo. El código nunca fue una barrera para este atacante — era el mismo
factor pedido dos veces.

**Lo que sí cambia, y a mejor**: el umbral de frescura. Una cookie robada de hace
seis días **ya no sirve** para registrar una máquina; antes sí. Es la única
diferencia real que la evaluación encontró entre el código y la sesión, y se
contestó con frescura en vez de con ceremonia.

### A-2 · Alguien que engaña a la persona para que teclee algo

**Antes**: este es el ataque que el patrón «teclea este código» habilita, y tiene
nombre — Storm-2372 lo usó contra el device code flow. Se convence a alguien de
que teclee un código que el atacante generó.

**Ahora**: no hay nada que teclear. **El vector desaparece.**

**Veredicto: el cambio cierra una superficie.** Es el único punto donde retirar
algo mejora la postura en lugar de dejarla igual.

### A-3 · Un builder que quiere más de lo suyo

`workstation:pair` lo tienen owner, admin y builder, porque —dice su propia
declaración— es «reclamar lo que es **tuyo**». Registrar una máquina propia entra
ahí.

**Lo que este cambio NO le da**: retirar el acceso de otra persona vive bajo
`team:manage` (owner y admin). Se colocó ahí **a propósito**, y el borrador lo
tenía mal: con `workstation:pair`, un builder habría podido echar a un owner. Hay
test.

### A-4 · Una máquina comprometida que quiere más credenciales

La credencial de máquina no sirve para registrar otra: el registro exige la
cookie de sesión, que vive en la partición humana y **no es alcanzable desde el
puente**. Las cinco operaciones del puente siguen siendo cinco.

**Veredicto: sin cambio.** El puente sigue siendo saliente y no gana ninguna
operación. A diferencia de la spec 009, aquí **no se abre ningún puerto** y no se
enmienda `no-inbound.test.ts`.

### A-5 · Alguien que acumula máquinas para agotar algo

**Antes**: el límite práctico era la fricción de pedir un código. No había tope.

**Ahora**: hay tope de cinco activas por persona, y las archivadas no cuentan.

**Veredicto: el cambio repone un freno que iba a desaparecer.** Sin el tope, esto
sería la única regresión real de la spec: registrar habría pasado de costar un
trámite a ser gratis, sin nada que lo acotara.

### A-6 · Dos personas en el mismo ordenador

Cada una recibe **la suya**, con su `principal_id`. Ninguna ve la credencial de
la otra — hay test, y es el que cambió de sentido al implementar US6: antes la
segunda persona se quedaba sin poder trabajar; ahora trabaja con lo suyo.

**Veredicto: mejora.** El caso antes no tenía solución sin pedir otro código.

## Lo que se conserva del código retirado

La spec 009 dejó la lista escrita al retirar el **otro** código, y aplica igual:

| Propiedad | Cómo sobrevive |
|---|---|
| Uso único | La credencial se entrega una vez y no se puede releer |
| Rechazo sin oráculo | «No hay sesión» y «la sesión caducó» son indistinguibles |
| Techo de intentos | Sigue, con la persona como clave en vez de `hostname+IP` |
| Hash en reposo | **Deja de aplicar, y es una mejora**: no hay secreto que guardar. Desaparece con la tabla |

## Lo que este modelo NO cubre

- **Robo de la cookie de sesión.** Es el activo que autoriza, y su protección es
  de la spec 009 (cookie `httpOnly`, `sameSite=lax`, `secure` en producción,
  caducidad absoluta de siete días sin renovación). Esta spec no la cambia.
- **Una máquina física comprometida.** Si alguien controla el ordenador, controla
  el llavero del sistema donde vive la credencial. Fuera de alcance, y lo estaba
  antes.
- **El `install_id`.** No es un secreto y no autoriza nada: solo dice qué
  instalación es, para no crear máquinas fantasma. Conocerlo no da acceso.

## Una mejora que este modelo no vio venir

Escrito lo de arriba, al correr la tubería entera apareció algo que ninguna de
las seis entradas nombra: **el puente se queda sin una sola ruta anónima.**

`/device/pair` era la única de `/device/*` montada **sin credencial**, y su
excepción estaba justificada —el código *era* la credencial de un solo uso—.
Retirarlo mueve el alta a la consola, donde la autoriza una sesión que ya
existía, así que la excepción se queda sin caso. De una puerta sin llave a
ninguna.

Lo delató el test que la afirmaba, `test_device_bridge_inbound.py`, al ponerse
rojo. No se retiró: se le dio la vuelta. La lista de excepciones sigue ahí,
vacía, y ahora el test afirma que está vacía — su trabajo nunca fue guardar un
nombre, sino obligar a que una excepción futura se escriba y se razone.

## Conclusión

**Nada de lo revisado obliga a cambiar lo entregado.** El cambio cierra un vector
(A-2), mejora dos casos (A-1 con la frescura, A-6), repone un freno que habría
desaparecido (A-5), retira la última ruta anónima del puente y deja el resto
igual. El punto que sí obligó a corregir algo —el permiso de A-3— se corrigió
durante la implementación y tiene test.
