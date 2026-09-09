#!/usr/bin/env bash
# T004 — construye la rueda del sustrato desde el commit fijado.
#
# No existe rueda pública: PyPI da 404 para `kirocrew` y los releases del proyecto
# publican solo bundles de escritorio. Así que la construimos nosotros, y por eso
# esto es cadena de suministro del paquete firmado y no una línea de dependencias.
#
# El clon NUNCA se toca: se exporta el commit con `git archive` a un directorio
# aparte y se construye desde esa copia. Un `pip install -e` sobre el clon dejaría
# artefactos dentro y rompería la comprobación de "0 archivos modificados".
set -euo pipefail

PINNED="${NEXUS_SUBSTRATE_COMMIT:-37933a5}"
CLONE="${NEXUS_SUBSTRATE_CLONE:-$HOME/Workspace/_oss-research/kirocrew}"
OUT="${1:-$(cd "$(dirname "$0")/.." && pwd)/build}"

[ -d "$CLONE/.git" ] || { echo "no hay clon del sustrato en $CLONE (fija NEXUS_SUBSTRATE_CLONE)" >&2; exit 2; }

before="$(git -C "$CLONE" rev-parse HEAD)"
rm -rf "$OUT/src" "$OUT/dist"
mkdir -p "$OUT/src" "$OUT/dist"
git -C "$CLONE" archive "$PINNED" | tar -x -C "$OUT/src"
uv build --wheel --out-dir "$OUT/dist" "$OUT/src" >"$OUT/build.log" 2>&1

# La comprobación que separa componer de forkear.
after="$(git -C "$CLONE" rev-parse HEAD)"
dirty="$(git -C "$CLONE" status --porcelain | wc -l | tr -d ' ')"
[ "$before" = "$after" ] || { echo "el clon cambió de HEAD durante el build" >&2; exit 1; }
[ "$dirty" = "0" ] || { echo "el clon quedó con $dirty ficheros modificados: eso es un fork, no una composición" >&2; exit 1; }

echo "rueda: $(ls "$OUT"/dist/*.whl)"
echo "clon intacto en $PINNED, 0 modificados"
