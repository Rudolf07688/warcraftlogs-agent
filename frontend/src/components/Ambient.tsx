// US6 ambient world: slow drifting blurred gradients + grain/vignette (CSS, cheap)
// plus a capped particle field. Particles and drift are disabled under reduced motion
// (FR-034); the engine pauses itself when the tab is hidden (SC-010).
import { useReducedMotion } from "motion/react";
import Particles, { ParticlesProvider } from "@tsparticles/react";
import { loadSlim } from "@tsparticles/slim";
import type { ISourceOptions } from "@tsparticles/engine";

const PARTICLE_OPTIONS: ISourceOptions = {
  fpsLimit: 60,
  pauseOnBlur: true,
  pauseOnOutsideViewport: true,
  fullScreen: { enable: false },
  detectRetina: true,
  particles: {
    number: { value: 40, density: { enable: true } },
    color: { value: ["#e8c88a", "#c9962f", "#f0d9a6"] },
    opacity: { value: { min: 0.08, max: 0.42 }, animation: { enable: true, speed: 0.4 } },
    size: { value: { min: 1, max: 2.6 } },
    move: {
      enable: true,
      speed: 0.4,
      direction: "top",
      random: true,
      straight: false,
      outModes: { default: "out" },
    },
  },
};

export function Ambient() {
  const reduced = useReducedMotion();
  return (
    <>
      <div className="ambient" aria-hidden="true">
        <div className="ambient-blob a" />
        <div className="ambient-blob b" />
      </div>
      <div className="grain" aria-hidden="true" />
      {!reduced && (
        <ParticlesProvider init={async (engine) => { await loadSlim(engine); }}>
          <Particles id="ambient-embers" className="ambient" options={PARTICLE_OPTIONS} />
        </ParticlesProvider>
      )}
    </>
  );
}
