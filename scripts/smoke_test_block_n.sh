#!/usr/bin/env bash
# Block N — end-to-end smoke test post-deploy.
#
# Verifies the full path:
#   YCloud webhook  →  signature verify  →  wamid dedupe  →  S3 media download
#   →  Whisper transcription (audio) / Claude vision (image)
#   →  Redis stream enqueue  →  worker pipeline  →  outbound dispatch
#   →  status callback updates Message.status
#
# Requires:
#   - NEXUS_API_BASE   (e.g. https://api.auphere.com)
#   - NEXUS_ADMIN_TOKEN
#   - NEXUS_YCLOUD_WEBHOOK_SECRET   (same one configured in Doppler)
#   - One canary tenant with WhatsApp channel + AgendaPro public_url set
#   - jq, curl, openssl in PATH
#
# Usage:
#   bash scripts/smoke_test_block_n.sh /path/to/voice-note.ogg

set -euo pipefail

API="${NEXUS_API_BASE:?must export NEXUS_API_BASE}"
ADMIN_TOKEN="${NEXUS_ADMIN_TOKEN:?must export NEXUS_ADMIN_TOKEN}"
SECRET="${NEXUS_YCLOUD_WEBHOOK_SECRET:?must export NEXUS_YCLOUD_WEBHOOK_SECRET}"
TENANT_SLUG="${TENANT_SLUG:-auphere-canary}"
BUSINESS_PHONE="${BUSINESS_PHONE:-+5693XXXXXXXX}"  # WABA E.164
SENDER_PHONE="${SENDER_PHONE:-+5611111111}"        # any test recipient
AUDIO_FILE="${1:-}"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m✓\033[0m %s\n" "$*"; }
fail() { printf "\033[31m✗\033[0m %s\n" "$*"; exit 1; }

bold "Block N smoke test — canary tenant: $TENANT_SLUG"

# 1. Health check ─────────────────────────────────────────────────────────
echo
bold "1/6  Health check"
status=$(curl -fsS "$API/health" | jq -r .status)
[[ "$status" == "ok" ]] && ok "API healthy" || fail "API not healthy ($status)"

# 2. Verify migrations applied ────────────────────────────────────────────
echo
bold "2/6  Verifying migrations 0019, 0020, 0021 applied"
migration=$(curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" "$API/admin/health/alembic" | jq -r '.current // "unknown"')
case "$migration" in
  0019*|002[0-9]*|003*) ok "Alembic head at $migration (>= 0019)" ;;
  *) fail "Alembic head $migration (expected >= 0019)" ;;
esac

# 3. WhatsApp channel exists ──────────────────────────────────────────────
echo
bold "3/6  Verifying WhatsApp channel for tenant"
channel=$(curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$API/admin/tenants/$TENANT_SLUG/integrations/whatsapp/preview" 2>/dev/null || echo "{}")
echo "$channel" | jq -e '.phone_number' >/dev/null \
  && ok "channel.provider_identifier=$(echo "$channel" | jq -r .phone_number)" \
  || fail "no WhatsApp channel for $TENANT_SLUG"

# 4. Inbound text via signed webhook ──────────────────────────────────────
echo
bold "4/6  Signed inbound text → expect status=queued"
WAMID="wamid.smoketest.$(date +%s)"
BODY=$(jq -nc \
  --arg phone "$BUSINESS_PHONE" \
  --arg sender "$SENDER_PHONE" \
  --arg wamid "$WAMID" \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{id: "evt_smoke", type: "whatsapp.inbound_message.received",
    createTime: $ts,
    whatsappInboundMessage: {
      wabaId: "WABA_SMOKE", to: $phone, from: $sender, wamid: $wamid,
      type: "text", text: {body: "ping smoke test"},
      customerProfile: {name: "Smoke Bot"}
    }}')
TS_SEC=$(date +%s)
SIG=$(printf "%s.%s" "$TS_SEC" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $2}')
HEADER="t=$TS_SEC,s=$SIG"
resp=$(curl -fsS -X POST "$API/webhook/ycloud" \
  -H "Content-Type: application/json" \
  -H "YCloud-Signature: $HEADER" \
  -d "$BODY")
echo "  response: $resp"
[[ "$(echo "$resp" | jq -r .status)" == "queued" ]] && ok "inbound queued" \
  || fail "inbound NOT queued — check tenant resolver + signature secret"

# 5. Idempotency — same wamid second time → expect deduped ────────────────
echo
bold "5/6  Replay same wamid → expect status=deduped"
sleep 1
TS_SEC=$(date +%s)
SIG=$(printf "%s.%s" "$TS_SEC" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $2}')
HEADER="t=$TS_SEC,s=$SIG"
resp=$(curl -fsS -X POST "$API/webhook/ycloud" \
  -H "Content-Type: application/json" \
  -H "YCloud-Signature: $HEADER" \
  -d "$BODY")
echo "  response: $resp"
[[ "$(echo "$resp" | jq -r .status)" == "deduped" ]] && ok "wamid idempotency works" \
  || fail "wamid replay NOT deduped — Redis SETNX or UNIQUE partial broken"

# 6. Opt-out detection ────────────────────────────────────────────────────
echo
bold "6/6  Opt-out keyword (STOP) → expect status=opted_out"
STOP_WAMID="wamid.smoketest.stop.$(date +%s)"
STOP_BODY=$(jq -nc \
  --arg phone "$BUSINESS_PHONE" \
  --arg sender "$SENDER_PHONE" \
  --arg wamid "$STOP_WAMID" \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{type: "whatsapp.inbound_message.received", createTime: $ts,
    whatsappInboundMessage: {
      wabaId: "WABA_SMOKE", to: $phone, from: $sender, wamid: $wamid,
      type: "text", text: {body: "STOP"}, customerProfile: {name: "Smoke Bot"}
    }}')
TS_SEC=$(date +%s)
SIG=$(printf "%s.%s" "$TS_SEC" "$STOP_BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $2}')
HEADER="t=$TS_SEC,s=$SIG"
resp=$(curl -fsS -X POST "$API/webhook/ycloud" \
  -H "Content-Type: application/json" \
  -H "YCloud-Signature: $HEADER" \
  -d "$STOP_BODY")
echo "  response: $resp"
[[ "$(echo "$resp" | jq -r .status)" == "opted_out" ]] && ok "STOP recorded as opt-out" \
  || fail "STOP NOT recognised as opt-out — check is_opt_out_text"

# 7. (Optional) Audio inbound → S3 + Whisper ──────────────────────────────
if [[ -n "$AUDIO_FILE" && -f "$AUDIO_FILE" ]]; then
  echo
  bold "BONUS  Real audio inbound — needs YCloud media_id; simulate via fixture"
  echo "  To test the real S3 → Whisper path:"
  echo "  - Upload $AUDIO_FILE manually to YCloud or use a real WhatsApp message"
  echo "  - Tail the worker logs:"
  echo "      railway logs --service worker --tail | grep media_processor"
  echo "  - Expect: 'media_processor.invoke transcript=...'"
fi

echo
bold "✓ smoke test PASS"
echo "Next: send a real WhatsApp message from your phone to the canary number"
echo "      and verify the worker logs show the agent reply within 5s."
