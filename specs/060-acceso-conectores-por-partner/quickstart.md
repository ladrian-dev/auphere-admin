# Quickstart: comprobar el acceso a conectores por partner

## En local

```bash
docker compose up -d
cd apps/api && uv run alembic upgrade head
```

1. **Nada cambia al desplegar.** Abrir un partner en el panel → Conectores. Todos aparecen «Habilitado», heredado. Abrir la consola de ese partner: ve los mismos conectores que antes.
2. **Restringir a un partner.** En el panel, abrir un conector (por ejemplo `woocommerce`) → «Disponible para» → valor por defecto «Deshabilitado», con motivo, y habilitarlo para un partner A.
   - Consola del partner A: lo ve.
   - Consola del partner B: no lo ve, ni en integraciones, ni en capacidades, ni en el constructor.
   - Un partner creado después tampoco lo ve.
3. **Quitar acceso con un cliente conectado.** Con un cliente de A que tenga el conector conectado, deshabilitarlo para A.
   - El panel enseña el cliente y sus agentes, y pide confirmar.
   - Al cancelar, no cambia nada.
   - Al confirmar, el agente de ese cliente deja de tener sus herramientas en el turno siguiente, y la ficha del cliente en el panel marca la conexión «No disponible para su partner».
4. **Volver.** Rehabilitarlo para A: el agente recupera las mismas herramientas sin tocar nada en la consola.
5. **Conector por defecto de un partner.** Intentar deshabilitar para un partner su `default_connector_slug`: el panel lo rechaza y dice qué cambiar antes.

## Pruebas

```bash
cd apps/api && uv run pytest tests/isolation/test_060_connector_partner_access.py tests/unit/connectors/test_availability_rule.py tests/unit/test_060_sweeps.py tests/integration/connectors/test_connector_access_admin.py
./scripts/verify.sh lint
cd apps/admin && pnpm vitest run src/app/\(dashboard\)/connectors src/app/\(dashboard\)/partners
```

## En staging, antes de la 061

Dejar `quedate` (cuando exista) deshabilitado por defecto y habilitado para Amacrux.
