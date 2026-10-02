import { useEffect, useRef, useState } from "react";

/**
 * US6 (FR-029): release streamed text at a steady, adaptive rate on
 * requestAnimationFrame so the uneven bursts the socket delivers don't look jittery.
 * Catches up proportionally when far behind, so it never lags noticeably.
 */
export function useSmoothText(target: string, streaming: boolean): string {
  const shownLen = useRef(streaming ? 0 : target.length);
  const [shown, setShown] = useState(streaming ? "" : target);

  useEffect(() => {
    if (!streaming) {
      shownLen.current = target.length;
      setShown(target);
      return;
    }
    // If the target shrank (new turn / reset), restart from the beginning.
    if (shownLen.current > target.length) {
      shownLen.current = 0;
    }
    let raf = 0;
    const tick = () => {
      const backlog = target.length - shownLen.current;
      if (backlog > 0) {
        const step = Math.max(2, Math.ceil(backlog / 15)); // ~2 chars/frame, faster when behind
        shownLen.current = Math.min(target.length, shownLen.current + step);
        setShown(target.slice(0, shownLen.current));
        raf = requestAnimationFrame(tick);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, streaming]);

  return shown;
}
