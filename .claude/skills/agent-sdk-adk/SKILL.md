---
name: google-adk-a2a-python-patterns
description: |
  Use this skill when implementing, exposing, or consuming Google ADK agents in Python, especially when integrating ADK with A2A and MCP. Covers implementation patterns from the Google ADK A2A conversion guidance and official Python ADK samples, including agent structure, entrypoints, async runtime flow, task execution bridging, response shaping, orchestration patterns, and common gotchas.
---

# Google ADK A2A Python Patterns

## Purpose

Use this skill when building Python agents with Google ADK, especially when:
- exposing an ADK agent over A2A,
- connecting an ADK agent to MCP tools,
- building an orchestrator agent that delegates to other agents,
- reasoning about ADK runtime flow, async execution, and response handling,
- translating between ADK-native agent execution and A2A task semantics.

This skill focuses on practical implementation patterns rather than product marketing or high-level concepts.

## Core Mental Model

Treat Google ADK as the **agent implementation layer** and A2A as the **inter-agent protocol layer**.

- ADK defines how the agent thinks, uses tools, stores state, and runs.
- MCP gives the agent access to external tools.
- A2A exposes the agent to other agents as a network-accessible capability.

Do not mix these concerns together.

Recommended split:
- `agent.py` contains ADK agent construction and core business logic.
- `__main__.py` exposes public identity and starts the A2A-facing app.
- `task_manager.py` bridges A2A task execution into ADK runtime invocation.
- optional orchestrator utilities handle discovery and delegation separately.

## Recommended Project Shape

A strong ADK + A2A Python layout looks like this:

```text
my_agent/
  __init__.py
  agent.py
  task_manager.py
  __main__.py
  requirements.txt
```

Recommended responsibilities:
- `agent.py`: build the ADK `LlmAgent`, define tools, and provide an invocation method.
- `task_manager.py`: implement the A2A executor interface and translate tasks into agent execution.
- `__main__.py`: define `AgentSkill`, `AgentCard`, server wiring, and runtime entrypoint.
- `__init__.py`: keep package import clean.

This separation keeps the ADK logic testable and the A2A surface replaceable.

## Agent Construction Pattern

Build the ADK agent first as a self-contained unit.

Recommended steps:
1. Create an `LlmAgent` with a precise role.
2. Attach tools or toolsets explicitly.
3. Keep the business prompt close to the agent definition.
4. Keep external configuration out of prompts and inject via environment or config.
5. Provide one clear invocation boundary that the A2A bridge can call.

When MCP is involved, initialize `MCPToolset` in the agent construction layer rather than scattering MCP setup across the runtime.

Pattern:
- define the ADK model,
- attach tools/toolsets,
- return the root agent object.

## MCP Integration Pattern

When ADK uses MCP, configure MCP as part of agent construction.

Guidance:
- Treat the MCP server as infrastructure, not as business logic.
- Pass secrets such as API keys via environment variables.
- Keep MCP startup or connection parameters centralized.
- Avoid embedding environment or host-specific values directly in prompts.

If using a launched MCP process or server, document clearly:
- startup mechanism,
- required environment variables,
- expected transport,
- timeout behavior,
- failure mode when the tool server is unavailable.

## Public Identity Pattern

An A2A-exposed ADK agent needs a public identity separate from its internal logic.

Define this in `__main__.py` with:
- one or more `AgentSkill` declarations,
- one `AgentCard`,
- application/server startup wiring.

### AgentSkill Guidance

Use `AgentSkill` to advertise externally visible capability, not internal implementation details.

Each skill should include:
- stable `id`,
- human-readable `name`,
- short, precise `description`,
- examples that show when the skill should be used.

Good skill descriptions behave like API documentation for another agent or planner.

Rule:
- describe outcomes,
- not model names,
- not chain internals,
- not vague marketing phrases.

### AgentCard Guidance

The `AgentCard` is the discovery contract.

Include:
- name,
- description,
- URL,
- version,
- supported skills,
- capabilities such as streaming,
- default input/output modes.

Make sure the card describes what another agent needs to know to call the service successfully.

Do not let the card drift away from actual behavior. If the agent only returns text, do not advertise broad multimodal outputs. If streaming is not implemented end-to-end, do not mark it enabled.

## Exposing ADK as A2A

Google's documented pattern is to convert an existing ADK agent into an A2A-compatible component instead of rewriting the core agent for networking.

There are two practical exposure patterns:

### 1. `to_a2a()` Wrapper

Use this when you want the fastest path to exposing an ADK agent.

Recommended when:
- the ADK agent already works,
- the public contract is simple,
- you want ADK to generate the A2A surface with minimal boilerplate.

Benefits:
- minimal glue code,
- fast iteration,
- strong fit for demos and small services.

