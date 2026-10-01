---
name: a2a-protocol-practical-deep-dive
description: |
  Use this skill when working with Agent2Agent (A2A) protocol design, implementation, debugging, or architecture. Covers A2A mental models versus MCP, Agent Cards, JSON-RPC message structure, task lifecycle, push notifications, streaming, Python SDK usage, and practical swarm/orchestrator patterns for multi-agent systems.
---

# A2A Protocol Practical Deep Dive

## Purpose

Use this skill when an agent needs to reason about, design, implement, or debug systems that use the Agent2Agent (A2A) protocol. This includes architecture planning, protocol-level payload design, Python server/client implementation, long-running task orchestration, push-notification workflows, and multi-agent delegation patterns.

This skill is especially relevant when:
- Building interoperable agents across different frameworks.
- Exposing an agent as an A2A server.
- Connecting orchestrator agents to worker agents.
- Modelling long-running tasks with async completion.
- Comparing A2A with MCP.
- Inspecting Agent Cards, tasks, messages, or artifacts.

## Core Model

Treat A2A as **agent-to-agent task delegation**, not as a tool call.

- **MCP** is for agent-to-tool communication.
- **A2A** is for agent-to-agent communication.
- MCP usually feels like invoking a capability directly.
- A2A means handing work to another autonomous system that owns its own reasoning loop, tools, prompts, memory, and execution path.

When using A2A, assume the remote agent is opaque. Do not rely on its internal chain, tool layout, or reasoning implementation. Interact only through the protocol surface it exposes.

## When To Choose A2A

Prefer A2A when:
- The remote system is itself an autonomous agent.
- The work may be long-running or multi-turn.
- The remote side may need clarification or confirmation.
- You need framework interoperability.
- You want the remote agent to return structured artifacts, files, or progressive updates.

Prefer MCP when:
- You are exposing tools, resources, or prompts to one agent.
- The caller should control invocation directly.
- The capability is better modelled as a function or resource access pattern.

## Protocol Fundamentals

A2A communication typically uses HTTP plus JSON-RPC 2.0 payloads.

The key mental hierarchy is:

```text
Context
  └── Task
        └── Message
              └── Part
```

Definitions:
- **Context**: optional grouping across related work.
- **Task**: the stateful unit of work.
- **Message**: one turn from a user or agent.
- **Part**: the atomic payload unit inside a message or artifact.

Common part types:
- **TextPart**: natural-language content.
- **DataPart**: structured JSON payloads.
- **FilePart**: binary or URI-based file references.

## Agent Card

Before calling an A2A agent, fetch its Agent Card from:

```text
/.well-known/agent-card.json
```

Use the Agent Card to understand:
- agent name and description,
- available skills,
- supported transports,
- input/output MIME types,
- authentication schemes,
- protocol capabilities such as streaming or push notifications.

Treat the Agent Card as the contract for discovery and delegation. If you are building an orchestrator, inject relevant card details into planning logic or prompts so the orchestrator can decide which remote agent should receive a task.

## Task Lifecycle

Model A2A work as a lifecycle, not a synchronous response.

Typical states:

```text
submitted -> working -> input-required -> working -> completed
                                   \-> failed
                                   \-> canceled
                                   \-> auth-required
```

Guidance:
- `submitted` means accepted.
- `working` means active processing.
- `input-required` means the remote agent needs more information before it can continue.
- `auth-required` means downstream credentials or authorization are needed.
- `completed`, `failed`, and `canceled` are terminal.

Do not force A2A into a request-response-only model. If a workflow may require confirmation, review, or delayed completion, preserve the task lifecycle explicitly.

## Common Methods

Know these methods first:
- `message/send`: send a message and start or continue a task.
- `message/stream`: send a message and receive streaming updates.
- `tasks/get`: fetch current task state.
- `tasks/cancel`: cancel an in-progress task.
- `tasks/pushNotificationConfig/set`: register a webhook for async updates.

Default implementation advice:
- Use `message/send` for most orchestrated task submissions.
- Use `tasks/get` for authoritative state reads.
- Use push notifications for long-running workflows where the client should not hold an open connection.
- Use `message/stream` only when streaming is materially useful.

## Payload Design

A2A messages should separate human-readable instruction from machine-readable structure.

Recommended pattern:
- Put the plain-language request in a `TextPart`.
- Put structured parameters in a `DataPart`.
- Return both readable output and structured output when possible.

