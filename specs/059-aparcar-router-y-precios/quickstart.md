# Guía de verificación: spec 059

## Antes

- Stack local levantado: `docker compose up -d`. La API debe responder en `:8000/health`.
- Migraciones al día: `cd apps/api && uv run alembic upgrade head`. La última debe ser
  `0231_platform_settings`.
- Un worker local en marcha, para que publique su latido. Sin él, Retirar y
  «No disponible» responden `defaults_unverified`, y eso también se comprueba.

## Pruebas automáticas (lo que bloquea)

```bash
./scripts/verify.sh lint                                        # ruff + mypy --strict
cd apps/api && uv run pytest tests/isolation/test_model_usage_scan_rls.py -x
cd apps/api && uv run pytest tests/integration/models tests/unit -k "model_usage or sale or lifecycle or registry or judge or eval or auphere" -x
cd apps/worker && uv run --with lupa pytest tests/unit -k "heartbeat or platform_models or pricing or promote" -x
cd apps/admin && pnpm vitest run src/components/shell src/app/'(dashboard)'/models src/app/'(dashboard)'/status src/app/'(dashboard)'/channels src/app/'(dashboard)'/builder src/app/'(dashboard)'/auphere
cd apps/admin && pnpm next build
```

Una sola suite de pytest a la vez: dos suites concurrentes comparten la base y dan
rojos que no son del cambio.

## Recorrido a mano (pase vivo, staging o local)

1. **Router aparcado.** El menú no tiene Router ni Certificaciones. `/router`,
   `/router/anomalies` y `/certifications` dan «no existe». Estado no tiene el
   bloque Router, y Modelos no tiene «Nuevo despliegue», «Activar», «Certificado
   en» ni «Le falta».
2. **Protección.** En Modelos, Sol y Terra muestran «En uso» y su menú no ofrece
   Retirar ni «No disponible». Un `curl` a `…/unavailable` sobre Sol responde
   `409 model_in_use`. Con el worker parado, más de 60 s después, responde
   `409 defaults_unverified`.
3. **Vuelta atrás.** Sobre GPT-4o (sin uso): «No disponible» y después «Volver a
   disponible» lo dejan activo. «Retirar» y después «Cancelar retirada», también.
4. **Precio de venta.**
   - Cambiar los pesos de Luna al 2,2 propuesto: el chip pasa a «En el objetivo».
   - Bajar la salida por debajo del suelo: el rechazo nombra el carril.
   - Cambiar el multiplicador a 2,5 con «aplicar a todos»: todos quedan en el
     objetivo, y la auditoría tiene una entrada por modelo.
   - Volver a 2,2.
5. **Coste.** El diálogo de Sol trae el coste vigente y la fecha de hoy. Una fecha
   de ayer se rechaza. Guardar no crea ninguna notificación de partner.
6. **Ancho.** A 1280 px, las 14 filas muestran el nombre y «Precio» sin
   desplazamiento horizontal.
7. **Limpiezas.**
   - Números de Auphere no tiene «Rotar secret» y su estado vacío explica qué
     significa.
   - `/qa/dev/ucm-gallery` da «no existe».
   - Sin `NEXUS_META_CONFIG_ID_WA_LOGIN`, Canales no tiene la subpestaña de la
     beta.
   - Calibración del juez nombra el modelo juez.
   - Evaluación dice 120 y enseña dos cifras.
8. **Números de Auphere** (en staging, con un número de prueba): alta, cambio de
   token con motivo, desactivar y reactivar. La auditoría nombra a la persona.
