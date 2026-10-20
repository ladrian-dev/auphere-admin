import * as Notifications from "expo-notifications";

/**
 * The system permission, as three words the screens act on (R10). `denied`
 * means the system will not ask again: only the phone's settings can change it.
 */
export type Permission = "granted" | "denied" | "undetermined";

export function permissionOf(p: Notifications.NotificationPermissionsStatus): Permission {
  const ios = p.ios?.status;
  if (
    p.granted ||
    ios === Notifications.IosAuthorizationStatus.AUTHORIZED ||
    ios === Notifications.IosAuthorizationStatus.PROVISIONAL ||
    ios === Notifications.IosAuthorizationStatus.EPHEMERAL
  ) {
    return "granted";
  }
  return p.canAskAgain ? "undetermined" : "denied";
}

export async function readPermission(): Promise<Permission> {
  return permissionOf(await Notifications.getPermissionsAsync());
}

export async function askPermission(): Promise<Permission> {
  return permissionOf(
    await Notifications.requestPermissionsAsync({ ios: { allowAlert: true, allowBadge: true, allowSound: true } }),
  );
}
