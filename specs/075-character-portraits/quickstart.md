# Quickstart: 075

1. Set `BLIZZARD_CLIENT_ID` / `BLIZZARD_CLIENT_SECRET` in `.env` (https://develop.battle.net), restart the backend.
2. Open the profile page: characters render at once; portraits fill in.
3. `curl -b cookie http://localhost:8000/api/profile/portraits` shows the URLs; a second call within a day makes no Blizzard request (the `char_portrait` family counts hits on the admin cache stats).
4. Without the credentials every `portrait_url` is null and no request leaves the backend.
