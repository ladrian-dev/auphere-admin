/**
 * Public surface of ``@nexus/ucm-render-web``.
 *
 * Host pattern:
 *   import { UCMRenderer } from "@nexus/ucm-render-web";
 *   <UCMRenderer ucm={msg} onInteractive={(e) => sendBack(e)} />
 *
 * To override a specific type, render one of the named components
 * directly instead of going through ``UCMRenderer``.
 */
export { UCMRenderer } from "./UCMRenderer";

export { Text } from "./components/Text";
export { QuickReplies } from "./components/QuickReplies";
export { List } from "./components/List";
export { CtaUrl } from "./components/CtaUrl";
export { Media } from "./components/Media";
export { Location } from "./components/Location";
export { Flow } from "./components/Flow";
export { Composite } from "./components/Composite";

export type {
  InteractiveResponse,
  OnInteractiveResponse,
  UCMComponentProps,
  UCMMessage,
} from "./types";

export { tokens } from "./tokens";
