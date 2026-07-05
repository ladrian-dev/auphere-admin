# @auphere/embed

Send WhatsApp template broadcasts from **your own product**, powered by
[Auphere](https://auphere.com). This SDK is a thin loader: it mounts a
secure Auphere iframe and hands it a short-lived session token. Your
bundle never contains Auphere or WhatsApp credentials, and the modal UI
updates without you redeploying.

## Install

```bash
npm install @auphere/embed
```

## 1. Mint session tokens in YOUR backend

Your secret API key (`ak_live_…`) must never reach the browser. Expose a
tiny endpoint that exchanges it for a short-lived widget session:

```ts
// e.g. app/api/auphere/session/route.ts (Next.js)
export async function POST() {
  const response = await fetch("https://api.auphere.com/v1/widget-sessions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.AUPHERE_SECRET_KEY}`,
      "Content-Type": "application/json",
    },
    // your OWN id for the signed-in client (tenant mapping is automatic)
    body: JSON.stringify({ external_client_ref: currentClient.id }),
  });
  return Response.json(await response.json());
}
```

> The endpoint is called on open **and again ~every 15 minutes** while a
> modal is open, so it must work without user interaction.

Register your client once (idempotent) with
`POST /v1/partners/clients { external_client_ref, name }`.

## 2. Create the client

```ts
import { createAuphere } from "@auphere/embed";

const auphere = createAuphere({
  partnerSlug: "acme", // shown in your Auphere dashboard
  fetchSession: async () =>
    (await fetch("/api/auphere/session", { method: "POST" })).json(),
  appearance: { colorPrimary: "#25D366", radius: "8px" },
  locale: "es",
});
```

## 3a. Broadcast button (React)

The button renders **only when the client's WhatsApp is connected**:

```tsx
import { AuphereBroadcastButton } from "@auphere/embed/react";

<AuphereBroadcastButton
  auphere={auphere}
  recipients={[
    { phone: "+56912345678", variables: { cliente: "Ana", saldo_pendiente: "$12.000" } },
    { phone: "+56987654321", variables: { cliente: "Luis", saldo_pendiente: "$8.000" } },
  ]}
  className="your-button-class"
  onDone={({ broadcastId, accepted }) => console.log(broadcastId, accepted)}
>
  Campañas WhatsApp
</AuphereBroadcastButton>;
```

`variables` keys must match the template's **named parameters** — you
map your schema to them in your backend. Recipients always come from
your data; the modal previews and sends, it never invents an audience.

## 3b. Vanilla JS

```ts
auphere.getStatus();                    // "connected" | "not_connected" | "unknown"
auphere.onStatusChange((s) => { ... }); // subscription

await auphere.openBroadcast({ recipients });
```

## 4. Connect WhatsApp (self-serve signup)

Call it from your settings/onboarding page — it opens Meta's Embedded
Signup inside the Auphere iframe:

```ts
await auphere.connectWhatsApp({
  onConnected: ({ displayPhoneNumber }) => refreshUI(),
});
```

## Security model (short version)

- Your secret key lives only in your backend; the browser only ever
  holds a 15-minute JWT scoped to one client.
- The modal runs on `embed.auphere.com`, isolated from your page's JS.
- Tokens travel via `postMessage` with strict origin checks — never in
  URLs or cookies.
- Allowed embedding origins are configured per API key in the Auphere
  dashboard; other origins are blocked by CSP.

## Content-Security-Policy

If your site sets a CSP, allow:

```
frame-src https://embed.auphere.com;
```
