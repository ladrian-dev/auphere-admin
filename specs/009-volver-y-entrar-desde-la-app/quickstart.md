# Fase 1 — cómo se valida a mano

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Lo que los tests **no** pueden probar: que la ventana cambia de verdad, que la
consola no se recarga al volver, y que una persona completa el recorrido de
principio a fin. Se deja la salida cruda en `.evidence/009/`.

## Antes de empezar

```bash
docker compose up -d
```

```bash
curl -s http://localhost:8000/health
```

```bash
cd apps/api && uv run alembic upgrade head
```

Tiene que llegar a `0122_session_codes`.

## Historia 1 — volver a la pantalla del equipo

Se valida **antes** de que exista nada de la Historia 2, y ése es el punto de que
sea P1.

```bash
pnpm --filter @nexus/desktop build && pnpm --filter @nexus/desktop start
```

| # | Qué se hace | Qué tiene que pasar |
|---|---|---|
| 1 | Mirar la barra en la pantalla del equipo | **No** hay acción de volver: ni apagada ni explicada (R1.2) |
| 2 | Pulsar «ir a la consola» | La consola ocupa la ventana **y aparece** la acción (R1.1) |
| 3 | Navegar dentro de la consola a un cliente | La acción sigue ahí |
| 4 | Pulsarla | Sale la pantalla del equipo (R1.3) |
| 5 | Volver a la consola | **Sigue donde estaba.** Si se recargó o volvió a la portada, R1.3 está roto |
| 6 | `Cmd+1`, icono de bandeja y `Cmd+Shift+A` | Los tres siguen funcionando (R1.4) |

**El caso que se olvida** (R2.4): con el cifrado no disponible —cancelar el
diálogo del llavero en un usuario recién creado— la barra se queda sin sus otras
acciones **y la de volver sigue ahí**. Si desaparece, alguien la metió dentro de
`actionsFor(state)`, donde la filtra el `if (!state.encryptionAvailable) return []`.

## Historia 2 — entrar con Google

Hace falta una cuenta de Google que sea principal de un partner, y **no** tener
sesión en la partición de la aplicación.

**No hay ningún código que teclear.** Es RFC 8252: la aplicación abre el
navegador, la persona entra, y el navegador vuelve solo a `127.0.0.1`.

| # | Qué se hace | Qué tiene que pasar |
|---|---|---|
| 1 | Abrir la app sin sesión | Se enseña la consola en `/login` |
| 2 | Pulsar «continuar con Google» | Se abre el **navegador del sistema** |
| 3 | Completar el inicio de sesión allí | El navegador vuelve solo y dice que ya puedes volver a Auphere |
| 4 | Mirar la aplicación | **Está dentro**, sin haber tecleado nada (H2.2) |
| 5 | Cerrar la pestaña a medias, antes de entrar | La app no se queda colgada: el oyente caduca y la barra lo cuenta como estado, nunca en rojo |

### Las cuatro comprobaciones que nadie hace y son el punto entero

**Que el oyente NO sobrevive al flujo** (spec 001, criterio 6.5.3). Con la app
abierta y **sin** inicio de sesión en curso:

```bash
lsof -nP -iTCP -sTCP:LISTEN | grep -i auphere
```

Tiene que salir **vacío**. Si sale algo, hay un servidor viviendo en la máquina
del partner y la enmienda del Requisito 6 introdujo justo lo que prometía evitar.

**Que mientras dura, escucha sólo en loopback** (6.5.1). Con el navegador
abierto a medio login, el mismo comando tiene que mostrar `127.0.0.1:` y
**nunca** `*:` ni `0.0.0.0:`.

**Que el redirector no se puede desviar** (el ataque que `desktop-redirect.ts`
cierra). A mano, en el navegador:

```
https://console.auphere.com/desktop-auth?redirect_uri=https://example.com/&state=x&code_challenge=y
```

Tiene que llevar a `/no-access` y **no emitir ningún código**.

**Que las sesiones son independientes** (R4.2). Cerrar la del navegador y ver
que la aplicación **sigue dentro**.

## Antes de declararlo hecho

```bash
./scripts/verify.sh
```

Y **`/cso`**, que aquí no es opcional: esto toca autenticación y secretos de un
solo uso. Un finding 🔴 bloquea el ship.

## Lo que este quickstart NO cubre, y conviene que esté dicho

- **El recorrido en un Mac limpio** — T021 de la spec 008, todavía sin ejecutar
  formalmente.
- **El ciclo de actualización completo** — T031 de la spec 008, también pendiente.
- **Windows** — esa mitad no está portada.
