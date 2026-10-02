---
name: react-fastapi-ai-chat
description: >
  Polishing a lightweight React + FastAPI (asyncio) AI chat app that streams agent responses and
  runs tool calls (external APIs, fetching game combat logs from the web), styled in a high-fantasy
  setting. Covers the stream event protocol for tool calls, multi-theme system (CSS tokens, fonts,
  textures, View Transitions), "spellcasting" waiting animations for tool calls, smoother and
  prettier streaming text (token smoothing, word ink-in, Streamdown, stick-to-bottom), ambient
  effects and performance. Use when changing the chat UI, animations, themes, the streaming
  renderer, or the FastAPI streaming endpoint of this app. Keep it lightweight: no Kafka, no
  brokers; Redis only if more than one process is ever needed.
license: MIT
metadata:
  author: internal
  version: "3.0"
  domain: react, fastapi, asyncio, ai-chat, streaming, animation, theming
compatibility: Python 3.11+, FastAPI 0.110+, React 19.1+, Tailwind CSS v4, motion 13.x
---

# React + FastAPI AI Chat — High-Fantasy Polish

## 0. Context & principles

- **The app:** an AI chat agent. It calls tools (external APIs, fetching combat logs from the web for a game) and streams its answer.
- **Status:** it already works and looks OK. This skill is about making it look **great**, not about rebuilding it.
- **Setting:** high-fantasy, warcraft-like. Think arcane runes, glowing sigils, embers, parchment, gold filigree.
- **Lightweight always:** one FastAPI process, SQLite or in-memory, no message brokers.
- **Order of impact** (do these first when improving an existing app):
  1. Smooth the token stream (§3.1). This alone makes it feel 2× more premium.
  2. Spellcasting tool-call cards (§4).
  3. Theme tokens + fonts + textures (§2).
  4. Ink-in text, caret, completion flourish (§3.2–3.4).
  5. Ambient particles and background (§5).
- **Edit, don't rewrite.** Find the existing stream parser, message component and CSS entry point, then layer these in.

---

## 1. Stream event protocol (backend → frontend)

Animations can only be as good as the events behind them. The backend must emit **typed events**
so the UI knows *when* a tool starts, *which* tool it is, and when it finishes.

| Event | Payload | UI reaction |
|-------|---------|-------------|
| `run_start` | `{run_id}` | Show the "summoning" orb (§4.2) |
| `tool_start` | `{id, name, args}` | Spawn a spell card, start cast bar |
| `tool_progress` *(optional)* | `{id, done, total, note}` | Switch cast bar to determinate |
| `tool_end` | `{id, ok, summary, ms}` | Resolve (burst) or fizzle (shake) |
| `token` | `{text}` | Feed the smoothing buffer (§3.1) |
| `done` | `{usage?}` | Completion flourish (§3.4) |
| `error` | `{message}` | Fizzle the whole run |

```python
# FastAPI: POST endpoint streaming SSE-formatted lines
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

@router.post("/api/chat")
async def chat(req: ChatRequest):
    async def gen():
        yield sse("run_start", {"run_id": run_id})
        async for ev in agent.run(req):          # your agent loop
            if ev.kind == "tool_call":
                yield sse("tool_start", {"id": ev.id, "name": ev.name, "args": ev.args})
            elif ev.kind == "tool_result":
                yield sse("tool_end", {"id": ev.id, "ok": ev.ok, "summary": ev.summary[:140], "ms": ev.ms})
            elif ev.kind == "text_delta":
                yield sse("token", {"text": ev.text})
        yield sse("done", {})
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

- `EventSource` only supports GET. For a POST chat endpoint, read the stream with `fetch` + `response.body.getReader()` and split on `\n\n` (or use `@microsoft/fetch-event-source`).
- Keep `summary` short and human-readable (e.g. "Fetched 3 boss encounters, 41 players"). It's shown in the resolved card.
- Emit `tool_progress` whenever you can (pages fetched, logs parsed). Determinate bars feel far better than spinners.

---

## 2. Theme system — unique, switchable fantasy themes

### 2.1 Token architecture

Every colour, glow, font and texture is a CSS variable, set per theme with `data-theme` on `<html>`.
Components only ever use tokens (`bg-background`, `text-primary`, `var(--glow)`). Swapping the theme swaps the whole mood.

```css
/* src/index.css */
@import "tailwindcss";
@import "tw-animate-css";

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-primary: var(--primary);
  --color-muted: var(--muted);
  --color-card: var(--card);
  --color-border: var(--border);
  --color-glow: var(--glow);
  --font-display: var(--font-display);
  --font-body: var(--font-body);
}

