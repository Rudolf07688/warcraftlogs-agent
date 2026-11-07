# Data model: 072 (response only, no storage change)

- `RaidSummary`: report_code str; has_data bool; duration_ms int|null; participants
  list[Participant] (≤ 100); my_characters list[MyCharacter]; fetched_at datetime|null.
- `Participant`: name str (≤ 60, neutralised); class_name str|null; spec str|null;
  role "tank"|"healer"|"dps"|null.
- `MyCharacter`: name, class_name, spec as above; parses list[Parse] (≤ 50).
- `Parse`: encounter str|null; difficulty str|null ("Mythic", "Heroic", "Normal", "LFR");
  percentile float 0–100|null.
