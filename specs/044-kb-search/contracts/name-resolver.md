# Contract: name resolver (sc-304, board `contract:kb` 1)

Module `backend/app/services/name_resolver.py`. 043 (chunk writers) and 045 (sc-131) import it
after the sc-304 milestone merge. Every function either returns a canonical value or raises
`ResolutionError`; none returns an empty match.

```python
def name_key(value: str) -> str
    # NFKD, combining marks dropped, casefolded, letters and digits only.
    # "Ula'tek" / "ulatek" / "Úla-tek" -> "ulatek". Writers store it in players[].key /
    # characters[].key; search matches with it.

class ResolutionError(ValueError):
    field: str                      # "class" | "spec" | "encounter" | "difficulty" | "character"
    value: str                      # the input as given
    reason: Literal["unknown", "ambiguous"]
    matches: tuple[str, ...]        # up to 5 close or competing matches, display form
    # str(err): 'Unknown spec "rets". Close matches: Retribution.' — safe to show the agent.

def resolve_class(value: str) -> str                          # "warr" -> "Warrior"
def resolve_class_spec(value: str, class_name: str | None = None) -> ClassSpec
    # ONE answer required: "arms warr" -> Warrior/Arms/dps; "prot" -> ambiguous;
    # ("prot", class_name="Paladin") -> Paladin/Protection/tank; a class alone -> spec None.
def spec_pairs(spec: str, class_name: str | None = None) -> tuple[ClassSpec, ...]
    # Search filter: every (class, spec) with this spec: "holy" -> Paladin/Holy, Priest/Holy.
    # Unknown spec, or a spec the given class lacks -> ResolutionError.
def resolve_difficulty(value: str | int) -> ResolvedDifficulty
    # "hc"/"heroic"/4 -> 4 Heroic; "m+"/"mythic+"/"mplus"/10 -> 10 Mythic+; "lfr"/1; "normal"/3; "mythic"/5.

async def resolve_encounter(value: str | int, *, session: AsyncSession, tenant_id: UUID | None)
        -> tuple[ResolvedEncounter, ResolvedDifficulty | None]
    # Zone list (load_world_zones, cached) + the tenant's known_encounters. A difficulty word in
    # the phrase ("heroic ulatek") is returned separately. Zone list unavailable -> known
    # encounters only.
async def resolve_character(value: str, *, session: AsyncSession, tenant_id: UUID)
        -> ResolvedCharacter
    # The tenant's user_characters (own + friends) and known_players; "Name-Realm" narrows a
    # name shared across realms. Never reads another tenant (explicit tenant predicate + RLS).
```

Aliases (the only new data; each target is checked against the roster at lookup time):
classes `warr, war, dh, dk, pally, pal, lock, hunt, sham, evo, mon` …; specs `ret, prot, resto,
disc, bm, mm, sv, arc, aff, demo, destro, enh, ele, ww, mw, bm, aug, dev, pres, sub, sin, veng,
bdk, ufk` … (the final list lives in the module; tests cover the AC's ten).
