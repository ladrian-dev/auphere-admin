import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PROFILE_A } from "@/domain/__tests__/fixtures";

const sendMock = vi.fn();
vi.mock("resend", () => ({
  Resend: class {
    emails = { send: sendMock };
  },
}));

import { POST, _resetForTests } from "../route";

const snapshot = {
  scoreTotal: 61, range: "oportunidad_prioritaria", leadTier: "caliente",
  segment: { profile: "decisor_negocio", maturity: "inicial", opportunityCategories: ["automatizacion_operativa"], intent: "media", complexity: "quick_win" },
  recommendationIds: ["clasificacion-solicitudes", "recordatorios-y-seguimiento", "asistente-interno-conocimiento"],
};
const lead = (over: Record<string, unknown> = {}) => ({
  name: "Ana Pérez", company: "Farmacia Central", email: "ana@farmacia.com", role: "Gerente",
  interest: "automatizacion_operativa", consentContact: true, consentMarketing: false,
  resultSnapshot: snapshot, answers: PROFILE_A, campaign: "ia-empresas-2026", idempotencyKey: crypto.randomUUID(), fax: "", ...over,
});
const post = (body: unknown, ip = "1.1.1.1") =>
  POST(new Request("http://localhost/api/leads", { method: "POST", headers: { "content-type": "application/json", "x-forwarded-for": ip }, body: JSON.stringify(body) }));

const env = process.env;
beforeEach(() => {
  _resetForTests();
  sendMock.mockReset();
  process.env = { ...env, NEXT_PUBLIC_DEMO_MODE: "false", RESEND_API_KEY: "re_test", LEADS_TO: "leads@amacrux.test", LEADS_FROM: "Diagnostico <d@amacrux.test>" };
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => {
  process.env = env;
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("POST /api/leads", () => {
  it("entrega por Resend y responde 200", async () => {
    sendMock.mockResolvedValue({ data: { id: "email_1" }, error: null });
    const res = await post(lead());
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true, delivered: true, id: "email_1" });
    expect(sendMock).toHaveBeenCalledTimes(1);
    const arg = sendMock.mock.calls[0]![0];
    expect(arg.to).toEqual(["leads@amacrux.test"]);
    expect(arg.subject).toMatch(/Farmacia Central/);
    expect(arg.text).toMatch(/ana@farmacia.com/);
    expect(arg.text).toMatch(/caliente/i);
  });

  it("modo demo sin clave: 200 sin entregar", async () => {
    delete process.env.RESEND_API_KEY;
    const res = await post(lead());
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true, delivered: false, mode: "demo" });
    expect(sendMock).not.toHaveBeenCalled();
  });

  it("misma clave de idempotencia: no reenvía", async () => {
    sendMock.mockResolvedValue({ data: { id: "email_1" }, error: null });
    const body = lead();
    await post(body);
    const res = await post(body);
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true, delivered: true, duplicate: true });
    expect(sendMock).toHaveBeenCalledTimes(1);
  });

  it("honeypot relleno: éxito falso sin enviar", async () => {
    const res = await post(lead({ fax: "bot" }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
    expect(sendMock).not.toHaveBeenCalled();
  });

  it("payload inválido: 400 con campos", async () => {
    const res = await post(lead({ email: "no", consentContact: false }));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBe("invalid");
    expect(Object.keys(body.fields)).toEqual(expect.arrayContaining(["email", "consentContact"]));
  });

  it("JSON roto: 400", async () => {
    const res = await POST(new Request("http://localhost/api/leads", { method: "POST", headers: { "x-forwarded-for": "9.9.9.9" }, body: "{" }));
    expect(res.status).toBe(400);
  });

  // En un evento todos salen por el NAT del recinto: el límite tiene que dar
  // para la sala entera, no para cinco personas.
  it("rate limit: aguanta 60 envíos de la misma IP y corta en el 61", async () => {
    sendMock.mockResolvedValue({ data: { id: "x" }, error: null });
    for (let i = 0; i < 60; i++) expect((await post(lead(), "2.2.2.2")).status).toBe(200);
    expect((await post(lead(), "2.2.2.2")).status).toBe(429);
    expect((await post(lead(), "3.3.3.3")).status).toBe(200);
  });

  it("fallo de Resend: 502 reintentable y no cachea", async () => {
    sendMock.mockResolvedValueOnce({ data: null, error: { message: "boom" } }).mockResolvedValueOnce({ data: { id: "ok" }, error: null });
    const body = lead();
    expect((await post(body)).status).toBe(502);
    expect((await post(body)).status).toBe(200);
  });

  it("configuración parcial: 503", async () => {
    delete process.env.LEADS_TO;
    expect((await post(lead())).status).toBe(503);
  });

  // Un despliegue sin variables no puede fingir que entregó: se cae y se ve.
  it("en producción, sin destinos y sin bandera de demo: 503", async () => {
    delete process.env.RESEND_API_KEY;
    vi.stubEnv("NODE_ENV", "production");
    const res = await post(lead());
    expect(res.status).toBe(503);
    expect(await res.json()).toMatchObject({ error: "unavailable" });
    expect(sendMock).not.toHaveBeenCalled();
  });

  it("en producción con la bandera explícita: modo demo", async () => {
    delete process.env.RESEND_API_KEY;
    vi.stubEnv("NODE_ENV", "production");
    process.env.NEXT_PUBLIC_DEMO_MODE = "true";
    expect(await (await post(lead())).json()).toMatchObject({ ok: true, mode: "demo" });
  });

  it("los logs no contienen datos personales", async () => {
    sendMock.mockResolvedValue({ data: { id: "x" }, error: null });
    await post(lead());
    const logged = JSON.stringify([...(console.info as unknown as { mock: { calls: unknown[] } }).mock.calls, ...(console.error as unknown as { mock: { calls: unknown[] } }).mock.calls]);
    expect(logged).not.toMatch(/ana@farmacia.com|Ana Pérez|Farmacia Central/);
  });
});

