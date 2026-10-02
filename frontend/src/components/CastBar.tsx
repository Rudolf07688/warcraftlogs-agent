// US6 cast bar: indeterminate (creeps toward 90%) until the tool resolves, then
// snaps to 100%. A determinate value (0–1) drives it directly when available.
import { useEffect } from "react";
import { motion, useAnimate, useReducedMotion } from "motion/react";

export function CastBar({
  hue,
  done,
  progress,
}: {
  hue: string;
  done: boolean;
  progress?: number;
}) {
  const [scope, animate] = useAnimate();
  const reduced = useReducedMotion();

  useEffect(() => {
    if (!scope.current) return;
    if (done) {
      animate(scope.current, { scaleX: 1 }, { duration: 0.18, ease: "easeOut" });
    } else if (progress != null) {
      animate(scope.current, { scaleX: Math.max(0, Math.min(1, progress)) }, { duration: 0.3 });
    } else if (reduced) {
      animate(scope.current, { scaleX: 0.6 }, { duration: 0 });
    } else {
      animate(scope.current, { scaleX: 0.9 }, { duration: 8, ease: [0.1, 0.6, 0.3, 1] });
    }
  }, [done, progress, reduced, animate, scope]);

  return (
    <div className="cast-bar">
      <motion.div
        ref={scope}
        className="cast-bar-fill"
        initial={{ scaleX: 0 }}
        style={{ background: hue, boxShadow: `0 0 12px ${hue}` }}
      />
      {!done && !reduced && <div className="cast-bar-sheen" />}
    </div>
  );
}