/* Arcane Sanctum — violet & starlight (default) */
:root, [data-theme="arcane"] {
  --background: oklch(0.16 0.04 285);
  --foreground: oklch(0.93 0.02 285);
  --card:       oklch(0.21 0.05 285 / 0.75);
  --muted:      oklch(0.65 0.05 285);
  --primary:    oklch(0.72 0.19 300);
  --glow:       oklch(0.80 0.17 300);
  --border:     oklch(0.45 0.10 295 / 0.5);
  --particle:   "motes";
  --font-display: "Cinzel", serif;
  --font-body:  "Alegreya Sans", system-ui, sans-serif;
}

/* Ember Forge — molten orange & soot */
[data-theme="ember"] {
  --background: oklch(0.15 0.02 40);
  --foreground: oklch(0.94 0.03 70);
  --card:       oklch(0.20 0.03 40 / 0.8);
  --muted:      oklch(0.66 0.06 55);
  --primary:    oklch(0.72 0.18 50);
  --glow:       oklch(0.82 0.17 65);
  --border:     oklch(0.50 0.12 45 / 0.5);
}

/* Frostbound — glacial cyan & silver */
[data-theme="frost"] {
  --background: oklch(0.17 0.03 240);
  --foreground: oklch(0.95 0.02 220);
  --card:       oklch(0.22 0.04 235 / 0.75);
  --muted:      oklch(0.70 0.04 225);
  --primary:    oklch(0.80 0.11 215);
  --glow:       oklch(0.90 0.09 210);
  --border:     oklch(0.60 0.07 220 / 0.45);
}

/* Shadowfen — sickly green & void */
[data-theme="shadowfen"] {
  --background: oklch(0.13 0.03 150);
  --foreground: oklch(0.92 0.04 140);
  --card:       oklch(0.18 0.04 150 / 0.8);
  --muted:      oklch(0.62 0.07 145);
  --primary:    oklch(0.78 0.20 140);
  --glow:       oklch(0.86 0.22 135);
  --border:     oklch(0.45 0.12 145 / 0.5);
}

/* Gilded Citadel — parchment & gold (a light theme) */
[data-theme="gilded"] {
  --background: oklch(0.94 0.03 85);
  --foreground: oklch(0.25 0.03 60);
  --card:       oklch(0.97 0.02 85 / 0.85);
  --muted:      oklch(0.50 0.04 70);
  --primary:    oklch(0.62 0.13 75);
  --glow:       oklch(0.78 0.15 85);
  --border:     oklch(0.62 0.10 75 / 0.6);
}

