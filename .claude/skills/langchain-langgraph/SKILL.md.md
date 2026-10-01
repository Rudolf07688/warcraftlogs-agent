---
name: langchain-langgraph
description: Usage guide for LangChain v1.2 and LangGraph v1.3 (Python) — streaming, message/state internals, tool-call propagation in deep/multi-agent graphs, and Vertex AI-specific gotchas. Load when building, debugging, or reviewing LangGraph agents.
---

# LangChain v1.2 / LangGraph v1.3 — Engineering Reference

## 1. Core mental model

LangGraph runs a **Pregel-style super-step loop**: each super-step activates all nodes with pending messages on their input channels, runs them (in parallel if independent), then applies their returned updates via **reducers** before the next super-step[web:1]. Checkpoints are written **at super-step boundaries, not mid-function** — if a node is interrupted or retried, it re-runs *from the start of its function*, so any side effects before an `interrupt()` or an external call must be idempotent[web:1].

## 2. State keys and reducers — "what happens behind the scenes"

- Every state key has an independent reducer. No `Annotated` reducer = **default reducer** = last-write-wins (right overwrites left)[web:1].
- `Annotated[list[X], operator.add]` = simple append; doesn't dedupe or handle ID-based updates.
- `messages: Annotated[list[AnyMessage], add_messages]` (or subclass `MessagesState`) is the standard pattern. `add_messages` does three things silently: appends new messages, **overwrites existing messages by matching `.id`** (critical for HITL edits), and **deserializes dict/plain inputs into LangChain Message objects**[web:1]. This is why you should always access `state["messages"][-1].content` via dot notation, not raw dicts, once `add_messages` is the reducer.
- `Overwrite` type lets you bypass a reducer for one update when you explicitly need last-write-wins on a normally-accumulating key[web:1].
- **Gotcha — private channels leak on `stream_mode="values"`**: input/output schema filters only constrain `invoke()` return values and node inputs. Streaming `"values"` emits **all** state channels by default, including ones you scoped as "private" or output-only. Use `output_keys=[...]` on `stream`/`stream_events` if you need to hide internal scratch keys from consumers[web:1].

## 3. Streaming modes — what each one actually gives you

| Mode | What you get | Notes |
|---|---|---|
| `values` | Full accumulated state after each step | Includes private channels (see above) |
| `updates` | Only the delta a node just returned, keyed by node name | Multiple nodes in one super-step stream as separate events |
| `messages` | `(token_or_message_chunk, metadata)` tuples from any LLM-invoking node | `metadata["langgraph_node"]` tells you which node emitted it |
| `custom` | Arbitrary payloads pushed via `get_stream_writer()` inside a node/tool | Only way to stream data not tracked as a state channel |

You can pass a list, e.g. `stream_mode=["messages", "updates"]`, and each chunk is `{"type": ..., "data": ...}`[web:2].

**v1.3 addition — typed event streaming (`stream_events(..., version="v3")`)**: gives you separate iterators/projections — `.messages`, `.tool_calls`, `.subagents`, `.values` — that you can `interleave()` instead of branching on `chunk["type"]` manually. This is the recommended API for new code going forward, especially for multi-agent/subagent graphs[web:2][web:3].

### Practical pattern: streaming tokens AND completed messages
`stream_mode="messages"` alone only gives incremental `AIMessageChunk`s — tool call args arrive as fragmented JSON strings (`tool_call_chunks`), not parsed tool calls. To get the **completed, parsed** `AIMessage.tool_calls` / `ToolMessage`, combine with `updates`: `stream_mode=["messages", "updates"]` and read the completed message off the `updates` event for that node[web:2].

### Reasoning/thinking tokens
Filter `message.content_blocks` (or the v1.3 `.reasoning` projection) for blocks of `type == "reasoning"`. LangChain normalizes Anthropic `thinking` blocks and OpenAI reasoning summaries into this same shape — but the underlying model must have reasoning enabled (e.g. `ChatVertexAI(include_thoughts=True)` for Gemini thinking models)[web:2][web:4].

## 4. Tool call and message propagation in deep/multi-agent graphs

- A model node returns an `AIMessage` with `tool_calls` → the graph routes to a tools node → each tool call produces a `ToolMessage` (matched back via `tool_call_id`) → routes back to the model node. This is the `create_agent` ReAct loop; you see it as three `updates` events per tool round-trip[web:2].
- **Tools can return `Command`** to simultaneously update state and route control flow (`update=` + `goto=`), instead of just a string result. Useful for tools that need to write to a state key other than `messages`, or short-circuit to a different node[web:1].
- **Subgraphs / handoffs**: a node inside a subgraph can jump straight to a node in the **parent** graph via `Command(goto="node_x", graph=Command.PARENT)`. This is the mechanism behind multi-agent handoff patterns[web:1].
  - **Gotcha**: if the key you update via that `Command` exists in both parent and subgraph state schemas, the **parent graph must define a reducer for it**, or the update silently overwrites/errors depending on shape.
