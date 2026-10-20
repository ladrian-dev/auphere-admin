# Idea Intake: spike S1 — el esqueleto de Expo SDK 58 (spec 031)

- **Slug**: 031-s1-esqueleto-expo-58
- **Created**: 2026-10-20
- **Source**: tarea T002 de `specs/031-auphere-customers-movil/tasks.md`
  (research D12, D23)
- **Type**: spike (no se fusiona como tal: lo que sobrevive entra por las
  tareas de la spec)

## La pregunta

¿Aguanta Expo SDK 58 (React Native 0.88, React 19.3) todo lo que la spec 031
da por hecho, o hay que bajar a 57.0.30?

1. El SDK 58 instala y compila en un workspace de pnpm anidado.
2. La vuelta de `expo-web-browser` por esquema propio (la universal se aplazó).
3. `expo-secure-store` con `WHEN_UNLOCKED_THIS_DEVICE_ONLY`.
4. Un aviso real de APNs `time-sensitive` y otro de FCM a un canal privado.
5. `NativeTabs` con `hidden` y el remontaje al cambiar los módulos.
6. Una animación de reanimated 4 en el hilo de UI.
7. `eas build` desde el workspace anidado.

## Restricción de la sesión

No hubo dispositivo físico ni simulador: Xcode local es 26.0.1 (el SDK 58 pide
26.4+) y el disco se quedó sin espacio a mitad del build de Android (177 MB
libres). Las comprobaciones 2–7 en dispositivo quedan pendientes y anotadas en
la decisión.