describe("POST /api/leads con Supabase", () => {
  const withStorage = () => {
    process.env.SUPABASE_URL = "https://xyz.supabase.co";
    process.env.SUPABASE_SERVICE_ROLE_KEY = "service-key";
  };
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("guarda en Supabase y envía el correo a varias direcciones", async () => {
    withStorage();
    process.env.LEADS_TO = "amacrux@test.com, auphere@test.com";
    fetchMock.mockResolvedValue(new Response(null, { status: 201 }));
    sendMock.mockResolvedValue({ data: { id: "email_1" }, error: null });
    const res = await post(lead());
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true, stored: true, delivered: true, mode: "live" });
    expect(fetchMock.mock.calls[0]![0]).toBe("https://xyz.supabase.co/rest/v1/leads");
    expect(sendMock.mock.calls[0]![0].to).toEqual(["amacrux@test.com", "auphere@test.com"]);
    // PATCH best-effort con el id del correo
    expect(fetchMock.mock.calls[1]![0]).toContain("idempotency_key=eq.");
  });

  it("si Supabase falla pero el correo sale, responde 200 con stored:false", async () => {
    withStorage();
    fetchMock.mockRejectedValue(new Error("down"));
    sendMock.mockResolvedValue({ data: { id: "email_1" }, error: null });
    const res = await post(lead());
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true, stored: false, delivered: true });
  });

  it("si fallan todos los destinos configurados responde 502", async () => {
    withStorage();
    fetchMock.mockResolvedValue(new Response("nope", { status: 500 }));
    sendMock.mockResolvedValue({ data: null, error: { message: "boom" } });
    expect((await post(lead())).status).toBe(502);
  });

  it("solo Supabase configurado (sin Resend): guarda y responde live sin correo", async () => {
    withStorage();
    delete process.env.RESEND_API_KEY;
    fetchMock.mockResolvedValue(new Response(null, { status: 201 }));
    const res = await post(lead());
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true, stored: true, delivered: false, mode: "live" });
    expect(sendMock).not.toHaveBeenCalled();
  });

  it("duplicado por idempotencia no vuelve a insertar", async () => {
    withStorage();
    fetchMock.mockResolvedValue(new Response(null, { status: 201 }));
    sendMock.mockResolvedValue({ data: { id: "email_1" }, error: null });
    const body = lead();
    await post(body);
    const inserts = fetchMock.mock.calls.filter((c) => (c[1] as RequestInit).method === "POST").length;
    await post(body);
    expect(fetchMock.mock.calls.filter((c) => (c[1] as RequestInit).method === "POST").length).toBe(inserts);
  });

  it("en modo demo no llama a Supabase ni a Resend", async () => {
    withStorage();
    process.env.NEXT_PUBLIC_DEMO_MODE = "true";
    const res = await post(lead());
    expect(await res.json()).toMatchObject({ ok: true, stored: false, delivered: false, mode: "demo" });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(sendMock).not.toHaveBeenCalled();
  });

  it("los logs no contienen datos personales tampoco con Supabase", async () => {
    withStorage();
    fetchMock.mockRejectedValue(new Error("down"));
    sendMock.mockResolvedValue({ data: { id: "x" }, error: null });
    await post(lead());
    const logged = JSON.stringify([...(console.info as unknown as { mock: { calls: unknown[] } }).mock.calls, ...(console.error as unknown as { mock: { calls: unknown[] } }).mock.calls]);
    expect(logged).not.toMatch(/ana@farmacia.com|Ana Pérez|Farmacia Central|service-key/);
  });
});

describe("POST /api/leads con webhook de hoja de cálculo", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    process.env.LEADS_WEBHOOK_URL = "https://n8n.test/webhook/leads";
    process.env.LEADS_WEBHOOK_SECRET = "s3cret";
  });
  afterEach(() => vi.unstubAllGlobals());

  it("envía la copia al webhook y no bloquea si falla", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 200 }));
    sendMock.mockResolvedValue({ data: { id: "email_1" }, error: null });
    const res = await post(lead());
    expect(await res.json()).toMatchObject({ ok: true, delivered: true, sheet: true });
    expect(fetchMock.mock.calls[0]![0]).toBe("https://n8n.test/webhook/leads");

    fetchMock.mockRejectedValueOnce(new Error("down"));
    const res2 = await post(lead());
    expect(res2.status).toBe(200);
    expect(await res2.json()).toMatchObject({ ok: true, delivered: true, sheet: false });
  });
});
