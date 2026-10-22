# Quickstart — spec 044

Cómo ver y comprobar lo que construye esta spec. Lo que no se pudo hacer en la
máquina queda escrito en `evidence/hallazgos.md` con su razón.

## 1. Arrancar

```bash
pnpm --dir apps/mobile install --frozen-lockfile
```

- **Contra la API local** (cuando la 043 exista): la API en `:8000` y Metro con
  `pnpm --dir apps/mobile exec expo start --dev-client`. El cliente de desarrollo
  de la 042 sirve: esta spec no añade nada nativo.
- **Contra la API de la 043 antes de fusionarla** (como se probó el
  2026-10-22): el código del worktree de `consolas-web` sobre una base propia,
  nunca sobre la compartida.

  ```bash
  W=<worktree de consolas-web>; DB=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_app_movil_044
  (cd $W/apps/api && NEXUS_DATABASE_URL=$DB uv run --frozen alembic upgrade head)
  (cd $W/apps/api && NEXUS_DATABASE_URL=$DB uv run --frozen python scripts/dev_seed_reservas_demo.py)
  ```

  La API de ese worktree en `:8010` con esa `NEXUS_DATABASE_URL` (y el resto de
  `apps/api/.env.local`), y Metro con `EXPO_PUBLIC_API_URL=http://localhost:8010`.
  Las personas de prueba son las que imprime la semilla: Peluquería Cultor
  (Servicios) y Restaurante La Fonda (Aforo). Para escribir el correo en el
  simulador, mejor Maestro (`inputText`): el teclado del simulador cambia `@` y `-`.
- **Con datos de ejemplo** (mientras no exista): igual, con
  `EXPO_PUBLIC_RESERVAS_DEMO=services` (Barbería Norte) o `capacity` (Casa
  Lucía). La API local sigue haciendo falta para entrar, la Bandeja y Consumo;
  Reservas sale de la fuente de ejemplo y lo dice en cada pantalla.

Simuladores de referencia: «13 26» (iPhone 13, iOS 26.0.1) y el emulador
Pixel 9 (API 36). Antes de capturar en un build de desarrollo, apagar el botón
flotante del cliente de desarrollo (memoria del repo: capturas sin tocar
código, y nada de recargas a mitad de tanda).

## 2. Recorridos

1. **Servicios · Día** — abrir Reservas: lista de hoy con «Ahora»; Cuadrícula;
   filtrar por profesional; un día cerrado (domingo).
2. **Aforo · Día** — cifras, tira de franjas (tocar una filtra), grupos por hora,
   «Llegó» en una de la próxima media hora, «No vino» en una pasada y
   «Deshacer» desde el aviso breve.
3. **Llegada sin reserva** — «+» → 4 → «Registrar llegada»; con 30 → «No cabe»
   → «Apuntar en lista de espera».
4. **Nueva reserva** — Servicios: Corte, Cualquiera, mañana, 17:00, nombre,
   guardar. Aforo: 12 comensales (aviso de máximo), hora con «quedan N».
5. **Hoja de una reserva** — marcar confirmada; cancelar (alerta con WhatsApp).
6. **Semana y Mes** — en los dos modos; tocar un día del mes; tocar una celda del
   mapa de calor.
7. **Lista de espera y Ajustes de reservas** — ofrecer (cuenta atrás), quitar;
   cambiar el aforo; bloquear la cena de mañana.
8. **Inicio** — atención con reservas sin confirmar y «Ver reservas»; «Hoy en
   Reservas»; tocar conversaciones y saldo.
9. **Bandeja y conversación** — grupo «Esperan a una persona»; tarjeta con la
   espera; tomar el control: «Devolver» y chips de respuestas.
10. **Contacto** — «Próxima reserva» lleva a la reserva.
11. **Consumo** — «Te alcanza hasta…».
12. **Ajustes y permiso** — avisos por grupo; «Ahora no» visible en 4,7″.

## 3. Estados en cada pantalla de Reservas

Ideal · vacío · carga (esqueleto) · error con «Reintentar» · sin red · parcial,
en claro y oscuro, y con el texto en AX-L. Para provocarlos con los datos de
ejemplo: `EXPO_PUBLIC_RESERVAS_DEMO_STATE=empty|error|slow`.

## 4. Verificar

```bash
./scripts/verify.sh mobile
```

## 5. Builds (no se lanzan sin que Luis lo pida)

Ver `docs/app-movil.md` §Builds y la lista de lo que crea Luis en
`specs/044-la-app-con-reservas/evidence/builds.md`.