Caution:
- this is convenient, but less explicit than a custom task bridge when you need advanced lifecycle control.

### 2. Explicit Task Bridge

Use a dedicated task manager that implements the A2A executor interface.

Recommended when:
- you need to control task lifecycle carefully,
- you want streaming progress updates,
- you need explicit cancellation behavior,
- you want precise response shaping,
- you need to map ADK runner events to A2A events deliberately.

This is the better pattern for serious orchestration systems.

## Task Manager Pattern

The task manager is the bridge between protocol and implementation.

Responsibilities:
- receive A2A task input,
- extract relevant user message content,
- invoke the ADK runtime,
- translate intermediate and final ADK events into A2A task updates,
- handle exceptions and cancellation,
- enqueue results onto the A2A event queue.

A strong task manager should:
- separate parsing from execution,
- treat task status transitions explicitly,
- emit progress if the workload is long-running,
- convert final ADK output into a stable A2A artifact structure.

Implementation rule:
Do not put all orchestration, parsing, and response shaping into one monolithic `execute()` block. Keep helper methods for:
- input extraction,
- ADK invocation,
- event translation,
- final artifact construction,
- failure handling.

## Async Runtime Pattern

ADK execution in this context should be treated as **async and eventful**, not as a single blocking function call.

Google's documented A2A conversion flow uses an invoke method that runs the ADK `Runner` and yields events asynchronously as execution progresses.

Recommended model:
- task manager receives request,
- task manager calls an async `invoke()` method on the agent wrapper,
- `invoke()` runs ADK runtime and yields events,
- task manager maps these events to A2A task updates and final artifacts.

This is the right place to support:
- incremental progress,
- partial outputs,
- internal checkpoints,
- long-running task status.

Do not collapse all ADK events into one final string unless the use case is truly trivial.

## Response Shaping

Translate ADK outputs into A2A-friendly structures deliberately.

Recommended response strategy:
- keep the final human-readable answer in a text payload,
- include structured JSON when downstream automation matters,
- emit final artifacts rather than raw internal runtime state,
- normalize output shape across runs.

Good final output shape typically includes:
- concise summary for human readers,
- machine-readable data object when available,
- references or file outputs when produced.

Bad practice:
- leaking raw internal event objects,
- returning inconsistent schemas across branches,
- exposing prompt fragments or intermediate chain internals unnecessarily.

## Streaming and Progress

If the ADK agent can emit meaningful intermediate progress, map that into A2A updates.

Good uses of streaming:
- long-running retrieval or research,
- multi-stage pipelines,
- operations that benefit from visible status,
- workflows where orchestrators may react to progress.

Bad uses of streaming:
- streaming every tiny internal token,
- exposing noisy model chatter,
- sending partial output that is not actionable.

Rule of thumb:
stream **status**, not thought process.

Examples of good progress messages:
- "Fetching requested documents"
- "Running extraction on 12 pages"
- "Synthesizing final answer"

## Orchestrator Pattern in ADK

Google's A2A orchestration pattern is:
1. discover available agents,
2. call them through the A2A client layer,
3. expose discovery and delegation as tools to an orchestrator `LlmAgent`.

This means the orchestrator itself is just another ADK agent, but its tools are:
- discovery,
- delegation,
- maybe task polling or callback registration.

Recommended orchestrator design:
- one discovery function that returns agent metadata from a registry or config source,
- one delegation function that wraps `a2a.client` request construction,
- one clear planner instruction set telling the LLM when and how to delegate.

Important rule:
The descriptions of sub-agents are effectively API documentation for the orchestrator's LLM. Poor descriptions lead to poor routing.

## Discovery Pattern

A practical orchestrator needs to know what remote agents exist.

Recommended development approach:
- start from static configuration or a known registry endpoint,
- load Agent Cards,
- cache the subset of fields the orchestrator actually needs,
- inject those details into planning context.

Do not assume an A2A environment automatically provides a global registry. Keep discovery explicit.

## Delegation Function Pattern

A delegation helper should:
- resolve the target agent endpoint,
- construct a `SendMessageRequest`,
- submit the task,
- handle async task semantics,
- normalize the result back into orchestrator-friendly output.

Keep this helper deterministic and observable.

It should log:
- chosen target agent,
- outgoing task ID or request ID,
- lifecycle transitions if polled,
- normalized final result.

Do not hide protocol failures inside vague natural-language fallbacks.

## State Management in ADK

ADK patterns rely heavily on session and state. Treat `session.state` as shared working memory for multi-step flows.

Recommended rules:
- use descriptive keys,
- keep state small and purposeful,
- write outputs that downstream steps actually need,
- avoid dumping entire raw event trees into state,
- treat state as contract, not scratch chaos.

If a sub-agent writes to state for another sub-agent to consume, document the key names clearly.

