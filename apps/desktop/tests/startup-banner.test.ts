import { describe, expect, it } from "vitest";

import { describeEnvironment } from "../src/startup-banner.js";

/**
 * Contra qué habla la aplicación — spec 009, tras un tropiezo real.
 *
 * El 2026-09-15 se probó el inicio de sesión con Google **contra producción
 * creyendo que era staging**, porque la aplicación no dice en ningún sitio a
 * dónde apunta. El síntoma —«entro en la web y la app no se entera»— era
 * idéntico al de un fallo de código, y costó una ronda entera descartarlo.
 *
 * Esto es un módulo puro y no un `console.info` suelto porque **la decisión de
 * qué entorno es** puede equivocarse en silencio, y entonces el aviso miente,
 * que es peor que no tenerlo.
 */
describe("decir contra qué entorno se habla", () => {
  it("nombra producción", () => {
    const s = describeEnvironment("https://console.auphere.com", "https://api.auphere.com");
    expect(s).toMatch(/producci/i);
  });

  it("nombra staging", () => {
    const s = describeEnvironment(
      "https://console.staging.auphere.com",
      "https://api.staging.auphere.com",
    );
    expect(s).toMatch(/staging/i);
    expect(s).not.toMatch(/producci/i);
  });

  it("dice las URLs enteras, no sólo la etiqueta", () => {
    // El nombre del entorno ayuda; la URL es lo que se compara con la barra del
    // navegador cuando algo no cuadra.
    const s = describeEnvironment("https://console.staging.auphere.com", "https://api.x.test");
    expect(s).toContain("https://console.staging.auphere.com");
    expect(s).toContain("https://api.x.test");
  });

  it("avisa cuando la consola y la API no son del mismo entorno", () => {
    // Mezclar staging y producción es el error más caro de diagnosticar: el
    // login sale bien y el canje falla contra otra base de datos.
    const s = describeEnvironment("https://console.staging.auphere.com", "https://api.auphere.com");
    expect(s).toMatch(/mezcl|distinto/i);
  });

  it("no pretende saber qué es un dominio que no conoce", () => {
    const s = describeEnvironment("http://localhost:3000", "http://localhost:8000");
    expect(s).not.toMatch(/producci|staging/i);
  });
});