body { background: var(--background); color: var(--foreground); font-family: var(--font-body); }
h1, h2, h3, .font-display { font-family: var(--font-display); letter-spacing: 0.04em; }
```

### 2.2 Fonts (free, Google Fonts / `@fontsource`)

| Role | Options | Note |
|------|---------|------|
| Display / headings / tool names | **Cinzel**, Cinzel Decorative, Uncial Antiqua, Pirata One | Use sparingly; caps look regal |
| Body / chat text | **Alegreya Sans**, Alegreya, Cormorant Garamond (larger sizes only) | Readability first. Never put a blackletter font in long chat text |
| Rune glyphs | Unicode Elder Futhark (`ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃ`) in any font that has them (e.g. Noto Sans Runic) | Free, no assets needed |

### 2.3 Texture & ornament (what makes it feel "fantasy", not "dark mode")

- **Grain:** a fixed full-screen SVG `feTurbulence` noise overlay at 4–8% opacity with `mix-blend-mode: overlay`.
- **Vignette:** `radial-gradient(ellipse at center, transparent 55%, oklch(0 0 0 / 0.55))` on a fixed overlay.
- **Ornate frames:** a 1px `--border` plus small SVG corner flourishes positioned at the card corners. Get them from game-icons.net or draw simple ones.
- **Living border on the active assistant message:** a rotating conic-gradient glow:

```css
@property --angle { syntax: "<angle>"; inherits: false; initial-value: 0deg; }
.arcane-border {
  border: 1px solid transparent;
  background:
    linear-gradient(var(--card), var(--card)) padding-box,
    conic-gradient(from var(--angle), transparent 60%, var(--glow), transparent 90%) border-box;
  animation: spin-angle 4s linear infinite;
}
@keyframes spin-angle { to { --angle: 360deg; } }
```

- **Icons:** `react-icons/gi` gives you game-icons.net's ~4,000 fantasy icons (`GiCrystalBall`, `GiScrollUnfurled`, `GiSpellBook`, `GiPortal`, `GiRuneStone`…). They're **CC BY 3.0, so add a credit line** (e.g. in an About/footer: "Icons by game-icons.net contributors, CC BY 3.0").

### 2.4 Theme switch with a magical reveal (View Transitions API)

```ts
export function switchTheme(next: string, e: React.MouseEvent) {
  const apply = () => document.documentElement.setAttribute("data-theme", next)
  if (!document.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) return apply()
  const { clientX: x, clientY: y } = e
  const r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))
  document.startViewTransition(apply).ready.then(() => {
    document.documentElement.animate(
      { clipPath: [`circle(0 at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
      { duration: 650, easing: "cubic-bezier(.2,.8,.2,1)", pseudoElement: "::view-transition-new(root)" },
    )
  })
}
```
The new theme spreads outward from the click like a spell. Store the chosen theme in `localStorage` (a per-viewer convenience).

### 2.5 IP guardrail
Keep the look **original and "warcraft-like"**, not Warcraft:
- No Blizzard logos, game UI art, screenshots or the game's commercial fonts.
- Use original theme names (as above) and CC-licensed icons.
- Data and images returned by a game's official API may be shown under that API's terms.

---

## 3. Streaming text — from "fading in" to "being inscribed"

### 3.1 Smooth the stream (biggest win)

Tokens arrive in uneven bursts, and that jitter is what makes streaming look cheap. Buffer the
incoming text and release it at a steady, adaptive rate on `requestAnimationFrame`. It speeds up when
far behind, so it never lags noticeably.

```tsx
// src/hooks/useSmoothText.ts
import { useEffect, useRef, useState } from "react"

export function useSmoothText(target: string, streaming: boolean) {
  const shownLen = useRef(streaming ? 0 : target.length)
  const [shown, setShown] = useState(streaming ? "" : target)

  useEffect(() => {
    if (!streaming) { shownLen.current = target.length; setShown(target); return }
    let raf = 0
    const tick = () => {
      const backlog = target.length - shownLen.current
      if (backlog > 0) {
        // ~2 chars/frame baseline; catch up proportionally when behind
        const step = Math.max(2, Math.ceil(backlog / 15))
        shownLen.current = Math.min(target.length, shownLen.current + step)
        setShown(target.slice(0, shownLen.current))
        raf = requestAnimationFrame(tick)
      }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, streaming])

  return shown
}
```

### 3.2 Markdown that doesn't break mid-stream: Streamdown

- `npm i streamdown` is a drop-in for `react-markdown` that renders **incomplete/unterminated markdown** gracefully, so no flashing `**` or broken tables while streaming.
- It memoizes completed blocks, so earlier paragraphs don't re-render on every token.
- With Tailwind v4, add `@source "../node_modules/streamdown/dist/*.js";` to `index.css` (check the README path for your version).

### 3.3 "Magic ink" word reveal

Wrap each word in a span with a rehype plugin. React keeps already-mounted spans, so a CSS
mount animation plays **once per new word only**. Use cheap CSS keyframes, not Motion components (there can be thousands of words).

```ts
// src/lib/rehypeWordSpans.ts
import { visit } from "unist-util-visit"

export function rehypeWordSpans() {
  return (tree: any) => {
    visit(tree, "text", (node: any, index, parent: any) => {
      if (!parent || index == null || ["code", "pre"].includes(parent.tagName)) return
      const parts = node.value.split(/(\s+)/).filter(Boolean)
      parent.children.splice(index, 1, ...parts.map((p: string) =>
        /^\s+$/.test(p)
          ? { type: "text", value: p }
          : { type: "element", tagName: "span", properties: { className: ["ink"] },
              children: [{ type: "text", value: p }] }))
      return index + parts.length
    })
  }
}
```

```tsx
<div className={streaming ? "is-streaming" : ""}>
  <Streamdown rehypePlugins={[/* keep Streamdown's defaults */, rehypeWordSpans]}>
    {useSmoothText(message.text, streaming)}
  </Streamdown>
</div>
```
Passing `rehypePlugins` may replace Streamdown's defaults. Import its exported defaults and append to them; check the shape in your installed version.

```css
.is-streaming .ink { animation: ink-in 480ms ease-out both; }
@keyframes ink-in {
  0%   { opacity: 0; filter: blur(5px); color: var(--glow); text-shadow: 0 0 12px var(--glow); }
  60%  { opacity: 1; filter: blur(0); }
  100% { color: inherit; text-shadow: none; }
}
```
Each word appears blurred and glowing in the theme colour, then settles into plain text, like ink drying.

### 3.4 Caret, layout and completion flourish

- **Ember caret:** a glowing flickering dot after the last block while streaming:
  ```css
  .is-streaming > :last-child::after {
    content: ""; display: inline-block; width: .45em; height: .45em; margin-left: .2em;
    border-radius: 50%; background: var(--glow); box-shadow: 0 0 10px 2px var(--glow);
    animation: flicker 1.1s ease-in-out infinite;
  }
  @keyframes flicker { 50% { opacity: .35; transform: scale(.8); } }
  ```
- **No jumpy growth:** give the message container Motion's `layout` prop so its height eases as text arrives.
- **Auto-scroll:** use **`use-stick-to-bottom`**. It's built for AI chat: it follows streaming content smoothly with variable-height content, and stops fighting the user when they scroll up (shows a "back to bottom" button).
- **Completion flourish** (on `done`): a single gold sheen sweeps diagonally across the finished message (a pseudo-element with a moving `linear-gradient`, ~900 ms, played once). Then the arcane border fades out.
- **Message entrance:** user messages spring in from the right (`initial={{ opacity: 0, x: 24, scale: .98 }}`, spring `stiffness: 300, damping: 26`). The assistant bubble fades/rises from the summoning orb's position.

---

## 4. Tool calls as spellcasting (the waiting experience)

### 4.1 Spell registry: one entry per tool

Each tool gets its own icon, magic school colour, verb and rotating flavor lines, so every tool call feels distinct.

```ts
// src/lib/spells.ts
import { GiScrollUnfurled, GiCrystalBall, GiPortal, GiSpellBook } from "react-icons/gi"

export const SPELLS: Record<string, Spell> = {
  fetch_logs: {
    icon: GiScrollUnfurled, hue: "oklch(0.80 0.15 85)",       // gold
    verb: "Unsealing the battle chronicles",
    flavor: ["Tallying the fallen…", "Reading the blood-ink ledgers…", "Counting every blow struck…"],
  },
  web_search: {
    icon: GiCrystalBall, hue: "oklch(0.78 0.14 220)",         // scrying blue
    verb: "Scrying the far realms",
    flavor: ["Peering through the mists…", "Whispers from distant lands…"],
  },
  call_api: {
    icon: GiPortal, hue: "oklch(0.75 0.20 300)",              // arcane violet
    verb: "Opening a portal",
    flavor: ["Binding the leyline…", "The gate shimmers…"],
  },
}
export const DEFAULT_SPELL = { icon: GiSpellBook, hue: "var(--glow)", verb: "Weaving a spell", flavor: ["The runes stir…"] }
```
Map **every** real tool name in the app here. Unknown tools fall back to `DEFAULT_SPELL`.

### 4.2 Phases & components

| Phase | Trigger | Visual |
|-------|---------|--------|
| **Summoning** | message sent → before first event | A pulsing orb with a slowly rotating rune circle; shimmer text "The archmage ponders…" |
| **Casting** | `tool_start` | Spell card slides in: rune circle around the tool icon, **cast bar** filling, rotating flavor line, embers rising |
| **Resolved** | `tool_end ok` | Bar snaps to 100% with a flash, radial burst, card **collapses into a compact chip** showing `summary` and duration |
| **Fizzled** | `tool_end !ok` | Quick shake (x: [0,-6,6,-4,4,0]), desaturate, red-tinted crack line, "The spell fizzled — <reason>" |
| **Narrating** | first `token` | Orb shrinks into the ember caret; text begins inscribing |

**Rules:**
- **Minimum display time ~600 ms** per cast. Hold fast results until then so cards never flicker.
- **Parallel tool calls:** stack the cards with `staggerChildren: 0.08` and `layout`, so resolved ones collapse and the others glide up.
- Resolved chips stay in the message (collapsed, expandable to show args/summary). The "spellbook" of what the agent did becomes part of the answer.

### 4.3 Cast bar (indeterminate → determinate)

```tsx
import { motion, useAnimate } from "motion/react"
import { useEffect } from "react"

export function CastBar({ hue, done, progress }: { hue: string; done: boolean; progress?: number }) {
  const [scope, animate] = useAnimate()
  useEffect(() => {
    if (done) animate(scope.current, { scaleX: 1 }, { duration: 0.18, ease: "easeOut" })
    else if (progress != null) animate(scope.current, { scaleX: progress }, { duration: 0.3 })
    else animate(scope.current, { scaleX: 0.9 }, { duration: 8, ease: [0.1, 0.6, 0.3, 1] }) // creeps toward 90%
  }, [done, progress])
  return (
    <div className="relative h-2 overflow-hidden rounded-full bg-black/40 ring-1 ring-border">
      <motion.div ref={scope} initial={{ scaleX: 0 }} style={{ originX: 0, background: hue,
        boxShadow: `0 0 12px ${hue}` }} className="absolute inset-0 rounded-full" />
      {/* travelling sparkle */}
      <div className="absolute inset-y-0 w-10 animate-[sheen_1.4s_linear_infinite]
                      bg-gradient-to-r from-transparent via-white/50 to-transparent" />
    </div>
  )
}
/* @keyframes sheen { from { transform: translateX(-40px) } to { transform: translateX(400%) } } */
```

### 4.4 Rune circle (pure SVG, no assets)

```tsx
export function RuneCircle({ hue, size = 64 }: { hue: string; size?: number }) {
  const runes = "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ"
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" style={{ color: hue }}>
      <defs><path id="ring" d="M50,50 m-38,0 a38,38 0 1,1 76,0 a38,38 0 1,1 -76,0" /></defs>
      <g className="origin-center animate-[spin_12s_linear_infinite]">
        <text fontSize="9" fill="currentColor" opacity=".85">
          <textPath href="#ring">{runes}</textPath>
        </text>
      </g>
      <circle cx="50" cy="50" r="46" fill="none" stroke="currentColor" strokeWidth=".8"
              strokeDasharray="2 6" className="origin-center animate-[spin_8s_linear_infinite_reverse]" />
      <circle cx="50" cy="50" r="28" fill="none" stroke="currentColor" strokeWidth="1.2" opacity=".5" />
    </svg>
  )
}
```
Place the tool icon in the centre. Add `filter: drop-shadow(0 0 6px currentColor)` for glow.

### 4.5 Flavor text: rotating with shimmer

```tsx
const [i, setI] = useState(0)
useEffect(() => { const t = setInterval(() => setI(n => n + 1), 2200); return () => clearInterval(t) }, [])
<AnimatePresence mode="wait">
  <motion.span key={i} initial={{ opacity: 0, y: 6, filter: "blur(4px)" }}
    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} exit={{ opacity: 0, y: -6, filter: "blur(4px)" }}
    className="bg-[linear-gradient(90deg,var(--muted),var(--glow),var(--muted))] bg-[length:200%_100%]
               bg-clip-text text-transparent animate-[shimmer_2s_linear_infinite]">
    {spell.flavor[i % spell.flavor.length]}
  </motion.span>
</AnimatePresence>
/* @keyframes shimmer { to { background-position: -200% 0 } } */
```

### 4.6 Embers & bursts

- **Card embers (CSS only):** 10–14 absolutely-positioned 3px dots with randomized `--x`, `--delay`, `--dur` custom properties, animating `translateY(-60px)` and fading out. Pretty and nearly free.
- **Resolve burst:** 8 dots radiating out (Motion `animate={{ x, y, opacity: 0, scale: 0 }}` over 500 ms) plus a ring that scales 0.6 → 1.6 while fading.
- **Full-screen spectacle** (optional): `@tsparticles/react` + `@tsparticles/slim` for theme-specific ambient particles (§5).

---

## 5. Ambient world

- **Background:** 2–3 large blurred radial gradients in theme colours drifting slowly (60–90 s loops) behind everything, plus the grain and vignette overlays (§2.3).
- **Theme particles** via `@tsparticles/react`: arcane → floating motes, ember → rising sparks, frost → slow snow, shadowfen → drifting spores, gilded → dust in sunbeams. Keep counts low (30–60) and pause when `document.hidden`.
- **Agent "breathing":** while a run is active, intensify particles slightly or brighten the vignette edge. The world reacts to the agent thinking.
- **Sound (optional, off by default):** `use-sound` for a soft chime on cast, whoosh on resolve, low thud on fizzle. Find CC0 sounds on freesound.org. Provide a mute toggle and remember it.

---

## 6. Motion & polish rules

- **Durations:** micro-interactions 150–250 ms; cards 300–450 ms; ambient loops long and slow. Springs for anything the user triggers.
- **Cheap properties only:** animate `opacity`, `transform`, `filter` (sparingly). Use `layout` for size changes. Never animate `width/height/top`.
- **Glow, don't flash:** use soft `box-shadow`/`drop-shadow` in `--glow`; avoid strobing.
- **One hero animation at a time:** while a spell is casting, everything else stays calm.
- **Reduced motion:** with `useReducedMotion()` or `prefers-reduced-motion`, disable particles, rotation and ink blur. Keep simple fades and static rune circles.
- **Performance:** per-word effects are CSS keyframes only. Memoize finished messages (`React.memo`). Cap particles. Check with the React Profiler and the Chrome Performance tab that streaming stays at 60 fps.

### Library cheat-sheet

| Need | Library |
|------|---------|
| Animation & gestures | `motion` (import from `motion/react`) |
| Streaming markdown | `streamdown` |
| Chat auto-scroll | `use-stick-to-bottom` |
| Fantasy icons | `react-icons/gi` (game-icons.net, CC BY 3.0) |
| Particles | `@tsparticles/react` + `@tsparticles/slim` |
| Animated illustrations | `@lottiefiles/dotlottie-react` (free Lottie files) |
| Sound | `use-sound` |
| Components & theming base | shadcn/ui + Tailwind v4 (CSS-first, OKLCH tokens) |
| Ready-made effects to adapt | Magic UI, Aceternity UI, Motion UI |
| Chat UI reference components | AI Elements (shadcn-based, uses Streamdown & stick-to-bottom) — borrow patterns |

---

## 7. Backend notes (keep it light)

- Single uvicorn worker; SQLite (WAL) or in-memory for history/cache.
- Cache fetched combat logs (in-memory dict with TTL, or a SQLite table) so repeat questions are instant. Then use the minimum-display rule (§4.2) so cached casts still look good.
- Run blocking parsing in `asyncio.to_thread`. Run parallel tool calls with `asyncio.gather`, emitting `tool_start` for all first.
- Redis only if more than one process is ever needed. Never Kafka.

---

## 8. Checklist

- [ ] Backend emits `run_start / tool_start / tool_progress / tool_end / token / done / error`
- [ ] Every tool has a `SPELLS` entry (icon, hue, verb, flavor)
- [ ] Token smoothing buffer in front of the renderer
- [ ] Streamdown + word ink-in + ember caret + `layout` growth
- [ ] `use-stick-to-bottom` for scrolling
- [ ] Spell cards: summoning → casting → resolved/fizzled, 600 ms minimum, parallel stacking
- [ ] ≥3 themes on tokens only, View Transition switch, grain + vignette
- [ ] Fantasy display font for headings, readable body font
- [ ] Game-icons CC BY credit present; no Blizzard assets
- [ ] Reduced-motion path tested; streaming holds 60 fps
