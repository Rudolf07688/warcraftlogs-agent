// Feature 080 / 085: a status line is model text (thoughts, interim text) or carries model ids
// (retry and fallback labels). It is shown as plain text, without bidi or zero-width controls
// (they could reorder or hide parts of a line that sits in app chrome), and never longer than
// this many characters, cut on a character boundary, not inside a surrogate pair.
export const STATUS_MAX = 120;

const CONTROLS = /[؜​-‏‪-‮⁠-⁩﻿]/g;

export function cleanStatus(text: string): string {
  return Array.from(text.replace(CONTROLS, "")).slice(0, STATUS_MAX).join("");
}
