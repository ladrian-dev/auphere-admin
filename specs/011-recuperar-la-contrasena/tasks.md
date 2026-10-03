---

description: "Tareas — spec 011, recuperar la contraseña"
---

# Tareas: Recuperar la contraseña, y salir con la puerta cerrada

**Entrada**: `specs/011-recuperar-la-contrasena/` — spec.md, plan.md

**Tests**: **no son opcionales** (§VII). Tres rojos que no son el camino feliz,
marcados con ⚠️.

---

## Phase 1: Setup

- [x] T001 Verificar y marcar la puerta de **licencias**: `git diff` sobre `apps/api/pyproject.toml` y `apps/console/package.json` vacío al terminar. _Requisitos: —_

- [x] T002 Verificar y marcar la puerta del **medidor**: no aplica — ni modelo, ni reloj de máquina, ni herramienta de pago. Un correo por petición, acotado por T012. _Requisitos: —_

- [x] T003 Comprobar **leyendo la migración**, no suponiéndolo, qué motivo de archivado sembró la spec 012 y reutilizarlo. Es lo que costó una enmienda allí. _Requisitos: 3.2_

---

## Phase 2: Foundational

- [x] T004 `PasswordResetRequest` en `apps/api/src/nexus_api/db/models/console_identity.py`, hermana de `SignupRequest` (`db/models/signup.py:49-90`): `account_id`, `token_hash` `String(64)` con **índice único**, `expires_at`, `used_at` nulo. **Solo el hash** (R1.4, R5.2). _Requisitos: 1.2, 1.4, 5.2_

- [x] T005 **La única migración de la spec**, en `apps/api/alembic/versions/`: crea la tabla en el esquema `console_auth`. Se ensaya arriba/abajo/arriba. _Requisitos: 1.2_

**Checkpoint**: la tabla existe y nada más cambió.

---

## Phase 3: US1 — Pedir y canjear (P1) · **MVP**

### Tests ⚠️

- [x] T006 [US1] ⚠️ **El no-oráculo, comparado carácter a carácter.** Test en `apps/api/tests/integration/test_password_reset.py`: las respuestas de (a) dirección con cuenta, (b) sin cuenta, (c) con el envío caído y (d) en el tope son **idénticas** — mismo estado, mismo cuerpo. Un test que solo mire el código de estado no ve la diferencia que importa. _Requisitos: 1.3, 1.5_

- [x] T007 [P] [US1] Test: el enlace sirve **una vez**; el segundo intento dice que ya no vale sin revelar de quién era. _Requisitos: 2.3, 5.1, 5.3_

- [x] T008 [P] [US1] Test: pedir uno nuevo **invalida los anteriores** de esa cuenta. Sin esto, tres peticiones dejan tres llaves buenas. _Requisitos: 1.6_

- [x] T009 [P] [US1] Test: tras canjear, la contraseña anterior **no sirve** y la nueva sí; y si la cuenta estaba bloqueada por intentos, queda desbloqueada. _Requisitos: 2.1, 2.2, 2.4_

- [x] T010 [P] [US1] Test: lo guardado **no permite reconstruir el enlace** — el valor en claro no aparece en la fila. _Requisitos: 1.4, 5.2_

### Implementación

- [x] T011 [US1] `services/password_reset.py`: crear la petición (hash + caducidad de **1 hora**, D-6), invalidar las vivas de esa cuenta en la misma transacción, y canjear. Reutiliza el generador de `core/one_time_codes.py`. _Requisitos: 1.2, 1.6, 2.1_

- [x] T012 [US1] El techo —**5 por dirección y hora**— con `services/one_time_code_limits.py`, que **ya existe y no se reescribe** (R5.5): su forma de dos claves —fallos en ventana y espera creciente— es la correcta, y borra ambas al acertar. La clave es **la dirección** (R5.4). Comprobado **antes** de mirar si la cuenta existe, para que el tiempo no delate (D-2). _Requisitos: 1.5, 5.4, 5.5_

- [x] T013 [US1] Las dos rutas públicas en `api/console/password_reset.py`. La de pedir devuelve **siempre lo mismo**: sin cuenta, con envío caído, en el tope y con cuenta archivada. _Requisitos: 1.1, 1.3, 1.5_

- [x] T014 [US1] El canje llama a `console_identity.set_password`, que **ya existe y no tiene llamantes** (`console_identity.py:294`) — reinicia intentos y desbloqueo incluidos. _Requisitos: 2.1, 2.2, 2.4_

- [x] T015 [US1] Las dos pantallas en `apps/console/src/app/(auth)/`: pedir y elegir la nueva. La primera **no finge que ya está** mientras el correo no llega: dice qué mirar y en cuánto tiempo (§V). Tras canjear, **lleva a la entrada** diciendo que ya puede entrar (D-5). _Requisitos: 1.1, 2.5_

