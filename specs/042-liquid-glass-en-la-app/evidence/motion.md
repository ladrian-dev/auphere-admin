# El cambio del panel al cuadro, fotograma a fotograma — spec 042 (T059, CE-004)

Grabación del simulador «13 26» (iPhone 13, iOS 26.0.1) con `startRecording`
de Maestro, en la conversación en espera: toque en «Tomar el control» → la
superficie pasa del panel de espera al cuadro de escribir, el cuadro toma el
foco y sube el teclado. `evidence/morph.mp4` (1,6 MB, 30 fps).

Método: `frames.swift` (scratchpad del pase; el mismo del spike S2) muestrea
el vídeo a 30 fps y mide la diferencia media absoluta entre fotogramas
consecutivos sobre una miniatura en gris de 64 × 128 (0–255). Un cambio
continuo es una tanda de deltas pequeños o moderados; un fotograma vacío o un
remontaje es un pico aislado de decenas.

## Lo que se ve (grabación de las 12:12, 2026-10-21)

| Tramo | Fotogramas | Deltas | Qué es |
|---|---|---|---|
| t = 0,600 y 0,733 | 2 sueltos | 3,9 · 3,7 | El toque: el botón pasa a su tono de pulsación y vuelve |
| t = 0,867 – 1,033 | 6 (≈ 200 ms) | 9,1 · 11,7 · 8,5 · 0,2 · 6,8 · 4,4 | **El panel se funde en el cuadro y la superficie encoge** (`durations.state`, 240 ms) |
| t = 1,133 – 1,433 | 10 (≈ 330 ms) | 7,1 → 11,4 → 1,9 (campana) | El teclado sube con la animación del sistema y el cuadro va con él |
| t ≥ 1,467 | — | < 0,5 | Reposo |

- **Ningún fotograma vacío**: el delta más alto es 11,7, en la mitad del
  fundido; un fotograma sin controles o un remontaje habría dado un pico de
  30–60 (como el que descartó el spike cuando la transición iba en un
  envoltorio y el vidrio saltaba).
- **El hilo no salta**: en los fotogramas 027 (t = 0,933) y 032 (t = 1,100)
  las burbujas están en su sitio y nítidas mientras la superficie cambia; el
  separador de la lista sigue a la superficie con `LayoutAnimation` a la
  misma duración.
- El morph en sí dura ~200 ms de los 240 configurados (los últimos fotogramas
  de `Easing.out(cubic)` cambian menos que el umbral); con el teclado, el
  conjunto termina en ~570 ms, dentro del presupuesto de 800 ms de carga de
  página y con una sola orquestación.
- Con «Reducir movimiento» (T072/`floating-surface.test.tsx`): la altura
  cambia sin animar y los hijos solo se funden; no se grabó en vídeo.

## Dónde mirar

- `evidence/morph.mp4` — la grabación entera.
- `scratchpad/cap13/morph-frames/` del pase (no en el repo): los fotogramas
  013–046 en PNG, de donde salen las cifras de arriba.
