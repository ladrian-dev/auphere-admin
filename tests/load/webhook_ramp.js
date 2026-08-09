// WP-15 — rampa de carga contra el webhook de Meta (staging).
//
// Simula tráfico entrante de WhatsApp con firma HMAC válida: cada request
// es un mensaje de texto de un remitente sintético hacia un canal
// sembrado por scripts/seed_synthetic.py. El ack del webhook debe ser
// <50ms p95 (el turno completo se mide en CloudWatch, no aquí — ver
// README.md: queue_oldest_pending_seconds < 30 durante toda la rampa).
//
// Uso:
//   k6 run tests/load/webhook_ramp.js \
//     -e BASE_URL=http://<alb-dns> \
//     -e META_APP_SECRET=<NEXUS_META_APP_SECRET del secreto de staging> \
//     -e PHONE_NUMBER_ID=+56990000000 \
//     -e TARGET_TPM=1500
//
// Perfil: calentamiento → sostenido a TARGET_TPM 15 min → pico 10x 2 min
// → vuelta al sostenido. Criterio del plan: 1.500 turnos/min sostenidos,
// error rate < 0.5%, webhook ack p95 < 50 ms.
//
// Tres knobs para no tener que editar el fichero (la campaña va por fases
// y cada fase quiere una forma distinta — ver README):
//   PROFILE=smoke     → 1 min a TARGET_TPM, sin pico. Valida el arnés.
//   SUSTAINED_MINUTES → largo del tramo sostenido (default 15).
//   PEAK_MULTIPLIER   → multiplicador del pico; 0 o 1 lo elimina.

import http from "k6/http";
import crypto from "k6/crypto";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const SECRET = __ENV.META_APP_SECRET || "";
const PHONE_NUMBER_ID = __ENV.PHONE_NUMBER_ID || "+56990000000";
const TARGET_TPM = parseInt(__ENV.TARGET_TPM || "1500", 10);

if (!SECRET) {
  throw new Error("META_APP_SECRET es obligatorio — sin firma válida el webhook responde 401.");
}

const TARGET_RPS = Math.ceil(TARGET_TPM / 60);
const PROFILE = __ENV.PROFILE || "full";
const SUSTAINED_MINUTES = parseInt(__ENV.SUSTAINED_MINUTES || "15", 10);
const PEAK_MULTIPLIER = parseInt(__ENV.PEAK_MULTIPLIER || "10", 10);

function stages() {
  if (PROFILE === "smoke") {
    return [
      { duration: "15s", target: TARGET_RPS },
      { duration: "45s", target: TARGET_RPS },
    ];
  }
  const base = [
    { duration: "2m", target: TARGET_RPS }, // calentamiento
    { duration: `${SUSTAINED_MINUTES}m`, target: TARGET_RPS }, // sostenido (criterio del plan)
  ];
  if (PEAK_MULTIPLIER <= 1) {
    return base;
  }
  return base.concat([
    { duration: "1m", target: TARGET_RPS * PEAK_MULTIPLIER }, // subida al pico
    { duration: "2m", target: TARGET_RPS * PEAK_MULTIPLIER }, // pico
    { duration: "2m", target: TARGET_RPS }, // recuperación
  ]);
}

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-arrival-rate",
      startRate: 10,
      timeUnit: "1s",
      preAllocatedVUs: 200,
      maxVUs: 2000,
      stages: stages(),
    },
  },
  thresholds: {
    // Ack del webhook — el SLI de WP-15 (webhook_ack_ms p95 < 50 ms).
    // Umbral k6 a 150 ms porque incluye red cliente→ALB; el ack real
    // servidor se lee del histograma webhook_ack_ms en CloudWatch.
    http_req_duration: ["p(95)<150"],
    http_req_failed: ["rate<0.005"], // error rate < 0.5%
  },
};

function metaPayload(seq) {
  // Mensaje entrante mínimo con la forma del Cloud API v20+. El remitente
  // rota sobre 10k números sintéticos para repartir entre conversaciones.
  const waId = `5698${String(100000 + (seq % 10000))}`;
  const msgId = `wamid.LOAD${seq}.${Date.now()}`;
  return JSON.stringify({
    object: "whatsapp_business_account",
    entry: [
      {
        id: "0",
        changes: [
          {
            field: "messages",
            value: {
              messaging_product: "whatsapp",
              metadata: {
                display_phone_number: PHONE_NUMBER_ID,
                phone_number_id: PHONE_NUMBER_ID,
              },
              contacts: [{ profile: { name: "Load Test" }, wa_id: waId }],
              messages: [
                {
                  from: waId,
                  id: msgId,
                  timestamp: String(Math.floor(Date.now() / 1000)),
                  type: "text",
                  text: { body: `mensaje de carga #${seq} — ¿tienen horas esta semana?` },
                },
              ],
            },
          },
        ],
      },
    ],
  });
}

let seq = 0;

export default function () {
  seq += 1;
  const body = metaPayload(seq * 100000 + __VU);
  const signature = "sha256=" + crypto.hmac("sha256", SECRET, body, "hex");

  const res = http.post(`${BASE_URL}/webhook/meta`, body, {
    headers: {
      "Content-Type": "application/json",
      "X-Hub-Signature-256": signature,
    },
  });

  check(res, {
    "ack 200": (r) => r.status === 200,
  });
}
