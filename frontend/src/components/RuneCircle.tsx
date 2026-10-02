// US6: a pure-SVG rotating rune circle framing a tool icon (no assets).
// Rotation is CSS (`.spin-slow`/`.spin-rev`), disabled under reduced motion.

const RUNES = "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ";

export function RuneCircle({ hue, size = 44 }: { hue: string; size?: number }) {
  return (
    <svg
      className="spell-rune"
      width={size}
      height={size}
      viewBox="0 0 100 100"
      style={{ color: hue }}
      aria-hidden="true"
    >
      <defs>
        <path id="rune-ring" d="M50,50 m-38,0 a38,38 0 1,1 76,0 a38,38 0 1,1 -76,0" />
      </defs>
      <g className="spin-slow">
        <text fontSize="9" fill="currentColor" opacity="0.85">
          <textPath href="#rune-ring">{RUNES}</textPath>
        </text>
      </g>
      <circle
        className="spin-rev"
        cx="50"
        cy="50"
        r="46"
        fill="none"
        stroke="currentColor"
        strokeWidth="0.8"
        strokeDasharray="2 6"
      />
      <circle cx="50" cy="50" r="30" fill="none" stroke="currentColor" strokeWidth="1.1" opacity="0.5" />
    </svg>
  );
}
