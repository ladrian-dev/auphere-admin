#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Prueba manual de entrega de plantilla — Muna (tenant `mouna`, partner amacrux)
#
# Recorre el MISMO camino de producción que usa el barrido de recordatorios:
#   API pública de partners -> validación de plantilla APPROVED contra Meta
#   -> cola -> dispatcher saliente -> Cloud API -> callbacks de estado.
#
# NO ejecuta nada por su cuenta: pide confirmación antes del envío real.
#
# Uso:   ./prueba-plantilla-muna.sh +58XXXXXXXXXX
# ---------------------------------------------------------------------------
set -euo pipefail

DEST="${1:-}"
[ -n "$DEST" ] || { echo "Uso: $0 +58XXXXXXXXXX   (número E.164 que dé el cliente)"; exit 1; }

API=https://api.auphere.com
PARTNER=7dd48741-4122-4edc-83fb-bac10f71d805      # amacrux
CLIENT=mouna                                       # external_client_ref
PLANTILLA="${PLANTILLA:-recordatorio_pago_vencido}"
export AWS_PROFILE="${AWS_PROFILE:-nexus}" AWS_REGION="${AWS_REGION:-eu-south-2}"

jq_or_python() { python3 -m json.tool 2>/dev/null || cat; }

echo "== 1/6 · Token de admin (no se imprime) =="
ADMIN=$(aws secretsmanager get-secret-value --secret-id nexus/prod/app \
  --query SecretString --output text \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["NEXUS_ADMIN_TOKEN"])')
[ -n "$ADMIN" ] || { echo "No pude leer NEXUS_ADMIN_TOKEN"; exit 1; }

echo "== 2/6 · Clave temporal de partner con scope broadcasts =="
# Amacrux hoy solo tiene claves con {provision} y {provision,widget_sessions}:
# ninguna puede enviar. Se crea una y se revoca en el paso 6.
KEYJSON=$(curl -sS -X POST "$API/admin/partners/$PARTNER/keys" \
  -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
  -d '{"type":"test","scopes":["broadcasts"]}')
KEY=$(printf '%s' "$KEYJSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["plaintext"])')
KEY_ID=$(printf '%s' "$KEYJSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "   clave creada: $KEY_ID"

revocar() {
  echo "== 6/6 · Revocando la clave temporal =="
  curl -sS -X POST "$API/admin/partners/$PARTNER/keys/$KEY_ID/revoke" \
    -H "Authorization: Bearer $ADMIN" >/dev/null && echo "   revocada: $KEY_ID"
}
trap revocar EXIT

echo "== 3/6 · Plantillas APPROVED en la WABA de Muna (lectura viva de Meta) =="
# Aquí se ve la CATEGORÍA de cada plantilla. Es el dato que explica por qué
# recordatorio_pago_vencido se entrega y recordatorio_pago_proximo da 131042.
curl -sS "$API/v2/partners/clients/$CLIENT/templates" \
  -H "Authorization: Bearer $KEY" \
  | python3 -c '
import json,sys
for t in json.load(sys.stdin)["templates"]:
    print(f'"'"'{t["name"]:<32} {t.get("language"):<4} {t.get("category"):<16} {t.get("status")}  calidad={t.get("quality_score")}'"'"')
'

echo
echo "== 4/6 · Envío real =="
echo "   plantilla : $PLANTILLA"
echo "   destino   : $DEST"
echo "   desde     : +584249018017 (rol notifications, WABA 100224919371986)"
read -r -p "   ¿Enviar? [s/N] " ok
[ "$ok" = "s" ] || { echo "   cancelado"; exit 0; }

IDEM="prueba-manual-$(date +%Y%m%d-%H%M%S)"
BODY=$(python3 - "$DEST" "$PLANTILLA" "$IDEM" <<'PY'
import json, sys
from datetime import date
dest, plantilla, idem = sys.argv[1:4]
print(json.dumps({
  "template_name": plantilla,
  "language": "es",
  "idempotency_key": idem,
  "recipients": [{"phone": dest, "variables": {
      "cliente": "Prueba Auphere",
      "negocio": "Muna Restaurante",
      "monto": "1,00",
      "fecha": date.today().strftime("%d/%m/%Y"),
  }}],
}))
PY
)
RESP=$(curl -sS -X POST "$API/v2/partners/clients/$CLIENT/broadcasts" \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d "$BODY")
echo "$RESP" | jq_or_python
BID=$(printf '%s' "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("broadcast_id",""))')
[ -n "$BID" ] || { echo "No hubo broadcast_id — mira el error de arriba."; exit 1; }

echo
echo "== 5/6 · Estado de entrega (12 sondeos, 5 s) =="
# pending -> sent (Meta lo aceptó) -> delivered (llegó al teléfono) -> read
# failed + reason: el código de Meta. 131042 = elegibilidad/facturación.
for i in $(seq 1 12); do
  sleep 5
  EST=$(curl -sS "$API/v2/partners/clients/$CLIENT/broadcasts/$BID" -H "Authorization: Bearer $KEY")
  printf '   [%02d] ' "$i"; printf '%s' "$EST" | python3 -c '
import json,sys
d=json.load(sys.stdin)
for r in d.get("recipients", []):
    print(f'"'"'{r["status"]:<10} {r.get("reason") or ""}'"'"')
' || printf '%s\n' "$EST"
  printf '%s' "$EST" | grep -qE '"status": *"(delivered|read|failed)"' && break
done

echo
echo "Veredicto:"
echo "  delivered / read -> el mensaje llegó. Camino de producción OK."
echo "  sent (y ahí se queda) -> Meta lo aceptó pero el teléfono no confirmó:"
echo "     número sin WhatsApp, o el callback de estado no llegó."
echo "  failed 131042 -> sigue el problema de facturación/elegibilidad en el"
echo "     Business Manager 'Muna restaurante' (1150509768155254) para ESA"
echo "     categoría de plantilla."
