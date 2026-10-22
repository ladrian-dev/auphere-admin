import { useEffect, useState } from "react";

/**
 * The phone's clock in ms, moving every `every` ms: for «hace N min» and
 * countdowns (spec 044). `notBefore` is when the data being counted arrived:
 * between ticks the clock would be older than it, and an offer made just now
 * would count down from «16 min» (first iOS pass).
 */
export function useNowMs(every = 30_000, notBefore = 0): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), every);
    return () => clearInterval(id);
  }, [every]);
  return Math.max(now, notBefore);
}
