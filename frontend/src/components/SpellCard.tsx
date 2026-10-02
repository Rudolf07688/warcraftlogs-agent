// US6 spellcasting card: casting (rune circle + icon + cast bar + rotating flavor)
// → resolved (compact chip with summary + duration) / fizzled (shake + reason).
// Honors a ~600 ms minimum display so fast/cached tools never flicker (FR-032).
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { SpellCardState } from "../types";
import { spellFor } from "../lib/spells";
import { RuneCircle } from "./RuneCircle";
import { CastBar } from "./CastBar";

const MIN_DISPLAY_MS = 600;

function Flavor({ lines, hue }: { lines: string[]; hue: string }) {
  const [i, setI] = useState(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced || lines.length <= 1) return;
    const t = setInterval(() => setI((n) => n + 1), 2200);
    return () => clearInterval(t);
  }, [reduced, lines.length]);
  const text = lines[i % lines.length];
  if (reduced) return <span className="spell-flavor" style={{ color: hue }}>{text}</span>;
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={i}
        className="spell-flavor shimmer-text"
        initial={{ opacity: 0, y: 6, filter: "blur(4px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        exit={{ opacity: 0, y: -6, filter: "blur(4px)" }}
        transition={{ duration: 0.3 }}
      >
        {text}
      </motion.span>
    </AnimatePresence>
  );
}

export function SpellCard({ card, instant }: { card: SpellCardState; instant?: boolean }) {
  const spell = spellFor(card.name);
  const Icon = spell.icon;
  const reduced = useReducedMotion();
  const mountedAt = useRef<number | null>(null);
  // Persisted chips (instant) show their final state immediately; live cards cast first.
  const [display, setDisplay] = useState<SpellCardState["status"]>(
    instant ? card.status : "casting",
  );

  // Record mount time without Date.now at render; performance.now via effect.
  useEffect(() => {
    if (mountedAt.current == null) mountedAt.current = performance.now();
  }, []);

  // Enforce the minimum cast display before flipping to resolved/fizzled.
  useEffect(() => {
    if (instant) {
      setDisplay(card.status);
      return;
    }
    if (card.status === "casting") {
      setDisplay("casting");
      return;
    }
    const start = mountedAt.current ?? performance.now();
    const elapsed = performance.now() - start;
    const remaining = Math.max(0, MIN_DISPLAY_MS - elapsed);
    if (remaining === 0) {
      setDisplay(card.status);
      return;
    }
    const t = setTimeout(() => setDisplay(card.status), remaining);
    return () => clearTimeout(t);
  }, [card.status, instant]);

  if (display !== "casting") {
    const fizzled = display === "fizzled";
    return (
      <motion.div layout initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}>
        <span className={`spell-chip ${fizzled ? "fizzled" : "ok"}`} title={card.summary || card.name}>
          <span className="spell-chip-dot" style={{ color: fizzled ? undefined : spell.hue }}>
            <Icon size={14} />
          </span>
          <span className="spell-chip-summary">
            {fizzled ? `The spell fizzled — ${card.summary || "no reason given"}` : card.summary || spell.verb}
          </span>
          {card.ms != null && <span className="spell-chip-ms">{formatMs(card.ms)}</span>}
        </span>
      </motion.div>
    );
  }

  return (
    <motion.div
      layout
      className="spell-card"
      initial={reduced ? { opacity: 0 } : { opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 26 }}
    >
      <div className="spell-icon" style={{ color: spell.hue }}>
        {!reduced && <RuneCircle hue={spell.hue} size={34} />}
        <span className="spell-glyph">
          <Icon size={16} />
        </span>
      </div>
      <div className="spell-body">
        <span className="spell-verb">{spell.verb}</span>
        <Flavor lines={spell.flavor} hue={spell.hue} />
        <CastBar hue={spell.hue} done={false} />
      </div>
    </motion.div>
  );
}

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}
