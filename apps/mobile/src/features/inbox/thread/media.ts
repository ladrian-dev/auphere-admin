import { Directory, File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";

import { APP_HEADERS, accessToken } from "@/api/client";
import { API_URL } from "@/config";

/**
 * A file a contact sent (R5.3): fetched with the phone's credential into the
 * app's cache — which the system may clear — and handed to the system's own
 * viewer. Nothing is kept anywhere else.
 */
export function mediaUrl(messageId: string): string {
  return `${API_URL}/console/lite/inbox/messages/${encodeURIComponent(messageId)}/media`;
}

export async function mediaHeaders(): Promise<Record<string, string> | null> {
  const token = await accessToken();
  return token ? { ...APP_HEADERS, Authorization: `Bearer ${token}` } : null;
}

export async function openMedia(messageId: string, mimeType?: string | null): Promise<boolean> {
  const headers = await mediaHeaders();
  if (!headers) return false;
  try {
    const dir = new Directory(Paths.cache, "media");
    if (!dir.exists) dir.create({ intermediates: true });
    const file: File = await File.downloadFileAsync(mediaUrl(messageId), dir, { headers, idempotent: true });
    if (!(await Sharing.isAvailableAsync())) return false;
    await Sharing.shareAsync(file.uri, mimeType ? { mimeType } : undefined);
    return true;
  } catch {
    return false;
  }
}
