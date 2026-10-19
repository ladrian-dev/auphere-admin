# T110 — Producción

**Fecha:** 2026-10-19. Completa [T110-staging.md](T110-staging.md): el commit
`11f0f2c8` se titula «… and the production rollout», pero aquel documento solo
recoge staging.

## Desplegada: sí

| Qué | Evidencia | Resultado |
|---|---|---|
| API (AWS) | `deploy-prod.yml`: `da4b1596` (la spec) el 2026-10-10 15:35 UTC; último, `28a5b562` el 2026-10-12 15:08 UTC | `success` los dos; despliegue `production` de `28a5b562` en `success` a las 15:41 UTC |
| Consola (Vercel) | despliegue «Production – auphere-console» de `28a5b562` | `success`, 2026-10-12 15:22 UTC |
| Migraciones | `/nexus/prod/migrate` (CloudWatch, una consulta de solo lectura) | `0150→0151 … 0154→0155` el 2026-10-10 16:03:17–18 UTC; `0155→0156` el 2026-10-12 12:22 UTC; `0156→0157` a las 13:36 UTC. La consulta filtraba `015`: 0147–0149 no se listaron |
| Salud | `curl --resolve api.auphere.com:443:35.43.199.219 https://api.auphere.com/health` (certificado verificado) | `200 {"status":"ok"}` |
| Rutas lite | la misma ALB, sin token | `/console/lite/me`, `/console/lite/home` y `/console/lite/inbox/conversations` → **401**; una ruta inexistente de `/console/` → **404**. Las rutas existen y piden identidad |

`28a5b562` es la misma base sobre la que se cerró la spec (T021, T105, T109,
T111 y `./scripts/verify.sh`), así que lo validado en local es lo que corre en
producción, salvo el cambio de cierre, que aún no está fusionado.

**La IP de la ALB cambió:** hoy es `35.43.199.219` y el `CLAUDE.md` del repo
dice `51.95.216.39`. El propio documento avisa de que cambia. Se resuelve con
`dig +short nexus-prod-317439020.eu-south-2.elb.amazonaws.com`.

## Funcionando para un cliente: no comprobado

- **Nadie ha entrado como persona de un cliente en producción en esta
  comprobación.** No hay una persona de cliente de pruebas en producción, y
  crear una (encender el acceso de un cliente real e invitar a alguien) es una
  decisión del owner, no de la sesión.
- **No se leyeron datos ni logs de la aplicación.** Saber si algún cliente
  tiene el acceso encendido, si hay tráfico real en `/console/lite/*` o cómo
  quedó el historial de evaluación de los clientes existentes exige leer
  producción. El permiso de la sesión lo denegó después de la consulta de
  migraciones, y no se intentó por otro camino.

## Para cerrarlo

1. En el admin de producción, pestaña «Acceso» de un cliente con WhatsApp:
   encender Panel, Bandeja y Consumo e invitar a una persona de prueba.
2. Recorrer el [quickstart](../quickstart.md) como esa persona, o correr la e2e,
   que **nunca envía mensajes**:

   ```bash
   E2E_BASE_URL=https://console.auphere.com E2E_CLIENT_EMAIL=… E2E_CLIENT_PASSWORD=… \
     pnpm --dir apps/console exec playwright test --project=lite
   ```

3. Para CE-006 con clientes reales: comparar sus `eval_runs` de antes y después
   del 2026-10-10 16:03 UTC. Ver
   [T109-regresion-multiagente.md](T109-regresion-multiagente.md).
