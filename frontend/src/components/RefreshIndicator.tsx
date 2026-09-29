import { useEffect, useState } from "react";

interface RefreshIndicatorProps {
  lastRefreshAt: number;
}

// Isolated into its own component so its once-a-second tick re-renders only this small line of
// text, not the whole results tree SearchPage owns (spec 0007's counter is purely cosmetic).
export function RefreshIndicator({ lastRefreshAt }: RefreshIndicatorProps) {
  const [, forceTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const seconds = Math.max(0, Math.floor((Date.now() - lastRefreshAt) / 1000));
  return <p className="shrink-0 text-xs text-slate-400 dark:text-slate-500">last refresh {seconds}s ago</p>;
}
