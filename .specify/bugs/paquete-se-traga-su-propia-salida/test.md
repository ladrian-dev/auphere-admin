# Bug Verification: el paquete se traga su propia salida

- **Slug**: paquete-se-traga-su-propia-salida
- **Tested**: 2026-09-15
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: **verified**

## Summary

La aplicación **abre en el Mac Intel** donde v0.1.0 y v0.1.1 salían con código 1 a
los ~290 ms. Y el artefacto publicado confirma que el arreglo sobrevivió a la
cadena: el `app.asar` de x64 pasa de **1.982.761.659 a 68.668.433 bytes**.

**La causa se identificó por eliminación y se confirmó con el arreglo. El
mecanismo interno de Electron no se aisló** — ver Riesgos.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Reproducción tras el arreglo | Instalar v0.1.3 y abrir en el Mac Intel | **pass** | **Lo ejecutó Luis, no yo.** «Ahora sí abrió la app en la pc intel» |
| El artefacto publicado, x64 | Leer la cabecera del asar de `Auphere-0.1.3-mac.zip` en el canal | **pass** | 68.668.433 bytes; `dist/` aporta 659.348 |
| El artefacto publicado, arm64 | Ídem sobre `Auphere-0.1.3-arm64-mac.zip` | **pass** | **68.668.433 — idéntico al de x64** |
| Tests de configuración | `pnpm --filter @nexus/desktop exec vitest run packaging-config` | **pass** | 5/5 |
| Regresión del escritorio | `pnpm --filter @nexus/desktop test` | **pass** | 389/389 |
| Tubería entera | `./scripts/verify.sh` | **pass** | 32 pasos, código 0 |
| Aislar el mecanismo en Electron | — | **not-run** | Ver Riesgos |

## Output Excerpts

```
===== app.asar de a13: 68,668,433 bytes =====
     64,798,993  node_modules/
        659,348  dist/

===== app.asar de x13: 68,668,433 bytes =====
     64,798,993  node_modules/
        659,348  dist/
```

**Que los dos pesen exactamente lo mismo es la prueba.** Antes no podían: el de
x64 se construía después y se llevaba dentro lo que el de arm64 acababa de
dejar en `dist/`.

Comparación con lo publicado en v0.1.0, sobre los mismos artefactos del canal:

| `app.asar` | v0.1.0 arm64 | v0.1.0 x64 | v0.1.3 (ambos) |
|---|---|---|---|
| total | 388.854.240 | 1.982.761.659 | **68.668.433** |
| de eso, `dist/` | 320.766.335 | 2.032.894.001 | **659.348** |

Desaparecen `dist/mac-arm64/`, `builder-debug.yml`, el temporal `dist/ziGLCl5u` y
`dist/.tempc5bkqpqxAuphere-0.1.0-arm64.dmg` — el DMG de 987 MB a medio escribir.

## Residual Risks

**v0.1.3 lleva cuatro arreglos, no uno.** Hay que decirlo. Pero los otros tres no
pueden explicar un arranque que muere a los ~290 ms, antes de `bootstrap()`:

- el del **updater** ocurre después de `whenReady`, y en la máquina de Luis la
  aplicación corría perfectamente con ese aviso en `stderr`;
- el del **mensaje del tope** y el del **banner** son de pantalla, y no se llega a
  pintar ninguna.

**El mecanismo exacto no se aisló.** Por qué un `app.asar` de 1,98 GB hace que el
proceso salga con código 1, en silencio, sin informe de caída y sin imprimir nada
ni con `ELECTRON_ENABLE_LOGGING=1`, sigue sin saberse. Se probó una hipótesis
—que fallara la validación de integridad del asar— y **resultó falsa**: los hashes
de la cabecera declarados en el `Info.plist` coincidían en los dos artefactos
publicados, comprobado uno por uno.

Así que el veredicto honesto es: **resuelto, con la causa identificada por
eliminación y confirmada por el arreglo, sin haber entendido el mecanismo
interno.** Si algún día vuelve a pasar con otro artefacto grande, este informe es
el punto de partida, no la explicación.

**Lo descartado antes de llegar aquí**, todo comprobado en esa máquina: versión de
macOS (26), arquitectura (`x86_64`, binario `Mach-O x86_64`, el `.dmg` correcto),
descarga truncada (pesaba los 1.017.906.539 exactos), Gatekeeper, firma, llavero y
cerrojo de instancia única.

## Lo que este informe cierra, y lo que no

**Cierra el fallo 5** de `docs/bugs-app-escritorio-2026-09-15.md`.

**Responde T021 de la spec 008, de rebote y en verde.** La pregunta era si la
notarización vale fuera de la máquina de Luis. En ese Mac Intel:

```
/Applications/Auphere.app: accepted
source=Notarized Developer ID
origin=Developer ID Application: FACELAD SpA (CBSWMG766P)
/Applications/Auphere.app: valid on disk
/Applications/Auphere.app: satisfies its Designated Requirement
```

**NO cierra T031** (el ciclo de actualización completo). Nadie ha confirmado
todavía que una máquina con 0.1.1 instalada se actualice sola a 0.1.3. Es lo
único que prueba que el arreglo del updater funciona de punta a punta, y sigue
pendiente.

**Tampoco cierra el peso.** `node_modules` es ahora el **94%** del asar
(64.798.993 de 68.668.433), con mapas de fuente y el `storybook-static` de
`@nexus/ui` dentro de una aplicación firmada y notarizada. Es un asunto aparte,
anotado en `fix.md`, y no se tocó.

## Recommendation

**Cerrar el bug.** Verificado en la máquina que lo produjo, con el artefacto
publicado medido y la tubería entera en verde.

Dos seguimientos que no bloquean:

1. **Confirmar T031**: que 0.1.1 → 0.1.3 se actualiza sola. Es la última pieza sin
   verificar de la cadena de la spec 008.
2. **Decidir qué hacer con los 64,8 MB de `node_modules`**, que ahora son casi
   todo el paquete.