## Description Quality Matters

In ADK multi-agent patterns, descriptions are not fluff. They are routing metadata.

This applies to:
- sub-agent descriptions,
- tool descriptions,
- `AgentSkill` descriptions,
- orchestrator instructions.

Write descriptions so another model can answer:
- what does this component do,
- when should it be chosen,
- what kind of input does it expect,
- what kind of output does it return.

Avoid descriptions like:
- "helpful assistant",
- "handles many tasks",
- "does web stuff",
- "smart reasoning agent".

## Response Structure Guidance

For ADK agents exposed through A2A, aim for stable output contracts.

Recommended practice:
- always return the same high-level result shape,
- include success/failure semantics clearly,
- use explicit fields for final answer, structured data, and attachments,
- convert internal ADK output into public response schema before returning.

For orchestration-heavy systems, define one normalized result model even if different workers use different frameworks internally.

## Error Handling Pattern

Design for these failures explicitly:
- MCP tool unavailable,
- model timeout,
- downstream A2A call failure,
- malformed agent card,
- task canceled mid-run,
- partial progress emitted before failure.

Recommended handling:
- move task to a terminal failure state cleanly,
- provide readable failure summary,
- log structured diagnostics separately,
- never return ambiguous partial success unless the schema supports it.

## Cancellation Pattern

If the A2A executor interface requires `cancel`, implement it intentionally.

At minimum:
- mark the task as cancelable only if runtime supports interruption,
- propagate cancellation to long-running subtasks where possible,
- prevent orphaned background work,
- emit a final canceled state explicitly.

Do not leave `cancel` unimplemented in production without understanding the consequence.

## Deployment and Entry Point Guidance

Keep the deployable entrypoint focused.

Recommended `__main__.py` responsibilities:
- load config,
- build or import the root agent,
- define skill/card metadata,
- wire task manager to the server,
- start the app.

Do not bury agent creation behind side effects that only work in one environment.

Keep environment requirements explicit:
- model provider config,
- Vertex settings if used,
- MCP API keys,
- network endpoints,
- runtime mode.

## Local Development Pattern

For local ADK + A2A development:
- validate the ADK agent first without networking,
- then validate A2A exposure,
- then validate remote consumption,
- then validate orchestrator behavior.

Recommended sequence:
1. run the core ADK agent locally,
2. validate tools and prompts,
3. expose through A2A,
4. inspect Agent Card,
5. send direct test requests,
6. add orchestrator delegation,
7. only then add gateway or platform complexity.

## Testing Guidance

Test at three layers:

### 1. ADK Unit Tests
- agent prompt and tool behavior,
- state transitions,
- expected tool calls,
- response normalization.

### 2. A2A Contract Tests
- Agent Card validity,
- request schema,
- task lifecycle,
- cancellation behavior,
- streaming behavior if enabled.

### 3. System Tests
- orchestrator chooses correct downstream agent,
- MCP tools are reachable,
- task completes or fails predictably,
- results preserve required structure.

## Common Gotchas

### 1. Blurring agent logic and network surface
Keep ADK logic independent from A2A wiring.

### 2. Advertising capabilities you do not actually support
Do not mark streaming or output modes that are only partially implemented.

### 3. Weak skill descriptions
Poor `AgentSkill` descriptions make orchestration brittle.

### 4. Returning raw ADK runtime output
Translate runtime events into stable public responses.

### 5. Treating async execution as sync text generation
Long-running workflows need explicit lifecycle handling.

### 6. Hardcoding registry or endpoint assumptions
Keep discovery explicit and configurable.

### 7. Overloading prompts with infrastructure concerns
Prompts should express role and behavior, not operational config.

### 8. Ignoring session.state contract quality
Messy shared state causes multi-agent pipelines to drift.

### 9. Skipping cancellation and failure semantics
Task systems need clear terminal states.

### 10. Assuming the orchestrator will infer everything
Sub-agent, tool, and skill descriptions must do real work.

## Recommended Engineering Rules

Use these rules consistently:
- Build the ADK agent first; expose second.
- Keep public A2A identity in `__main__.py`.
- Use a dedicated task bridge for non-trivial lifecycle control.
- Treat ADK runner output as async events.
- Normalize public responses deliberately.
- Make skill descriptions concrete and operational.
- Keep discovery and delegation as separate functions.
- Use structured state keys in multi-agent flows.
- Do not promise protocol features you have not tested end-to-end.

## Best Fit Use Cases

This skill is well suited for creating:
- ADK agents exposed over A2A,
- ADK agents using MCP toolsets,
- orchestrator agents that delegate to remote specialists,
- engineering patterns for async multi-agent systems on Python,
- implementation guides for ADK + A2A backends,
- team conventions for ADK agent structure and response contracts.
