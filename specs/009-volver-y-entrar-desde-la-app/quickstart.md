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

| # | Qué se hace | Qué tiene que pasar |
|---|---|---|
| 1 | Abrir la app sin sesión | Se enseña la consola en `/login` |
| 2 | Pulsar «continuar con Google» | Se abre el **navegador del sistema**. Esto no cambia y no debe cambiar |
| 3 | Completar el inicio de sesión allí | El navegador llega a una pantalla con un código de ocho caracteres y qué hacer con él (R3.1) |
| 4 | Teclearlo en la barra | La app queda dentro y sale la pantalla del equipo sin tocar nada más (H2.2) |
| 5 | Teclear el **mismo** código otra vez | Rechazado, sin decir de quién era (R4.4) |
| 6 | Pedir uno nuevo y teclear el **anterior** | Rechazado: sólo hay uno vivo por persona (R3.4) |
| 7 | Pedir uno y esperar once minutos | Rechazado por caducado, y la barra ofrece pedir otro (H2.4) |
| 8 | Pedir uno y teclearlo en **otra máquina** | Rechazado, y **con el mismo mensaje** que el caducado y que uno inventado (R5.3 + R4.5) |
| 9 | Fallar cinco veces seguidas | Espera creciente, igual que el emparejamiento (R4.6) |

### Las tres comprobaciones que nadie hace y son el punto entero

**Que las sesiones son independientes** (R4.2). Con sesión en las dos, cerrar la
del navegador:

```bash
open "https://console.auphere.com/logout"
```

La aplicación **sigue dentro**. Si se cae, se copió el secreto en vez de acuñar
uno nuevo, y Q1 está incumplido.

**Que se puede cerrar la de la app sin cerrar la del navegador** (R4.3), que es lo
que hace que «independientes» no sea sólo una palabra. Desde la consola, en la
lista de sesiones: termina la que lleva `AuphereDesktop/` y la del navegador
sigue viva.

**Que el código no aparece en claro en ningún sitio** (R5.4):

```bash
docker compose logs api --since 10m | grep -oE "\b[ABCDEFGHJKMNPQRSTVWXYZ23456789]{8}\b" | head
```

Ahí no puede salir ningún código. El alfabeto del `grep` es el de
`core/pairing_codes.py` a propósito: busca exactamente la forma que tienen. **Si
aparece algo, es 🔴 y bloquea antes de seguir.**

### Lo que la auditoría tiene que poder decir (R5.5)

La sesión acuñada por el canje se distingue por su `user_agent`, que la cáscara
pone desde la spec 002:

```bash
docker compose exec -T postgres psql -U nexus -d nexus -c "SELECT principal_id, user_agent, created_at FROM console_auth.principal_sessions ORDER BY created_at DESC LIMIT 5;"
```

Una de las filas recientes tiene que llevar `AuphereDesktop/`. Si las dos sesiones
son indistinguibles, la auditoría no puede decir qué máquina hizo qué.

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
