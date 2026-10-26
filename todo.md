# ----- To Do ----- #
Ticket IDs refer to the Shortcut "Team 1" board.

## Agent / AI
- Add symmantic search vector store `epic-100`
  - Look for data related to the user's query or whatever the agent decides would be a good search term.
  - Essentially used as a cache to speed up api call waiting.
  - Agent must be able to run more than one search terms in parallel
- Add a "spin up sub-agent" tool call `epic-101`
  - Agent creates an agent with a prompt (all tools available)
  - Long term: Give subagent REPL enviroment
- Agent skills for how to assess WoW numbers in terms of performance `sc-149`
- API rate limits `sc-163`
  - The agent is making too many requests to build the class guides, running out of request before completing the guide.
  - We must put together some agent skill or pattern to help the agent find the information it needs quicker and easier.
- If current model returns 429 errors, switch to the second available model in class `sc-164` `sc-176`
  - If already switch, switch back to the first model
    - If it still gives 429s then report that to the user and ask to try again in a bit.
- Self-aware agent `epic-203`
  - Agent must be "self aware" of the harness it operates in, for example:
    - When asked "Add the characters from the dungeon to my friends, except the shamen" it should be able to add it to your character profile
  - Design docs: HTML architecture report with diagrams, animated arrows and the technologies per layer with the reasoning behind each choice `sc-209` `sc-210`
  - Feature design docs for the epic-203 build tickets (capabilities + profile tools; participants + in-chat confirmation) `sc-211` `sc-212`

## Data / Caching
- Implement redis - confirm browser cache usage. `sc-147`
- Every single fetch must be stored in the db `epic-103`
  - Over time we will have saved all relavent data, building up a massive database of information
  - I want to structure the app so that 80% of questions don't require external api calls (fast)
- Upload warcraftlogs file directly `epic-102`

## Infra / Platform
- Deployment / Hosting Plan `sc-146`
- Worker server (BIG - must be specced accordingly and done properly) `epic-196`
  - Have a separate container running for background tasks running independently
  - These tasks can include:
    - Building raid and dungeon guides continuously when new pieces of information are found
      - Keep the update profile small so it doesn't rate limit models and take forever to run.
    - Building up your profile bit by bit based off previous chat data ("offline" character profile, not user conversational memory)
  - NATS message queue to handle tasks and failures
    - (maybe deadletter, maybe retry queue?)
    - NATS backend / task state captured with postgres for persistent data requirements (including stuff like audit trails)
- Unstructured directory `./wcl_agent/*.py` `sc-150` `sc-171`

## Reports
- ~~PDF reports still look terrible with some html/markdown markers visible `epic-99`~~
  - ~~Need to use proper pdf generation~~

## UI / Design
- Chat interface redesign `epic-105`
  - mayby rather single-lane chat
  - Scroll to top of the question-message once answer is fully complete.
  - Chat bubbles to scale to a percentage of the width of screen, not fixed amount `sc-208`
- ~~Slightly increase default font size `sc-152`~~
- ~~Showing to many recent raids in the welcome chat `sc-153`~~
  - ~~Rather include some recent m+ runs as well when available~~
  - ~~6 raids and 6 dungeons max (most recent ones, in order)~~
- ~~In the left side bar, previous conversations must be above the "Raids" section. `sc-154`~~
  - ~~Generate conversation name based on the messages `sc-155`~~
- ~~Pinnabable chats `sc-165`~~
  - ~~In chat window and sidebar.~~
