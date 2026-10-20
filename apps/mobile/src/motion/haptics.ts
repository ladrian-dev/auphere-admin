import * as Haptics from "expo-haptics";

/**
 * Spec 031, R14.9: a vibration with a meaning, one per case — never on a
 * scroll or a plain navigation. Failures are swallowed: a phone without a
 * vibration motor is not an error.
 */
export const haptics = {
  /** «Tomar el control» landed, a message went out. */
  success: () => void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined),
  /** A send started, a filter changed. */
  light: () => void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => undefined),
  /** Someone else changed the conversation first; a send failed. */
  warning: () => void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => undefined),
};
