# Plan: Slightly larger default font (023)

Light flow (1 point, CSS only). Decision 30 fixes the approach.

1. Commit 1: mechanical pass converting every `font-size: Npx` in `frontend/src/styles.css` and `frontend/src/index.css` to `N/16 rem`. Computed sizes stay identical at the 16px root; verified by a before/after computed-style dump.
2. Commit 2: `html { font-size: 106.25% }` (relative, so the user's browser setting still scales) once in `index.css`.
3. Verify the build and layout at 1280px and 390px.

Files: `frontend/src/styles.css`, `frontend/src/index.css`, `specs/023-larger-font/**`. No dependencies, no migrations.
