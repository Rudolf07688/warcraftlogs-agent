// US6 ambient world: slow drifting blurred gradients + grain/vignette (CSS, cheap)
// plus a capped particle field. Particles and drift are disabled under reduced motion
// (FR-034); the engine pauses itself when the tab is hidden (SC-010) and while a reply
// streams (PERF-010).
import { lazy, memo, Suspense } from "react";
import { useReducedMotion } from "motion/react";

// PERF-011: the particle engine is decorative, so it loads after first paint.
const AmbientParticles = lazy(() => import("./AmbientParticles"));

function AmbientImpl({ paused = false }: { paused?: boolean }) {
  const reduced = useReducedMotion();
  return (
    <>
      <div className="ambient" aria-hidden="true">
        <div className="ambient-blob a" />
        <div className="ambient-blob b" />
      </div>
      <div className="grain" aria-hidden="true" />
      {!reduced && (
        <Suspense fallback={null}>
          <AmbientParticles paused={paused} />
        </Suspense>
      )}
    </>
  );
}

export const Ambient = memo(AmbientImpl);