- [x] T016 [US1] **D-4, el repliegue SMTP** en `services/email.py`: solo cuando no hay clave de Resend **y** sí hay `NEXUS_SMTP_URL`. En producción no hay `SMTP_URL`, así que su camino no cambia. Y cablear Mailhog, que lleva en `docker-compose.yml:34-39` sin conectar a nada. _Requisitos: —_

**Checkpoint US1**: deja de hacer falta escribir un hash a mano en producción. **Entregable solo.**

---

## Phase 4: US2 — Restablecer retira todo el acceso (P1)

### Tests ⚠️

- [x] T017 [US2] ⚠️ **La atomicidad, y no se ve por el camino feliz.** Forzar un fallo **entre las mitades** y comprobar que no queda una contraseña cambiada con las sesiones vivas. Si el test pasa sin haber roto nada, no está probando la atomicidad. _Requisitos: 3.3_

- [x] T018 [US2] ⚠️ **El alcance, con dos personas.** `tests/isolation/test_42_reset_scope.py`: montar **dos** cuentas con sesiones y máquinas, restablecer una, y comprobar que la otra **no se movió**. Corre con **rol dueño**: la RLS no lo impide, solo el `WHERE`. _Requisitos: 3.5_

- [x] T019 [P] [US2] Test: tras restablecer, una sesión abierta en otro sitio deja de valer y las máquinas quedan archivadas con su motivo. _Requisitos: 3.1, 3.2_

- [x] T020 [P] [US2] Test: queda asiento de la retirada, con la persona y el motivo. _Requisitos: 3.4_

### Implementación

- [x] T021 [US2] El canje llama a `services/principal_access.revoke_all_access` **dentro de su misma transacción**. La pieza **ya existe** —la construyó la 012— y **no hace commit a propósito**, que es lo que permite componerla aquí. No se reescribe. _Requisitos: 3.1, 3.2, 3.3_

- [x] T022 [US2] La pantalla avisa **antes** de restablecer de que cierra las sesiones y obliga a volver a entrar en cada máquina (R3.6). Con la 012 entregada eso es «abre la app y entra», no repetir una ceremonia. _Requisitos: 3.6_

**Checkpoint US2**: restablecer deja fuera a quien entró. **Entregable solo.**

---

## Phase 5: US3 — El aviso (P2)

- [x] T023 [P] [US3] Test: un restablecimiento con éxito envía aviso; el aviso **no lleva** contraseña ni enlace que sirva para entrar. _Requisitos: 4.1, 4.3_

- [x] T024 [P] [US3] Test: si el aviso no se puede enviar, el restablecimiento **ya ocurrido no se deshace** y el fallo queda en los registros. _Requisitos: 4.4_

- [x] T025 [US3] El aviso, con cuándo ocurrió y a quién escribir si no fue la persona. _Requisitos: 4.1, 4.2_

---

## Phase 6: Polish

- [x] T026 Pasar los **cuatro gates de interfaz** del `CLAUDE.md` del workspace sobre las dos pantallas nuevas de `(auth)/`. _Requisitos: 1.1, 2.5_

- [x] T027 Actualizar `docs/` con el circuito y con **por qué el rechazo es uniforme**, en el mismo commit. _Requisitos: 1.3_

- [x] T028 Ejecutar **`./scripts/verify.sh` entero**. Una sola ejecución de `pytest` a la vez, comprobada con `ps` antes de lanzar. _Requisitos: —_

- [ ] T029 Recorrer el circuito a mano con Mailhog delante. **Lo que salga de ahí manda.** Lo firma Luis. _Requisitos: 1.1, 2.1, 3.1_

---

## Dependencies & Execution Order

```
Setup (T001-T003) → Foundational (T004-T005)
   ↓
US1 (T006-T016) ──┬─→ US2 (T017-T022)
                  └─→ US3 (T023-T025)
   ↓
Polish (T026-T029)
```

### El orden que importa

- **T012 antes que T013.** El tope se comprueba **antes** de mirar si la cuenta
  existe: si se hace al revés, el tiempo de respuesta delata cuáles existen.
- **T021 dentro de la transacción de T014**, no después. R3.3 no se cumple de
  otra forma, y la pieza no hace commit precisamente para esto.
- **T017 y T018 no se prueban por el camino feliz.** Uno rompe a propósito; el
  otro necesita **dos** personas.
- **T003 antes que T021.** Inventar un motivo de archivado nuevo cuando ya hay
  vocabulario sembrado es lo que costó una enmienda en la 012.

### MVP

T001-T016: el circuito entero. Retira el procedimiento manual que el 2026-09-18
obligó a escribir un hash en producción.
