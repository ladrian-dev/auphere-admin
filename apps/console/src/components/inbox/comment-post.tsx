"use client";

import * as React from "react";

import { useT } from "@/i18n/client";
import type { ActionResult } from "@/lib/actions";
import type { InboxCommentPost } from "@/lib/backend/inbox";

export type LoadCommentPost = (messageId: string) => Promise<ActionResult<InboxCommentPost | null>>;

/**
 * The post a comment was left on, above the comment. If Meta does not give it,
 * nothing shows and the comment still reads on its own. Its picture is decorative:
 * the caption and the link say what it is.
 */
export function CommentPost({ messageId, load }: { messageId: string; load: LoadCommentPost }) {
  const t = useT();
  const [post, setPost] = React.useState<InboxCommentPost | null>(null);
  const [broken, setBroken] = React.useState(false);

  React.useEffect(() => {
    let live = true;
    void load(messageId).then((r) => {
      if (live && r.ok) setPost(r.data);
    });
    return () => {
      live = false;
    };
  }, [messageId, load]);

  if (!post) return null;
  return (
    <div data-slot="comment-post" className="flex w-full max-w-sm min-w-0 gap-3 rounded-md border border-border-soft bg-card p-2">
      {post.image_url && !broken ? (
        // eslint-disable-next-line @next/next/no-img-element -- Meta's own CDN; the address changes and expires
        <img
          src={post.image_url}
          alt=""
          aria-hidden="true"
          loading="lazy"
          onError={() => setBroken(true)}
          className="size-14 shrink-0 rounded-sm bg-muted object-cover"
        />
      ) : null}
      <div className="flex min-w-0 flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">{t("inbox.comment.on")}</span>
        {post.text ? <p className="line-clamp-2 text-xs text-pretty">{post.text}</p> : null}
        {post.permalink ? (
          <a href={post.permalink} target="_blank" rel="noreferrer" className="text-xs font-medium text-primary-text underline">
            {t("inbox.comment.open")}
          </a>
        ) : null}
      </div>
    </div>
  );
}
