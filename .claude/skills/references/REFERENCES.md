# LangChain / LangGraph — Reference Links

## Core Documentation

- https://docs.langchain.com/oss/python/langchain/overview — LangChain Python docs home, entry point for concepts, agents, models, messages.
- https://docs.langchain.com/oss/python/langgraph/graph-api — Graph API overview: State, Nodes, Edges, reducers, Command, Send. The core mental model reference.
- https://docs.langchain.com/oss/python/langchain/streaming — LangChain agent streaming guide (stream modes, tokens, custom updates, reasoning).
- https://docs.langchain.com/oss/python/langchain/event-streaming — v1.3 typed event-streaming API (`stream_events`, projections like `.messages`, `.tool_calls`, `.subagents`).
- https://docs.langchain.com/oss/python/langgraph/streaming — LangGraph-level streaming (lower-level than the agent streaming guide).
- https://docs.langchain.com/oss/python/langgraph/persistence — Checkpointers, threads, state persistence.
- https://docs.langchain.com/oss/python/langgraph/interrupts — `interrupt()`, human-in-the-loop, resume semantics.
- https://docs.langchain.com/oss/python/langgraph/use-subgraphs — Subgraphs, namespacing, parent/child state sharing.
- https://docs.langchain.com/oss/python/langgraph/use-graph-api — Practical how-tos: map-reduce/Send, Command, input/output schemas, Overwrite.
- https://docs.langchain.com/oss/python/langgraph/functional-api — `@task`/`@entrypoint` functional API, determinism and idempotency rules.
- https://docs.langchain.com/oss/python/langgraph/fault-tolerance — Retries, graceful shutdown, error handling patterns.
- https://docs.langchain.com/oss/python/langchain/agents — `create_agent` factory reference (the prebuilt ReAct-style agent loop).
- https://docs.langchain.com/oss/python/langchain/messages — Message types, standard content blocks, streaming chunks.
- https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs — Multi-agent handoff patterns using `Command(graph=Command.PARENT)`.
- https://docs.langchain.com/oss/python/deepagents/subagents — Deep agents / subagent architecture, context isolation, `task()` delegation contract.
- https://docs.langchain.com/llms.txt — Auto-generated full documentation index; useful for discovering pages not linked elsewhere.

## API Reference

- https://reference.langchain.com/python/langgraph/graph/state/StateGraph — `StateGraph` class reference.
- https://reference.langchain.com/python/langgraph/graph/message/add_messages — `add_messages` reducer reference.
- https://reference.langchain.com/python/langgraph/types/ — `Command`, `Send`, `CachePolicy`, `Overwrite`, `interrupt` types.
- https://reference.langchain.com/python/langchain-google-vertexai/chat_models/ChatVertexAI — `ChatVertexAI` full API reference (params, deprecation notes, response metadata fields).
- https://reference.langchain.com/python/langgraph/config/get_stream_writer — `get_stream_writer` reference for custom stream events inside nodes/tools.

## Release Notes / Versioning (check these for what's new)

- https://github.com/langchain-ai/langchain/releases — LangChain Python package release notes; check here for v1.2/v1.3+ changelogs.
- https://github.com/langchain-ai/langgraph/releases — LangGraph Python package release notes; primary source for breaking changes between minor versions.
- https://docs.langchain.com/oss/python/releases/langgraph-v1 — LangGraph v1 migration/release guide.
- https://docs.langchain.com/oss/python/releases/langchain-v1 — LangChain v1 migration/release guide.
- https://pypi.org/project/langchain/#history — PyPI version history for `langchain` (quick way to confirm latest published version).
- https://pypi.org/project/langgraph/#history — PyPI version history for `langgraph`.
- https://pypi.org/project/langchain-google-vertexai/#history — PyPI version history for the Vertex AI integration package (tracks independently from core langchain).

## Source Code

- https://github.com/langchain-ai/langchain — Main LangChain monorepo (Python + JS historically split; check `libs/` for current structure).
- https://github.com/langchain-ai/langgraph — Main LangGraph monorepo.
- https://github.com/langchain-ai/langchain-google — Google (Vertex AI / Gemini) integration package source.

## Vertex AI / Google-specific

- https://docs.langchain.com/oss/python/integrations/providers/google — Google provider integration overview (Vertex AI, Gemini direct, embeddings, etc.), useful for comparing `ChatVertexAI` vs `google_genai:` provider paths.
- https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference — Vertex AI model reference for Gemini model IDs, useful when setting `model=` strings in `create_agent`.

## Community / Support

- https://forum.langchain.com — Official LangChain forum for Q&A and troubleshooting.
- https://langchain-ai.github.io/langgraph/ — Older LangGraph docs site (legacy, sometimes still surfaces in search — prefer docs.langchain.com for current info).
