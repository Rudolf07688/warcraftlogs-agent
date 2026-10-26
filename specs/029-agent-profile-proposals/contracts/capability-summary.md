# Contract: capability summary (sc-204)

Design: C1–C4. Decisions D13 (app-facts line). Research R3, R4.

## Python API

```python
# wcl_agent/capabilities.py (new)
CAPABILITY_SUMMARY_MAX_CHARS = 4000
MAX_TOOL_LINE_CHARS = 160

@dataclass(frozen=True)
class ToolGroup:
    label: str            # e.g. "Report deep-dive (one log)"
    tools: tuple          # plain functions or ADK BaseTool instances
    note: str = ""        # group rule; only the backend profile group sets one

def render_capability_summary(groups: Sequence[ToolGroup], *, web_search: bool) -> str: ...

# wcl_agent/agent.py
TOOL_GROUPS: tuple[ToolGroup, ...]           # the WCL tools, grouped like today's comments
TOOLS: list                                  # flattened TOOL_GROUPS, kept for existing imports
def build_instruction(ctx=None, *, capabilities: str = "") -> str: ...
def build_agent(model=DEFAULT_MODEL, retry=None, *, extra_groups: Sequence[ToolGroup] = ()) -> Agent: ...
INSTRUCTION: str                             # root_agent's instruction (CLI / Gemini snapshot)
```

`build_agent` builds `groups = [*TOOL_GROUPS, *extra_groups]`, plus
`ToolGroup("External knowledge", (web_search_tool,))` for non-Anthropic models. It then
renders the summary and registers `tools=[t for g in groups for t in g.tools]`, so the
summary and the registered list come from the same object. The instruction provider is
`functools.partial(build_instruction, capabilities=summary)`.

**For 030 (one-line registration after 029 merges)**: add the participant tool to the
`tools` tuple of the "Report deep-dive" group in `TOOL_GROUPS`. It then shows up in `TOOLS`,
in the registered list and in the summary with no other edit. Its docstring's first
paragraph becomes its summary line (≤ 160 characters, no braces).

## Rendered text (order fixed; tool lines generated)

```
Use only tools exposed in this session. Combine them freely; when a question needs several
independent lookups, issue those tool calls together in parallel rather than one at a time.

<Group label>[ (<note>)]:
- <tool name>: <first paragraph of its description, ≤ 160 chars per line>
...
[No web search in this session: say current-patch verification was not possible.]   # web_search=False
[You can change: …own characters and friends, including raid roles, only by proposing…]  # a group has a note
[In the app (the user does these themselves): the Profile page (…), … the model picker.]  # a group has a note
You cannot: …                                                                          # always; wording per profile group
```

## Invariants (asserted by tests)

1. Adding a tool to a group adds its line; removing it removes the line; no prose changes.
2. For the backend's largest set (Gemini + web_search + profile group) the summary is ≤ 4,000
   characters, and every line is ≤ 160.
3. Every registered tool has a docstring (non-empty description).
4. The fixed `<TOOLS>` section of `_INSTRUCTION_BODY` contains no registered tool name (it is
   just the token). The rendered instruction contains every registered tool name.
5. Without web search (Claude), the "No web search" line is present. With it, `web_search`
   has a line.
6. Without the profile group (CLI `root_agent`), no "You can change" or "In the app" line.
7. No `{` or `}` anywhere in the rendered instruction.
8. The `<CURRENT_TIME>` block stays last (PERF-003). The summary sits before it, in the
   cacheable prefix.
