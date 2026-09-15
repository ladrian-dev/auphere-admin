# Fase 1 — modelo de datos

**Spec**: [spec.md](spec.md) · **Investigación**: [research.md](research.md)

Una tabla nueva. Nada más cambia de forma.

## `console_auth.session_codes` (migración 0122)

El secreto de un solo uso que trae una sesión de Google a la aplicación.

| Columna | Tipo | Notas |
|---|---|---|
| `code_hash` | `varchar(64)` **PK** | SHA-256 del código. **La PK es el hash**, igual que en `principal_sessions`: un volcado de la tabla no deja entrar en ninguna cuenta |
| `principal_id` | `uuid` NOT NULL | FK → `console_auth.principals.id`, `ON DELETE CASCADE`. Quién lo pidió |
| `created_at` | `timestamptz` NOT NULL | `now()` |
| `expires_at` | `timestamptz` NOT NULL | `created_at + CODE_TTL` (10 min) |
| `consumed_at` | `timestamptz` NULL | **NULL = sin usar.** Se rellena al canjear, y no se borra la fila |

**Índices**: `principal_id` (para invalidar el anterior al emitir uno nuevo) y
`expires_at` (para la limpieza).

### Cuatro decisiones dentro de esa tabla

**`consumed_at` en vez de borrar la fila.** Borrar haría indistinguible «ya usado»
de «no existió», y **esa indistinguibilidad tiene que ser una decisión de la
respuesta, no un efecto de la tabla** (R4.5). Con la fila delante, el servidor
elige qué contesta; sin ella, no puede elegir. Además es lo que permite auditar
que un código se usó (R5.5).

**Sin columna de máquina, desde la enmienda del 2026-09-15.** La tabla llegó a
tener un `machine_hint` hasheado para atar el código. Se retiró al descubrir que
no hay a qué atarlo: quien pide el código es el navegador del sistema. Dejarla
como columna muerta habría sido peor que quitarla — un dato que nadie lee parece
una protección que nadie tiene. Lo que se registra del canje es lo que
`principal_sessions` ya guarda de cualquier sesión: `ip` y `user_agent`.

**Un solo código vivo por persona.** R3.4: emitir uno nuevo invalida el anterior.
Se implementa marcando `consumed_at` en los vivos de esa `principal_id` antes de
insertar, no con un `UNIQUE` parcial — un índice único devolvería un error de base
de datos donde lo correcto es una sustitución silenciosa.

**Sin `tenant_id` y sin RLS propia.** Vive en `console_auth`, que es el esquema de
identidad de la consola: `principals` tampoco lleva tenant. El alcance de una
persona sale de `partner_memberships`, como siempre. **Ninguna de las 7 garantías
de aislamiento se toca**, y por eso no hay test en `tests/isolation/` — lo que sí
hay es el test de no suplantación, que es otra cosa y va en su sitio.

## Estados de un código

```
        emitido ──(canje correcto)──► consumido
           │
           ├──(se emite otro para la misma persona)──► consumido (sustituido)
           │
           └──(pasan 10 minutos)──► caducado
```

**Los tres finales responden lo mismo hacia fuera** (R4.5). La diferencia sólo
existe dentro, para la auditoría.

## Lo que NO cambia

- **`principal_sessions`**: ninguna columna nueva. La sesión de la aplicación se
  distingue por el `user_agent` que ya se guarda, porque la cáscara se anuncia con
  `AuphereDesktop/<versión>` desde la spec 002 (D2 de la investigación).
- **`local_workstation` / credenciales de máquina**: intactas. Este código no ata
  una máquina; ata una persona.
- **El modelo del escritorio**: `BarState` gana una acción, no un estado. Los
  siete estados de conexión siguen siendo siete.