- **Deep agents / subagents (`deepagents` package, built on LangGraph)**: the main agent delegates via a `task()` tool call to a subagent. The supervisor **blocks until the subagent finishes** and only the *final result* is returned to the parent — the subagent's internal tool calls and intermediate messages are isolated from the parent's context window (this is the whole point: context quarantine)[web:5].
  - Custom subgraphs used as `CompiledSubAgent` **must** expose a `"messages"` state key — that's the calling contract[web:5].
  - Runtime `context` passed into the parent propagates down to subagents and their tools automatically; skills/permissions do **not** propagate by default (isolated per subagent) unless explicitly inherited[web:5].
  - Streaming subagents: use the v1.3 `stream.subagents` projection to get per-subagent handles (`.name`, `.messages`, `.tool_calls`, `.status`, `.output`) rather than trying to demux `updates` events by hand[web:5].

## 5. `Command` and `Send` — routing internals

- `Command(update=..., goto=...)` combines a state update with routing in one return value from a node **or a tool**. You must annotate the node's return type (`-> Command[Literal["other_node"]]`) so the graph builder can register the dynamic edge[web:1].
- **Gotcha**: `Command(goto=...)` does **not** disable statically-defined `add_edge(...)` edges from the same node — both execute. Pick one routing mechanism per node (static edges *or* dynamic `Command`/conditional edges), never mix, or you'll get duplicate/unexpected parallel branches[web:1].
- `Send(node_name, state)` is for map-reduce fan-out where the number of downstream invocations isn't known ahead of time (e.g., generate N sub-tasks, run a node once per task)[web:1].
- **Gotcha — `Command(resume=...)` vs plain dict input**: `Command(resume=...)` (after an `interrupt()`) resumes from the **last checkpointed super-step**, not `__start__`. If you mistakenly pass `Command(update={"messages": [...]})` as input to continue a *finished* multi-turn conversation, the graph looks "stuck" because it's trying to resume a completed run instead of starting fresh. To continue a conversation, pass a plain dict `{"messages": [...]}`; reserve `Command(resume=...)` strictly for continuing after an active `interrupt()`[web:1].

## 6. Interrupts and idempotency gotchas

- `interrupt()` pauses the node; the graph checkpoints and returns control to your app. Resuming replays the **entire node function from its top** — everything before the `interrupt()` call re-executes, including any DB writes, API calls, or tool invocations[web:1].
- Fix: wrap side effects before/around `interrupt()` in idempotency keys or upserts, or move them into a `@task`-decorated function — task **results** are checkpointed independently and skipped on resume, unlike plain code in a node[web:1].
- Same determinism caveat applies to any `task()` calls inside a node: reordering tasks/interrupts in code between runs can desync cached results from the checkpoint.

## 7. Google Vertex AI specifics (`langchain-google-vertexai`)

- `ChatVertexAI` is explicitly flagged as **deprecated in favor of `ChatGoogleGenerativeAI`** (the `google_genai:` provider prefix) in current reference docs — for new agent builds prefer `model="google_genai:gemini-<version>"` over instantiating `ChatVertexAI` directly, even though both currently work[web:4].
- Auth resolves via `google.auth` — ADC, `GOOGLE_APPLICATION_CREDENTIALS`, or workload identity, in that order; no API key path like Gemini-direct.
- Tool calling: `bind_tools()` works the same as other providers and returns the same normalized `.tool_calls` shape, but responses carry Vertex-specific `response_metadata` (`safety_ratings`, `is_blocked`, `citation_metadata`) — if you build guardrail middleware, check `is_blocked` here rather than assuming empty content means "no output"[web:4].
- Thinking/reasoning: set `thinking_budget` + `include_thoughts=True` on the model to get reasoning content blocks; without `include_thoughts=True` the reasoning tokens are consumed but never surfaced to your stream, which silently breaks the "stream thinking tokens" pattern described in section 3 if you forget it[web:4].
- Streaming chunks accumulate via `chunk_a + chunk_b`; usage metadata typically only appears on the **final** chunk, not every delta — don't sum per-chunk usage_metadata, read it off the last chunk or the aggregated message[web:4].
- Built-in Google tools (`google_search`, `code_execution`) are passed as raw `google.cloud.aiplatform_v1beta1.types.Tool` objects, not LangChain `@tool` functions — mixing these with `bind_tools()`-style custom tools has different call/response shapes; test tool-call propagation through your graph separately for native vs. custom tools[web:4].

## 8. Quick gotcha checklist

- Reducer-less keys are last-write-wins — a second node writing the same key silently discards the first node's update.
- `add_messages` overwrites by `.id`; passing a manually-constructed message without preserving the original `.id` when trying to "edit" it will append instead of replace.
- Private/internal state channels are visible on `stream_mode="values"` unless you pass `output_keys`.
- Never mix static `add_edge` and `Command(goto=...)`/conditional-edge routing from the same node.
- `Command(update=...)` alone as `invoke()`/`stream()` input is only valid for resuming — not for new turns.
- Idempotency required for anything before `interrupt()` or inside a retried node.
- Subgraph → parent `Command(graph=Command.PARENT)` updates need a matching reducer defined in the **parent's** schema.
- Deep-agent subagents isolate context by design — don't expect the parent to see subagent tool calls in `updates`; use `stream.subagents` (v1.3) instead.
- Prefer `google_genai:` provider strings over direct `ChatVertexAI()` instantiation for new work — it's the currently recommended path.
- Always set `include_thoughts=True` on Vertex/Gemini thinking models if you plan to stream reasoning — otherwise those tokens vanish from the stream silently.
</content>