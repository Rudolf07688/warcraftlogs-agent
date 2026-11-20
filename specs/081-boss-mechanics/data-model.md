# Data model: mechanic notes

One file per raid tier, `backend/app/kb/mechanics/<tier>.json` (`TierNotes`):

- `zone`: `{id, name}` (WCL zone).
- `note`: free text for maintainers.
- `encounters[]` (`Encounter`): `id` (WCL encounter id), `name`, `aliases[]` (NPC names, short forms),
  `abilities[]`.
- `abilities[]` (`Ability`): `name` (Encounter Journal name), `ids[]` (spell ids, as WCL reports them), `aliases[]`,
  `what_it_does` (<= 400 chars), `what_to_do` (<= 500), `source {name, url (https)}`, `patch` (x.y.z: the patch live
  when the source was last updated).

Rules (tests): every lookup key (normalised name, alias, id) is unique within a boss; boss keys are unique across
bosses; every note has an https source.
