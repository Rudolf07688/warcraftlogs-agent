# contract:mechanics-tool (as built)

`get_boss_mechanics(ability: str, encounter: str | None = None) -> dict`, in `KB_TOOLS` ("Stored knowledge").

- Hit: `{"status": "success", "found": true, "encounter", "ability", "ability_ids": [int], "what_it_does",
  "what_to_do", "source": {"name", "url"}, "patch"}`.
- Miss: `{"status": "success", "found": false, "message": "Not in my mechanic guides."}`; when the ability exists
  under another boss than the one named (or under several, none named): plus `"found_under": [boss names]`, and
  with a known named boss the message is `"Not in my mechanic guides for <boss>."`.
- Bad argument (empty, over 100 chars, not a string): `{"status": "error", "error_message": <fixed text>}`.
