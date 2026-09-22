# Contrato — registrar la máquina con la sesión

Sustituye a `POST /device/pair`. La diferencia con lo que había no es el
resultado —la misma credencial, para la misma máquina, de la misma persona—
sino **quién demuestra tener derecho a pedirla**: antes un código tecleado,
ahora la sesión que ya estaba ahí.

---

## El camino, entero

```
  aplicación (proceso principal de Electron)
      │  fetch desde la partición humana, con su cookie de sesión
      ▼
  BFF de la consola · POST /api/desktop/register-machine
      │  comprueba la sesión, comprueba el permiso, firma un token de servicio
      ▼
  API · POST /console/workstation/machines
      │  vuelve a comprobar, emite la credencial UNA vez, deja asiento
      ▼
  la aplicación la guarda cifrada en el llavero del sistema
```

**Por qué pasa por el BFF y no directo a la API.** No es estilo. Está escrito en
el código del precedente (`apps/console/src/app/api/desktop/redeem/route.ts:9-12`):
la ruta de la API exige la credencial de servicio del BFF y **la cáscara no
tiene ninguna ni puede tenerla**. Hay un test que existe porque esto ya se
desplegó mal una vez y devolvió `401 Missing bearer token`.

**Por qué no se reutiliza `/api/desktop/redeem`.** Ata otra cosa: aquélla ata una
**persona** a la aplicación (deja una cookie), ésta ata una **máquina** a la
cuenta (devuelve una credencial). ADR-039 avisó exactamente de esta confusión —
«se parecen y atan cosas distintas»— y esta spec existe en parte por no haberlo
mirado antes.

---

## La ruta del BFF

**`POST /api/desktop/register-machine`**

**Entrada**: lo que la aplicación sabe de sí misma y la persona no elige — cómo
se llama la máquina y en qué plataforma corre. **Ningún identificador de persona
ni de partner**: eso sale de la cookie, y es la razón de ser de todo esto.

**Cookie**: la de la partición humana. Es lo único que autoriza.

**Salida, 201**: la credencial y lo que la aplicación necesita para enseñar quién
es — identificador de máquina, generación, cuándo caduca, y los datos de
presentación del partner y la persona. Misma forma que devuelve hoy el canje del
código: esa parte no cambia y no hay motivo para que cambie.

**Esta es la única ruta del BFF que devuelve un secreto.** De ahí sale el
Requisito 7: se entrega una vez, no se puede releer, y no se registra en ningún
sitio.

### Todos los rechazos dicen lo mismo

**401**, cuerpo único, sin distinguir:

- no hay sesión;
- la sesión es vieja (más de una hora desde que se abrió — R3.2);
- la persona no tiene permiso para emparejar puesto de trabajo;
- ya está en el tope de máquinas.

Que el tope esté en esta lista es deliberado y va contra la intuición: sería más
amable decir «tienes cinco máquinas». Pero el mismo cuerpo tiene que valer para
«no tienes permiso», y decir cuántas máquinas tiene alguien a quien no conoces es
contar de más. **La aplicación sí puede explicar el tope**, porque habla con una
persona que ya está dentro: lo pregunta por la vía normal, no lo deduce de un
rechazo.

**429** con `Retry-After` cuando se pasa del techo de intentos (R3.5). La clave
del limitador pasa a ser **la persona**, no `hostname+IP` como en el canje viejo:
ahora hay sesión, así que se puede.

---

## La ruta de la API

**`POST /console/workstation/machines`**

Exige la credencial de servicio del BFF, como todas las de `/console/*`, y
**vuelve a comprobar el permiso por su cuenta**. Dos comprobaciones, no una: el
BFF comprueba para decir que no pronto; la API comprueba porque es la que emite
el secreto y no puede fiarse de que su llamante haya mirado. Es la misma regla
que el repositorio ya aplica a la consola de partners.

**Deja asiento** (`device.paired`) en el éxito y (`device.pair_denied`) en el
rechazo, con su motivo real — el motivo va a la auditoría aunque no vaya a la
respuesta. Es la distinción que hace que un rechazo uniforme siga siendo
investigable.

**Registrar la misma máquina dos veces** devuelve la que ya existe en vez de
crear una segunda (R3.7).

---

## Lo que desaparece

| Qué | Dónde |
|---|---|
| `POST /device/pair` | el puente |
| `POST /console/workstation/pairing-codes` | la consola |
| La tabla de códigos y su repositorio | la API |
| El generador, el alfabeto y el hash del código | la API |
| El diálogo de la consola | la consola |
| El diálogo de la aplicación y su alfabeto duplicado | el escritorio |
| El canal de IPC para emparejar | el escritorio |

**Lo que NO desaparece**: las máquinas ya registradas siguen valiendo (R6.2).
Nadie vuelve a registrar lo que ya tenía.

---

## Retirar el acceso de una persona

**`DELETE /console/team/members/{membership_id}/access`** · permiso
**`team:manage`**

> **Corrección del 2026-09-22, al implementar.** Este contrato la puso primero
> bajo `/console/workstation/*`, que es donde están sus parientes. Estaba mal, y
> por el permiso: ahí el permiso es `workstation:pair`, que **tiene el builder**
> porque —dice su propia declaración— es «reclamar lo que es **tuyo**». Esto es
> lo contrario, retirarle el acceso a **otra persona**, y colgarlo del permiso
> vecino por proximidad de fichero habría dejado a un builder echando a un
> owner. `team:manage` es owner y admin: quien administra a los demás. Tiene su
> test.

Una operación, dos efectos, una transacción: sus sesiones dejan de resolver y sus
máquinas dejan de poder trabajar. **O las dos cosas, o ninguna** (R1.2).

**Sobre la propia**: se deja hacer, a diferencia de cambiar de rol o quitarse del
equipo, que llevan guarda. Quien sospecha que le han entrado necesita poder
cerrarlo todo sin pedir permiso, y el coste de equivocarse es volver a entrar.

**No retira la pertenencia** — eso ya existe y es `DELETE /members/{id}`. Esto
solo corta lo que está abierto ahora.

Es la pieza que la spec 011 llamará cuando restablecer la contraseña revoque
máquinas (D-6), y por eso vive en un módulo propio en vez de dentro de la
identidad o del puesto de trabajo: **las cruza**.

**Aviso de diseño que su test tiene que cubrir:** corre con rol dueño, porque es
mantenimiento de plataforma —igual que ya lo es archivar las máquinas de quien
pierde la pertenencia—. Eso significa que **la RLS no la protege**. Lo único que
impide que alcance a otra persona es su propia condición, y por eso necesita un
test de aislamiento que lo afirme (R1.5).

**Deja asiento** con quién, sobre quién y por qué.

---

## Desemparejar, desde la aplicación

Lo que hoy es un olvido local pasa a ser una revocación. La máquina se archiva
con motivo `"desemparejada"` —un valor que **ya está declarado en la base y que
nadie escribía**— y deja asiento `device.unpaired`, que estaba en el mismo caso.

**Si la revocación no se puede completar, no se olvida en local** (R2.3). El
estado «olvidada aquí, viva allí» es exactamente el defecto que esta historia
cierra; repetirlo por un fallo de red sería cambiar un defecto permanente por uno
intermitente, que es peor de encontrar.

La pantalla dice lo que pasa y **lo que no**: lo que la máquina ya está
ejecutando en este momento no se puede parar desde aquí. Lo que se corta es que
pueda volver a pedir trabajo o devolver resultado.
