import Animated, { type SharedValue } from "react-native-reanimated";

import type { SavedReply } from "@/api/endpoints";
import type { T } from "@/i18n/t";
import { useMotion } from "@/motion/use-motion";
import { FloatingSurface } from "@/ui/floating-surface";

import type { ComposerMode } from "../model";
import { Composer } from "./composer";
import { ControlCard } from "./control";
import { FOOT_RADIUS } from "./foot-radius";

/**
 * The foot of a conversation (spec 042, R2.1–R2.9): one surface, floating over
 * the thread, whose content is what the person can do now — why it waits and
 * «Tomar el control», who answers, «Reabrir», or the box. Taking control
 * changes the children; the surface stays and animates its height (D24's one
 * choreography, on glass). With «Reducir movimiento» the children only fade.
 */
export function ThreadFoot({
  mode,
  busy,
  online,
  t,
  replies,
  focusSignal,
  onTakeOver,
  onGiveBack,
  onReopen,
  onReadMore,
  onSend,
  onAttach,
  onReplies,
  clearance,
  onClearance,
  bottomInset = 0,
}: {
  mode: ComposerMode;
  busy: boolean;
  online: boolean;
  t: T;
  replies: SavedReply[] | null;
  focusSignal: number;
  onTakeOver: () => void;
  onGiveBack: () => void;
  onReopen: () => void;
  /** The agent's reason, whole, when two lines are not enough (R2.4). */
  onReadMore: () => void;
  onSend: (text: string) => void;
  onAttach: () => void;
  onReplies: (insert: (body: string) => void) => void;
  clearance?: SharedValue<number>;
  /** The clearance as a number each time it settles (see `FloatingSurface`). */
  onClearance?: (px: number) => void;
  bottomInset?: number;
}) {
  const motion = useMotion();
  return (
    <FloatingSurface
      tone={mode.kind === "waiting" ? "warning" : "neutral"}
      radius={FOOT_RADIUS}
      bottomInset={bottomInset}
      clearance={clearance}
      onClearance={onClearance}
      testID="thread-surface"
    >
      {mode.kind === "mine" ? (
        <Animated.View key="mine" entering={motion.enter} exiting={motion.exit}>
          <Composer
            mode={mode}
            online={online}
            focusSignal={focusSignal}
            replies={replies}
            t={t}
            onSend={onSend}
            onAttach={onAttach}
            onReplies={onReplies}
            onGiveBack={mode.blocked === null ? onGiveBack : undefined}
          />
        </Animated.View>
      ) : (
        <Animated.View key={`control-${mode.kind}`} entering={motion.enter} exiting={motion.exit}>
          <ControlCard mode={mode} busy={busy} online={online} t={t} onTakeOver={onTakeOver} onGiveBack={onGiveBack} onReopen={onReopen} onReadMore={onReadMore} />
        </Animated.View>
      )}
    </FloatingSurface>
  );
}
