import { ImageResponse } from "next/og";

export const alt = "Diagnóstico IA · Amacrux";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background: "linear-gradient(160deg, #01103f 0%, #0a1f63 60%, #01103f 100%)",
          color: "#ffffff",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 28, letterSpacing: 6, fontWeight: 700 }}>
          <div style={{ width: 28, height: 28, borderRadius: 999, background: "#5bdfd2" }} />
          AMACRUX
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ fontSize: 64, fontWeight: 700, lineHeight: 1.05, maxWidth: 980 }}>Descubre dónde puede aportar más valor la IA en tu empresa</div>
          <div style={{ fontSize: 30, color: "#5bdfd2" }}>Diagnóstico gratuito · 2–4 minutos · sin registro</div>
        </div>
      </div>
    ),
    { ...size },
  );
}
