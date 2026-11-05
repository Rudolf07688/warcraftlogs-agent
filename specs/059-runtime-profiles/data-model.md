# Data model: 059

| Instrument | Type | Unit | Attributes (all on METRIC_ATTRIBUTES) | Recorded |
|---|---|---|---|---|
| `app.llm.finish_reasons` | counter | `{response}` | `gen_ai.request.model`, `app.llm.finish_reason` (fixed set, else `other`) | each non-partial model response with a reported reason, any run |
| `app.agent.turns_per_conversation` | histogram | `{turn}` | `gen_ai.agent.name` | end of a chat turn (workspace runs only) |
| `app.embedding.duration` | histogram | `s` | `gen_ai.request.model`, `app.embedding.task` (`document`, `query`) | each provider embedding request |
| `app.embedding.batch_size` | histogram | `{text}` | same | same |

Stored data: ADK session state key `app_turns` (int, session scope), set through the user event's `state_delta` of each chat turn.

Mimir names (OTLP, no suffixes): `app_llm_finish_reasons`, `app_agent_turns_per_conversation`, `app_embedding_duration`, `app_embedding_batch_size`; labels `gen_ai_request_model`, `app_llm_finish_reason`, `gen_ai_agent_name`, `app_embedding_task`.
