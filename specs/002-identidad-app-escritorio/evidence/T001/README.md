# T001 — spike: `BaseWindow` + dos `WebContentsView`

`spike.mjs` se ejecuta con el Electron de `apps/desktop`
(`./node_modules/.bin/electron spike.mjs`) y escribe `result.json` y dos capturas.

Resultado del 2026-09-09: `ok: true`. La vista de la consola no tiene `preload` y
`window.auphere` no existe en ella; la barra sí lo tiene y responde `pong`; las
particiones `persist:auphere-console` / `auphere-bar` / `auphere-agent` son
distintas y solo la primera persiste.
