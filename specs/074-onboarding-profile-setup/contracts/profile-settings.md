# Contract: profile settings (074)

All under the session (cookie); unsafe methods need `X-CSRF-Token`. Tenant from the session only.

## GET /api/profile/settings → 200
```json
{"main_class": "Paladin", "main_spec": "Holy", "main_content": "both", "onboarding_pending": false}
```
Fresh workspace: all three null, `onboarding_pending: true`.

## PUT /api/profile/settings → 200 (same body as GET)
Request (all three keys required, each nullable; no other keys):
```json
{"main_class": "Paladin", "main_spec": "Holy", "main_content": "both"}
```
422, nothing stored, when: unknown key (e.g. `tenant_id`), a missing key, class not an exact
roster class, spec not an exact spec of that class, spec without class, content not
raid|mplus|both|null, any string over 40 characters.

## POST /api/profile/onboarding/skip → 200 (same body as GET, `onboarding_pending: false`)
Idempotent; the first skip time is kept.

## Unchanged
`GET /api/profile` (`ProfileOut`) and every existing profile route.