Example request shape:

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "messageId": "msg-001",
      "contextId": "ctx-123",
      "parts": [
        { "kind": "text", "text": "Investigate incident INC-123 and suggest next actions." },
        { "kind": "data", "data": { "incidentId": "INC-123", "dryRun": true } }
      ]
    }
  }
}
```

Recommended response design:
- return task metadata immediately,
- later return artifacts,
- include `TextPart` for readability,
- include `DataPart` for downstream automation,
- include `FilePart` when generated assets matter.

## Push Notifications

Use push notifications for long-running tasks.

Recommended pattern:
1. Submit the task.
2. Register a webhook with `tasks/pushNotificationConfig/set`.
3. Accept async callbacks for status and artifact updates.
4. After receiving a webhook, call `tasks/get` to confirm authoritative state.

Important rule:
Treat the webhook as a notification signal, not the sole source of truth. Always reconcile with `tasks/get` before final state changes in your application.

## Streaming

Use streaming when you need progressive updates over one live connection.

Typical event categories:
- status updates,
- artifact updates,
- final completion.

Avoid streaming when:
- the caller is a chat UI that does not need live token-by-token feedback,
- tasks are long-running and webhook completion is cleaner,
- you want simpler retry and recovery semantics.

## Authentication

A2A authentication is handled at the HTTP layer, not inside the JSON-RPC payload.

Use Agent Card security declarations to determine the required auth mechanism. Common options include bearer tokens, API keys, OAuth2, and mTLS.

Implementation rule:
- Read auth requirements from the Agent Card.
- Acquire credentials out-of-band.
- Send credentials in HTTP headers.

## Orchestrator Patterns

There are three common patterns for deciding which agents talk to each other.

### 1. LLM-Driven Delegation

Use this when tasks are open-ended.

Pattern:
- discover remote agents,
- read their Agent Cards,
- inject skills and descriptions into planner context,
- expose a delegation primitive such as `send_task(agent_name, task_description)`,
- let the LLM decide which agent to call.

Use when the orchestrator should reason dynamically about which specialist is most appropriate.

### 2. Deterministic Routing

Use this when workflows are structured.

Pattern:
- map message types, NATS subjects, or request metadata to fixed downstream agents,
- invoke those agents directly,
- avoid LLM routing overhead.

Use when predictability and cost control matter more than flexible delegation.

### 3. Agent-Initiated Peer Delegation

Use this for true swarm-style systems.

Pattern:
- any agent may also act as an A2A client,
- the agent discovers another agent's card,
- delegates a subtask,
- incorporates the result into its own response.

Use only when endpoint discovery, trust boundaries, and task ownership are well defined.

## Swarm Guidance

When designing a swarm of A2A agents:
- keep each agent specialized,
- define clear ownership boundaries,
- make outputs machine-readable,
- design for long-running tasks explicitly,
- preserve task IDs and context IDs across delegation,
- assume retries, duplication, and partial failure will happen.

Recommended separation of concerns:
- orchestrator decides delegation,
- worker agents execute specialized work,
- MCP servers expose tools,
- webhook receiver handles async completion,
- client or gateway tracks task correlation.

## Python Implementation Guidance

### Client Side

In Python, a typical client flow is:
1. resolve the Agent Card,
2. construct an A2A client,
3. send a message,
4. capture the returned task ID,
5. poll or register push notifications,
6. inspect artifacts at terminal state.

### Server Side

A typical server implementation needs:
- an Agent Card,
- an executor that runs the business logic,
- a task store,
- an HTTP app wrapper.

If using the official Python SDK, structure server code around an executor abstraction that receives a request context and emits task or artifact events.

## Framework Notes

### Google ADK

Use ADK when you want the smoothest native A2A path. Expose the agent through its A2A wrapper and let ADK generate the A2A surface from agent metadata.

### Agno

Use Agno when you want native A2A support through AgentOS. Ensure the runtime entrypoint actually starts AgentOS with A2A enabled.

### LangChain / LangGraph

Do not assume native open-source A2A server support exists. Wrap the agent using the official A2A Python SDK and implement a thin executor that translates request context into LangChain invocation and returns artifacts.

## Gateway Guidance

If using a gateway in front of multiple A2A agents:
- treat it as a routing and policy layer,
- configure one explicit route per agent,
- do not assume it provides a universal dynamic registry of all A2A agents,
- prefer path-based or host-based routing conventions,
- keep A2A routing distinct from MCP federation.

Important distinction:
- MCP gateways often aggregate many tool servers into one logical endpoint.
- A2A gateways usually route to specific agent backends rather than collapsing all agents into one undifferentiated endpoint.

## Development Workflow

For local development, use a minimal setup:
- one orchestrator agent,
- one or more worker agents,
- one webhook receiver,
- one notebook or script as a lightweight submitter,
- one protocol inspector UI if available.

Recommended dev loop:
1. Validate each worker independently.
2. Inspect Agent Cards.
3. Submit tasks from a notebook or CLI.
4. Watch task transitions.
5. Verify webhook callbacks.
6. Only after this, insert a gateway.

## Debugging Checklist

When A2A is not working, check in this order:
1. Agent Card is reachable and valid.
2. Base URL and route path are correct.
3. Authentication matches Agent Card declarations.
4. Message payload contains valid JSON-RPC envelope.
5. Task is being created and a task ID is returned.
6. State transitions are being emitted correctly.
7. Artifacts contain expected parts.
8. Push notification webhook is reachable.
9. `tasks/get` matches webhook claims.
10. Gateway routing is targeting the intended backend.

## Design Rules

Follow these rules consistently:
- Do not model remote agents as if they were simple tools.
- Do not assume synchronous completion.
- Do not rely on undocumented skill I/O conventions unless you control both sides.
- Prefer structured `DataPart` output when downstream automation exists.
- Keep text readable for humans and data structured for machines.
- Use webhook plus polling reconciliation for long-running tasks.
- Preserve explicit task and context correlation across the system.

## Deliverables This Skill Should Help Produce

This skill is appropriate when creating:
- A2A architecture proposals,
- multi-agent orchestration designs,
- Python A2A server/client implementations,
- protocol debugging notes,
- Agent Card designs,
- payload templates,
- webhook-based async task systems,
- engineering briefs for A2A-enabled backends.
