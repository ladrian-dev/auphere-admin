# Quickstart — validar la spec 012 a mano

Lo que los tests no pueden firmar. Cada bloque dice **qué tiene que pasar** y
—más importante— **qué tiene que fallar**: una capacidad que solo se prueba por
el camino feliz no está probada.

```bash
docker compose up -d
cd apps/api && uv run uvicorn nexus_api.main:app --reload
```

---

## 1 · Retirar el acceso de una persona (H1)

Se prueba con el código de emparejamiento **todavía puesto**. Si esto exige
haber entregado H3, el orden de entrega está mal.

**Preparación**: una persona con dos sesiones abiertas (dos navegadores) y dos
máquinas registradas.

| Paso | Qué tiene que pasar |
|---|---|
| Retirar su acceso | Las dos sesiones dejan de resolver **en la siguiente petición**, sin esperar a los siete días |
| Mirar sus máquinas | Las dos archivadas, con su motivo |
| Que una máquina lata | Recibe su negativa. No espera a que caduque la credencial de 12 h |
| Mirar la auditoría | Consta quién lo hizo, sobre quién y por qué |

**Lo que tiene que fallar:**

- **Otra persona del mismo partner** conserva sus sesiones y sus máquinas.
  Si esto no se comprueba, no se ha comprobado nada: la operación corre con rol
  dueño y la RLS **no** la está protegiendo.
- **A mitad**: forzar un fallo entre las dos mitades y comprobar que no quedan
  las sesiones cerradas con las máquinas vivas.

---

## 2 · Desemparejar (H2)

| Paso | Qué tiene que pasar |
|---|---|
| Desemparejar desde la aplicación | La máquina deja de poder trabajar **en el servidor**, no solo en esa ventana |
| Volver a abrir la aplicación | Sigue desemparejada |
| Mirar la auditoría | Consta el hecho y su motivo |

**Lo que tiene que fallar:** desemparejar **sin red**. La aplicación tiene que
decir que no se pudo y **no** dejar la máquina olvidada aquí y viva allí. Ese
estado es el defecto que esta historia cierra; volver a crearlo por un fallo de
red sería cambiarlo por uno intermitente, que es peor de encontrar.

---

## 3 · Entrar deja la máquina lista (H3)

**El recorrido que se mide.** Instalación limpia, sin credencial guardada.

| Paso | Qué tiene que pasar |
|---|---|
| Abrir la aplicación | Pide entrar |
| Entrar por el navegador y volver | **La máquina queda lista.** Sin pantalla intermedia, sin código, sin nada que caduque mientras lo haces |
| Contar los pasos | Cuatro: instalar, entrar, declarar la carpeta, escribir (CE-001) |
| Mirar la auditoría | El registro consta, aunque para la persona haya sido silencioso |

**Lo que tiene que fallar:**

- **Sesión vieja**: con una sesión abierta hace más de una hora, abrir la
  aplicación en una máquina sin registrar **pide entrar de nuevo**. Este es el
  caso por el que se eligió la Opción B y no la A: si no se comprueba, la spec
  entregó la A.
- **Sin permiso**: una persona con rol que no puede emparejar no registra, y la
  respuesta es **la misma** que la de sesión vieja.
- **Registrar dos veces** desde la misma máquina no crea dos máquinas.

---

## 4 · El tope (H4)

| Paso | Qué tiene que pasar |
|---|---|
| Registrar hasta el tope | Funciona |
| Una más | Se rechaza, y **ninguna se archiva sola** |
| Retirar una y registrar otra | Funciona |
| Archivar una y contar | Las archivadas no ocupan sitio |

**Antes de entregar esto**, mirar producción: si alguien tiene hoy más máquinas
activas que el tope, se lo rompemos al desplegar.

---

## 5 · La carpeta al frente (H5)

Instalación limpia y entrar. **Lo primero que se ofrece es declarar la carpeta
de un cliente**, no un panel de estado de la máquina. Es la decisión que la
persona tiene que tomar y recordar.

---

## 6 · El código no existe (H6)

Se comprueba **buscando**, no confiando: en la consola, en la aplicación, y en el
código fuente. No queda pantalla, campo, endpoint, tabla ni canal.

Y lo que sí tiene que seguir: **una máquina registrada antes del cambio sigue
funcionando**. Nadie vuelve a registrar lo que ya tenía.

---

## Antes de dar por cerrada cualquier pantalla

Los cuatro gates del `CLAUDE.md` del workspace —estados, accesibilidad,
responsive y tokens— y `./scripts/verify.sh` entero. Este cambio toca consola,
escritorio y API a la vez, que es justo donde este repositorio ha roto la tubería
dos veces.

Y **una sola ejecución de pytest a la vez**: las suites comparten la base de
desarrollo, y dos a la vez dan rojos que no son del cambio.
