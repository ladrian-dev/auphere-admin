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

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-arrival-rate",
      startRate: 10,
      timeUnit: "1s",
      preAllocatedVUs: 200,
      maxVUs: 2000,
      stages: [
        { duration: "2m", target: TARGET_RPS }, // calentamiento
        { duration: "15m", target: TARGET_RPS }, // sostenido (criterio del plan)
        { duration: "1m", target: TARGET_RPS * 10 }, // subida al pico 10x
        { duration: "2m", target: TARGET_RPS * 10 }, // pico
        { duration: "2m", target: TARGET_RPS }, // recuperación
      ],
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
