import * as Haptics from "expo-haptics";

/**
 * Spec 031, R14.9: a vibration with a meaning, one per case — never on a
 * scroll or a plain navigation. Failures are swallowed: a phone without a
 * vibration motor is not an error (and neither is a missing method).
 */
function safely(fire: () => Promise<void> | undefined): void {
  try {
    void Promise.resolve(fire()).catch(() => undefined);
  } catch {
    // No motor, no module: nothing to do.
  }
}

export const haptics = {
  /** A choice changed: a chip, a segment, a switch, a tab (spec 069, R2.6: the design's «select»). */
  select: () => safely(() => Haptics.selectionAsync?.()),
  /** «Tomar el control» landed, a message went out. */
  success: () => safely(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)),
  /** A send started, a filter changed. */
  light: () => safely(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)),
  /** Someone else changed the conversation first; a send failed. */
  warning: () => safely(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)),
};
