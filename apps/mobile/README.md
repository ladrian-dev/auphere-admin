# Auphere Customers

La Consola Lite en el teléfono, para las personas de los negocios que atiende
Auphere (spec [031](../../specs/031-auphere-customers-movil/spec.md)). Lo que
hace, cómo entra, cómo avisa y cómo se publica: [docs/app-movil.md](../../docs/app-movil.md).

Expo SDK 58 en **su propio workspace de pnpm**: todo se ejecuta desde esta
carpeta, nunca desde la raíz del monorepo.

```bash
pnpm install              # con el pnpm fijado en package.json (10.15.0)
pnpm android              # build de desarrollo en el emulador (necesita la pila local)
pnpm ios                  # ídem en el simulador (Xcode 26.4 o posterior)
pnpm start                # Metro para un build de desarrollo ya instalado
pnpm verify               # tsc + eslint + jest + generados al día
pnpm gen                  # regenerar tipos, tokens y textos desde sus fuentes
```

Sin `EXPO_PUBLIC_API_URL` ni `EXPO_PUBLIC_CONSOLE_URL`, un build de desarrollo
habla con la máquina donde se compiló (`.env.example`). Los flujos de Maestro
están en `e2e/`.
