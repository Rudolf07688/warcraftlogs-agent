import { useEffect, useRef, useState } from "react";

// PERF-010: re-render (and so re-parse the markdown) at most ~30 times a second.
const FRAME_MS = 33;

/**
 * US6 (FR-029): release streamed text at a steady, adaptive rate on
 * requestAnimationFrame so the uneven bursts the socket delivers don't look jittery.
 * Catches up proportionally when far behind, so it never lags noticeably.
 *
 * One animation loop runs for the whole stream (it reads the latest target from a ref)
 * instead of restarting on every token, and commits at most every FRAME_MS.
 */
export function useSmoothText(target: string, streaming: boolean): string {
  const shownLen = useRef(streaming ? 0 : target.length);
  const targetRef = useRef(target);
  targetRef.current = target;
  const [shown, setShown] = useState(streaming ? "" : target);

  useEffect(() => {
    if (!streaming) {
      shownLen.current = target.length;
      setShown(target);
      return;
    }
    let raf = 0;
    let last = 0;
    const tick = (now: number) => {
      const latest = targetRef.current;
      // If the target shrank (new turn / reset), restart from the beginning.
      if (shownLen.current > latest.length) shownLen.current = 0;
      const backlog = latest.length - shownLen.current;
      if (backlog > 0 && now - last >= FRAME_MS) {
        const step = Math.max(4, Math.ceil(backlog / 8)); // ~4 chars/commit, faster when behind
        shownLen.current = Math.min(latest.length, shownLen.current + step);
        setShown(latest.slice(0, shownLen.current));
        last = now;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // While streaming, the loop reads the target from a ref, so it isn't a dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streaming, streaming ? null : target]);

  return shown;
}
