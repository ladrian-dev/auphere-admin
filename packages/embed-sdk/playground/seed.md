# Seed local para el playground

Prerequisito: stack local corriendo (`docker compose up -d` en la raíz,
`uv run alembic upgrade head` y `uv run uvicorn nexus_api.main:app` en
`apps/api`).

```bash
ADMIN="Authorization: Bearer dev-admin-token-change-me"
API=http://localhost:8000

# 1. Partner
PARTNER_ID=$(curl -s -X POST "$API/admin/partners" -H "$ADMIN" -H 'Content-Type: application/json' \
  -d '{"name": "Demo Partner", "slug": "demo"}' | jq -r .id)

# 2. API key con el origin del playground (guarda el plaintext que devuelve)
curl -s -X POST "$API/admin/partners/$PARTNER_ID/keys" -H "$ADMIN" -H 'Content-Type: application/json' \
  -d '{"allowed_origins": ["http://localhost:5500"]}' | jq '{plaintext, id}'

# 3. Provisionar un cliente (crea tenant en provisioning) — con la key del paso 2
KEY="ak_live_…"   # ← plaintext del paso 2
curl -s -X POST "$API/v1/partners/clients" -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"external_client_ref": "client-1", "name": "Tienda Demo"}' | jq

# 4. (Opcional, para llegar hasta templates/broadcast sin Meta real)
#    Mapear la ref a un tenant existente con canal WhatsApp activo:
#    en el admin (http://localhost:3001/partners) → tab Tenants → vincular
#    external_client_ref "client-1" al tenant con canal ACTIVE.

# 5. Mintear un session token para pegar en el playground
#    (el mint es server-to-server: CORS bloquea llamarlo desde el browser
#    del playground — pegar el token es el camino fiel al modelo real)
curl -s -X POST "$API/v1/widget-sessions" -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' \
  -d '{"external_client_ref": "client-1"}' | jq -r .session_token

# 6. Servir el playground en el origin permitido
cd packages/embed-sdk && python3 -m http.server 5500
# → http://localhost:5500/playground/index.html — pegar el token y abrir
```

Nota máquina local: si npm/pnpm dan ETIMEDOUT, prefijar
`NODE_OPTIONS="--no-network-family-autoselection"`.

Recordatorio: `GET /v1/embed/templates` pega a Meta Graph con las
credenciales del tenant — para un tenant sin credenciales reales devuelve
409 y el modal muestra el estado de error (esperado en local).
