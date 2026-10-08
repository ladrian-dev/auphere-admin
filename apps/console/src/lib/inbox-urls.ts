/**
 * Browser-side paths of the Inbox (spec 030): the BFF route handlers. Their
 * own module — pure strings, no server imports — because Client Components
 * use them and `lib/backend` is server-only.
 */
export const inboxMediaUrl = (messageId: string) => `/api/lite/inbox/media/${encodeURIComponent(messageId)}`;
export const inboxStreamUrl = "/api/lite/inbox/stream";
export const inboxAttachmentUrl = (conversationId: string) =>
  `/api/lite/inbox/attachments/${encodeURIComponent(conversationId)}`;
