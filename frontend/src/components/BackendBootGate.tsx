import { useEffect, useRef, useState, type ReactNode } from "react";
import { getBackendHealth } from "../api/restClient";
import type { BackendHealth, StartupStep } from "../types";
import { RuneCircle } from "./RuneCircle";

const POLL_MS = 1000;

type Probe =
  | { kind: "unreachable"; attempts: number }
  | { kind: "booting"; health: BackendHealth }
  | { kind: "failed"; health: BackendHealth };

/**
 * Holds the whole app behind a boot overlay until the backend reports `ready`.
 *
 * With `docker compose up` the Vite container is up long before the Python one has
 * finished its lifespan work (ADK tables, guide registry, model probes). The backend
 * exposes that progress on GET /api/health (see backend/app/startup.py); until it is
 * ready every other route 503s, so nothing below this gate is mounted — in particular
 * AuthProvider's /api/auth/me must not run early or it would read a 503 as signed-out.
 *
 * The gate only applies to the initial load: once ready it never re-engages (the chat
 * header's connected/disconnected pill covers later hiccups).
 */
export function BackendBootGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [probe, setProbe] = useState<Probe>({ kind: "unreachable", attempts: 0 });
  const attempts = useRef(0);

  useEffect(() => {
    if (ready) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const tick = async () => {
      let health: BackendHealth | null = null;
      try {
        health = await getBackendHealth();
      } catch {
        health = null; // connection refused / proxy 502 / non-JSON body
      }
      if (!active) return;
      if (health?.status === "ok") {
        setReady(true);
        return;
      }
      if (!health || !health.startup) {
        attempts.current += 1;
        setProbe({ kind: "unreachable", attempts: attempts.current });
      } else if (health.status === "error") {
        setProbe({ kind: "failed", health });
      } else {
        setProbe({ kind: "booting", health });
      }
      timer = setTimeout(tick, POLL_MS);
    };

    void tick();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [ready]);

  if (ready) return <>{children}</>;
  return <BootOverlay probe={probe} />;
}

function BootOverlay({ probe }: { probe: Probe }) {
  const steps = probe.kind === "unreachable" ? [] : probe.health.startup?.steps ?? [];
  const failed = probe.kind === "failed";
  const headline =
    probe.kind === "unreachable"
      ? "Waiting for the backend container…"
      : failed
        ? "The backend failed to start"
        : "The backend is still booting…";
  const sub =
    probe.kind === "unreachable"
      ? probe.attempts < 5
        ? "The API is not answering yet. This is normal right after `docker compose up`."
        : "Still no answer from the API. Is the backend container (re)building, or did it exit? Check `docker compose logs backend`."
      : failed
        ? probe.health.startup?.error ?? "A required startup step failed."
        : "Hold tight — the page will load itself as soon as every step is done.";

  return (
    <div
      className={`boot-overlay${failed ? " boot-failed" : ""}`}
      role="status"
      aria-live="polite"
      aria-busy={!failed}
    >
      <div className="boot-card">
        <div className="boot-spinner" aria-hidden="true">
          <RuneCircle hue={failed ? "var(--danger)" : "var(--wow-gold)"} size={88} />
          <span className="boot-glyph">{failed ? "✕" : "✦"}</span>
        </div>
        <h1 className="boot-title">{headline}</h1>
        <p className="boot-sub">{sub}</p>
        {steps.length > 0 && (
          <ol className="boot-steps">
            {steps.map((s) => (
              <StepRow key={s.key} step={s} />
            ))}
          </ol>
        )}
        {probe.kind !== "unreachable" && probe.health.startup && (
          <p className="boot-elapsed">
            {(probe.health.startup.elapsed_ms / 1000).toFixed(1)}s elapsed
            {probe.health.db === "error" ? " · database unreachable" : ""}
          </p>
        )}
        {failed && (
          <p className="boot-hint">
            Fix the cause and restart the backend; this page keeps checking and will load
            once it reports ready.
          </p>
        )}
      </div>
    </div>
  );
}

const STATUS_GLYPH: Record<StartupStep["status"], string> = {
  pending: "○",
  running: "◌",
  done: "✓",
  skipped: "–",
  failed: "✕",
};

function StepRow({ step }: { step: StartupStep }) {
  return (
    <li className={`boot-step boot-step-${step.status}`}>
      <span className="boot-step-glyph" aria-hidden="true">
        {STATUS_GLYPH[step.status]}
      </span>
      <span className="boot-step-label">{step.label}</span>
      <span className="boot-step-detail">
        {step.detail ?? (step.ms != null ? `${step.ms} ms` : "")}
      </span>
    </li>
  );
}
