# Quickstart: Diagnóstico IA de Amacrux (009)

## Requisitos
Node 22, pnpm 10.15 (`npm i -g pnpm@10.15.0` si Corepack falla), sin Docker ni base de datos.

## Arrancar
```bash
cd apps/amacrux-event
cp .env.example .env.local        # sin RESEND_API_KEY → modo demo
pnpm install
pnpm dev                          # http://localhost:3120
```

## Verificar
```bash
pnpm check        # lint + typecheck + test + check-no-env-leaks
pnpm build        # build de producción
curl -s localhost:3120/api/health
curl -s -X POST localhost:3120/api/leads -H 'content-type: application/json' -d @docs/fixtures/lead-valid.json
curl -s -X POST localhost:3120/api/leads -H 'content-type: application/json' -d '{"name":"x"}'   # 400
```

## Escenarios de validación (manuales, navegador a 360 px)
1. **Perfil A → C**: recorrer los cuatro perfiles de `docs/EVENT-GUIDE.md` y comprobar categorías esperadas (spec Historia 1, escenarios 4–7).
2. **Atrás / recarga**: responder 3 pantallas, volver 2, cambiar, recargar → mismo paso y respuestas.
3. **Reinicio**: desde el resultado, "Reiniciar" + confirmar → bienvenida limpia (2 acciones).
4. **Sin datos**: "Prefiero no dejar mis datos" → resultado visible, copiar funciona.
5. **Lead**: enviar válido (demo: confirmación honesta), inválido (errores por campo), doble toque (un solo POST en la pestaña Red).
6. **Storage corrupto**: `sessionStorage.setItem("amacrux-diagnostico:v1","{")` y recargar → arranca limpio con aviso.
7. **Accesibilidad**: recorrer con Tab/Enter/Espacio; foco visible; lector de pantalla anuncia progreso.
8. **Dark mode y reduced motion**: activar en el sistema y comprobar contraste y ausencia de animaciones.