- Rework Raids page `epic-106`
  - Make tabs instead of dropdown
  - Show previously pulled data from that raid (participents, duration, my character's parse etc)
  - Add button to start a new chat with the current "analyze this raid" message
- Select which character this chat is about ("filter") with checkboxes on every chat `epic-107`
  - Default is no filter - all characters - more general overview unless asked specifically in chat
    - e.g. "How did my mage do on ..."
      - Bonus premium goal: the ai is able to change the UI filter button (as if the user clicked the filters in the UI) when a user asks a targeted question.
- On account creation take the player straight to the profile page and ask them to fill in at least one character `epic-162`
  - not forced / skippable
  - Also include a simple selector to select their main class
    - Also select main content (Raid / M+ or both)
    - This will start generating guides for that spec in the background.

## QA Hits
Medium findings still open:
- PERF-001: the app waits for model discovery before serving anything. `sc-156`
- SEC-003: remote images in model output can leak data. `sc-157`
- SEC-004: the login rate limit is shared by all users behind the proxy. `sc-158`
- SPEC-002 and SPEC-004: the missing startup log line, and a catalog response without models being read as empty. `sc-159`

---
# Done 
# ----- Phase 1 ----- #

1. Keep track of raid encounters I have previously asked about - give date/time on the UI and sort by that so I know which raids I'm looking at. 
  - When I click the specific raid encounter it must automatically start a new chat, sending the AI a prompt like "Please investigate this raid and highlight and important findings".
  - Store this in the postgres DB.
2. SessionId and chat messages and responses must also be saved to the db.
3. Add a web-search subagent as a tool to the agent.
4. The available models must be dynamically fetched from the available gemini and anthropic models on vertex. If there is a "health check" api, test with that, otherwise just try with a "hello" message and see if the llm responds.
5. Download PDF report with graphs and stuff.


# ----- Phase 2 ----- #

1. Agent must be able to predict follow-up questions the user might want know, for example "What are the parse scores for everyone?", and then render buttons (max 3) for the user to click to further prompt the agent.
2. Confirm parallel tool calls - make better - shared disk space for tool output the agent can pick up when done.
3. Fix chat window rendering whre response panel sizes seem fixed.
4. Your name is "Barnaby" the tavern / innkeeper. See your prompt. You can't be oberly nice and must emphasize the mistakes (in a fun way of course)
5. New background image `frontend/dist/assets/morgan-howell-img-1760.jpg`. Use that as the new background but keep it in and make it togglable from config.
6. Resizable side panel.

# ----- Phase 3 ----- #

1. Always paste links to the warcraftlogs url that you are sourcing information from (or just query patameters if easier).
2. Duplicating raids tracked in the side bar? 
  2.1 Display date and time of the raid encounter + boss name if applicable.
3. As specific bosses come up in the raid results, list them as checkboxes to send to the agent prompt to focus/filter on.
4. PDF report not working anymore. Previous render looked terrible.
5. When entering a new chat the backend must preemptively send a message to the agent, invisible to the user, saying "Greetings, Barnaby!" so the agent greets yoy with a warm greeting when you start.
  - To get this still feeling snappy, the greating prompt should be sent on application startup and cached for new chats during the session.

# ----- Phase 4 ----- #

1. Define self/friend characters for extra context.
  - Add guild name as well (limited to one main guild for current user)
  - responses are more focussed to guild members (unless answering unrelated questions)
2. Store / cache results for quick access.
3. Speed up tool calls (parallelize tasks? Run predefined workflows? Subagents?)
4. Implement MCP communication protocol, specifically (but not limited to), being able to render plots and artifacts
  - Perhaps use python plotly at the back and pass the json to the js plotly library so the graphs are nice and interactive.
5. The "Download pdf report" button should sit on a specific message reply as well - taking only that message (with required context to generate the answer) and generate almost "analytic" reports
6. When you lock in the names in the "Add a personal character" / "Add guild name" / "Add friend character", a background task should kick off that fetches and persists a guide to the characters' active spec for the agent to use in context.
7. Fix the rendering of agent responses such as: "Top players always open with: $$\text{Pre-cast Frostbolt} \longrightarrow \text{Icy Veins} \longrightarrow \text{Frozen Orb} \longrightarrow \text{Flurry/Spike Combo}$$"
  - Include rendering for mathmatical equations such as latex, or howwever the agent typicallt responds with.

# ----- Phase 5 ----- #
- Capture metadata details such as "Known Raids", "known players" etc. dynamically as tool calls are successful. This must be used as a sort of "cache" and help speed up follow-up other conversations app-wide.
- Improve PDF report downloads:
  - It shouldn't just be a copy of the conversation text.
  - It needs to extract information from the chat and generate a full report on what findings were discovered, not what was said.
  - The per-message report focussing doing the same, but only for the contents of that specific message.
- Improve profile setup
  - More than one friend
  - Roles for those characters (DPS/Tank/Healer)

# ----- Phase 6 ----- #
- Welcome page
  - Background fetch of your character's most recent raids.
    - Must be stored since it won't change
  - Clicking on one opens up a new chat.

# ----- Phase 7 ----- #
- ~~**Fix Class guides**~~
  - ~~Hallucinations~~
    - ~~Add better grounding~~
    - ~~Add an agent to review the guide after generation and agent must fix it first.~~
      - ~~Current datetime and exact patch version must be sent to agent context~~
  - ~~Devourer DH spec not showing~~
- ~~Show that report is being generated / downloaded while waiting~~
  - ~~Feels like it doesn't work~~

# ----- Moved from To Do (2026-10-26) ----- #
- ~~Rate limit llm for 429s (Done: 011)~~
  - ~~Also catch 429 timeouts as tool errors so it doesn't break the agent loop~~
- ~~[Small] Add option to add a multiple characters~~
- ~~Dashboard from previous pulled stats~~
  - ~~Use this data as cache layer to answer questions (maybe fill in a template?)~~ -> Redis
