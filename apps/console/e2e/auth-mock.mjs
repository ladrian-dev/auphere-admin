/**
 * La API simulada de las páginas públicas — spec 066, solo para
 * `auth-entrar.config.ts`.
 *
 * Contesta lo que piden Entrar, Recuperar la cuenta y Contraseña nueva:
 *
 * - Google disponible;
 * - el login siempre falla (aquí no se entra: se mira la pantalla);
 * - pedir el enlace siempre da 202, como la API de verdad (spec 011, R1.3);
 * - canjear un token que empieza por `dead` da 404 y cualquier otro, 200;
 * - el alta (spec 067): pedirla da 202, un token `dead…` es un enlace muerto y
 *   cualquier otro es una solicitud viva de `ana@agencia.com`.
 *
 * Todo lo demás es un 404.
 */
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8712);

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const route = `${req.method} ${url.pathname}`;
  process.stderr.write(`[auth-mock] ${route}\n`);
  if (route === "GET /health") return send(res, 200, { status: "ok" });
  if (route === "GET /console/auth/google/available") return send(res, 200, { available: true });
  if (route === "POST /console/auth/login") return send(res, 401, { detail: "invalid_credentials" });
  if (route === "POST /console/password-reset") return send(res, 202, { status: "sent" });
  if (route === "POST /console/signup") return send(res, 202, { status: "sent" });
  if (url.pathname.startsWith("/console/signup/")) {
    const parts = url.pathname.split("/");
    const token = decodeURIComponent(parts[3] ?? "");
    if (token.startsWith("dead")) return send(res, 404, { detail: "not_found" });
    if (req.method === "GET" && parts.length === 4) {
      return send(res, 200, { email: "ana@agencia.com", provider: null, expires_at: new Date(Date.now() + 86_400_000).toISOString() });
    }
    if (req.method === "POST" && parts[4] === "complete") {
      return send(res, 200, { session_token: "e2e-signup", expires_at: new Date(Date.now() + 3_600_000).toISOString(), partner_slug: "agencia-sol", role: "owner" });
    }
  }
  if (req.method === "POST" && url.pathname.startsWith("/console/password-reset/")) {
    const token = decodeURIComponent(url.pathname.split("/").pop() ?? "");
    return token.startsWith("dead") ? send(res, 404, { detail: "not_found" }) : send(res, 200, { status: "reset" });
  }
  return send(res, 404, { detail: "not_found" });
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[auth-mock] listening on ${PORT}\n`));
