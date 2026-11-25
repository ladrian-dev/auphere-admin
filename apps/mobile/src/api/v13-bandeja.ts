import { API_URL } from "@/config";

import { APP_HEADERS, accessToken, api, call } from "./client";
import type { ConversationPage, Detail, InboxFilter } from "./endpoints";
import type { components } from "./schema.gen";

/**
 * The Bandeja's calls that spec 069 adds (Requisitos 9–12), all routes that
 * already exist in `openapi.json` (the API does not change):
 *
 * - the list filtered by channel (`channel`, 87b7c4cc);
 * - «Vaciar chat» (`/clear`) and «Eliminar chat» (`/archive`, 056 R16);
 * - the post a comment was left on (`/messages/{id}/post`, 049 R4);
 * - the contact's photo (`/avatar`), streamed with the phone's credential.
 *
 * `endpoints.ts` is shared and stays as it is; these live here.
 */
type S = components["schemas"];
export type ChannelType = S["ChannelType"];
export type CommentPost = S["CommentPostOut"];

const C = "/console/lite/inbox/conversations/{conversation_id}" as const;
const path = (id: string) => ({ path: { conversation_id: id } });

export const bandejaApi = {
  /** `GET …/conversations` with what the shared call does not send: the channel. */
  conversations: (q: { filter: InboxFilter; q?: string; agent?: string | null; channel?: ChannelType | null; cursor?: string | null }) =>
    call(
      api.GET("/console/lite/inbox/conversations", {
        params: {
          query: {
            filter: q.filter,
            ...(q.q ? { q: q.q } : {}),
            ...(q.agent ? { agent: q.agent } : {}),
            ...(q.channel ? { channel: q.channel } : {}),
            ...(q.cursor ? { cursor: q.cursor } : {}),
          },
        },
      }),
    ) as Promise<ConversationPage>,
  /** «Vaciar chat»: empty for the Bandeja and for the agent, not erased. Answers the conversation as it is now. */
  clear: (id: string) => call(api.POST(`${C}/clear`, { params: path(id) })) as Promise<Detail>,
  /** «Eliminar chat»: out of the Bandeja, archived rather than erased. 204; from then on the conversation is a 404. */
  archive: (id: string) => call(api.POST(`${C}/archive`, { params: path(id) })),
  /** The post of a comment; `null` when Meta does not give it (the comment still reads on its own). */
  post: (id: string, messageId: string) =>
    call(api.GET(`${C}/messages/{message_id}/post`, { params: { path: { conversation_id: id, message_id: messageId } } })) as Promise<CommentPost | null>,
};

/** The contact's photo: the API streams it (RLS decides whose it is); no storage link reaches the phone. */
export function avatarUrl(conversationId: string): string {
  return `${API_URL}/console/lite/inbox/conversations/${encodeURIComponent(conversationId)}/avatar`;
}

/** The phone's credential as headers, for an image the API streams (expo-image cannot use the typed client). */
export async function credentialHeaders(): Promise<Record<string, string> | null> {
  const token = await accessToken();
  return token ? { ...APP_HEADERS, Authorization: `Bearer ${token}` } : null;
}
