// The ember particle field behind the app (US6). Split out of Ambient so the particle
// engine loads as its own chunk after first paint, not in the main bundle (PERF-011).
import { useEffect, useRef } from "react";
import Particles, { ParticlesProvider } from "@tsparticles/react";
import { loadSlim } from "@tsparticles/slim";
import type { Container, ISourceOptions } from "@tsparticles/engine";

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

// PERF-010: `paused` stops the animation (e.g. while a reply streams) so the canvas
// doesn't compete with rendering the reply.
export default function AmbientParticles({ paused }: { paused: boolean }) {
  const container = useRef<Container | undefined>(undefined);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  useEffect(() => {
    if (paused) container.current?.pause();
    else container.current?.play();
  }, [paused]);
  return (
    <ParticlesProvider init={async (engine) => { await loadSlim(engine); }}>
      <Particles
        id="ambient-embers"
        className="ambient"
        options={PARTICLE_OPTIONS}
        particlesLoaded={async (c) => {
          container.current = c;
          if (pausedRef.current) c?.pause();
        }}
      />
    </ParticlesProvider>
  );
}
