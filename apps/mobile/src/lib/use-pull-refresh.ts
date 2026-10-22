import { useState } from "react";

/**
 * Pull to refresh that spins only while the person's own pull is being read
 * (spec 044, first iOS pass). Bound to a query's `isRefetching`, every read in
 * the background — a live event, a write that re-reads — showed the spinner and
 * pushed the large title under the search bar of the Bandeja.
 */
export function usePullRefresh(refetch: () => Promise<unknown>): { refreshing: boolean; onRefresh: () => void } {
  const [refreshing, setRefreshing] = useState(false);
  const onRefresh = () => {
    setRefreshing(true);
    const done = () => setRefreshing(false);
    void refetch().then(done, done); // a failed read says so on the screen; the spinner just stops
  };
  return { refreshing, onRefresh };
}
