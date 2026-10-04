"""WebSocket: streaming chat turns (see contracts/websocket.md).

One turn is processed at a time per socket (the receive loop awaits each turn to
completion), so turns on a single socket are naturally serialized rather than
racing.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from wcl_agent.cache import set_scope_prefix as set_cache_scope

from ..agent_runner import stream_response
from ..auth.csrf import origin_matches
from ..auth.dependencies import authenticate_session
from ..config import settings
from ..db import repository as repo
from ..model_state import is_valid_model
from ..scratch import TurnScratch
from ..tenancy.context import RequestIdentity, apply_tenant_scope, tenant_scope
from ..schemas import (
    ArtifactFrame,
    ChatTurn,
    DoneFrame,
    EncountersFrame,
    ErrorFrame,
    MetaFrame,
    RaidTrackedFrame,
    SuggestionsFrame,
)
from ..suggestions import generate_followups
from ..services import graphs as graphs_service
from ..services import known_entities
from ..services import raids as raids_service
from ..services.artifacts import capture_artifact_from_tool
from ..services.charts import chart_spec_to_plotly
from ..services.encounters import encounters_from_tool
from ..services.profile_context import build_preamble
from ..services.tool_summary import summarize_tool_result

router = APIRouter()


async def _send(ws: WebSocket, frame) -> None:
    payload = frame.model_dump(mode="json") if hasattr(frame, "model_dump") else frame
    await ws.send_json(payload)


async def _forward_tool_start(ws: WebSocket, record: dict) -> None:
    """Forward a user-safe tool_start (name + optional report_code only)."""
    frame: dict = {"type": "tool_start", "name": record["name"]}
    report_code = (record.get("args") or {}).get("report_code")
    if isinstance(report_code, str):
        frame["report_code"] = report_code
    await ws.send_json(frame)


async def _handle_tool_end(
    ws: WebSocket, session, record: dict, conv_id, identity: RequestIdentity
) -> None:
    """Forward a user-safe tool_end and route the full record to capture services."""
    tenant_id = identity.tenant_id
    name = record["name"]
    ok = record.get("ok", False)
    args = record.get("args") or {}
    result = record.get("result") or {}

    # US6: forward a short result summary + elapsed ms so the UI can resolve the
    # spell card to a compact chip. Both optional/additive.
    tool_end: dict = {"type": "tool_end", "name": name, "ok": ok}
    summary = summarize_tool_result(name, ok, result)
    if summary:
        tool_end["summary"] = summary
    ms = record.get("ms")
    if isinstance(ms, int):
        tool_end["ms"] = ms
    await ws.send_json(tool_end)

    # US1: upsert a tracked raid on a successful report retrieval (also merges the
    # distinct boss list from a successful get_report_fights).
    raid = await raids_service.capture_raid_from_tool(
        session,
        tenant_id=tenant_id,
        name=name,
        ok=ok,
        args=args,
        conversation_id=conv_id,
        result=result,
    )
    # US5: capture graph JSON for later PDF rendering.
    graph = await graphs_service.capture_graph_from_tool(
        session,
        tenant_id=tenant_id,
        name=name,
        ok=ok,
        args=args,
        result=result,
        conversation_id=conv_id,
    )
    # US2: capture an agent-declared chart as a persisted artifact + emit a frame.
    spec = capture_artifact_from_tool(name, ok, result)
    artifact = None
    if spec is not None:
        artifact = await repo.add_artifact(
            session,
            tenant_id=tenant_id,
            conversation_id=conv_id,
            kind=spec.kind,
            title=spec.title,
            spec_json=spec.model_dump(),
        )
    # US1 (feature 007): silently capture known players/encounters from successful tool
    # results so later conversations can reuse them. Best-effort — never blocks the turn.
    captured_players = await known_entities.capture_players_from_tool(
        session,
        tenant_id=tenant_id,
        name=name,
        ok=ok,
        args=args,
        result=result,
        conversation_id=conv_id,
    )
    captured_encounters = await known_entities.capture_encounters_from_tool(
        session,
        tenant_id=tenant_id,
        name=name,
        ok=ok,
        args=args,
        result=result,
        conversation_id=conv_id,
    )
    # Commit immediately so a later stream error can't lose what we actually pulled,
    # then re-apply the tenant scope for the rest of the turn (commit drops it).
    if (
        raid is not None
        or graph is not None
        or artifact is not None
        or captured_players
        or captured_encounters
    ):
        await session.commit()
        await apply_tenant_scope(session, identity)
    if raid is not None:
        await _send(ws, RaidTrackedFrame(report_code=raid.report_code, label=raid.label))
    if artifact is not None and spec is not None:
        await _send(
            ws,
            ArtifactFrame(
                artifact_id=artifact.id,
                kind=spec.kind,
                title=spec.title,
                figure=chart_spec_to_plotly(spec),
            ),
        )

    # US4: surface the report's distinct bosses so the UI can render a focus picker.
    encounters = encounters_from_tool(name, ok, result)
    report_code = args.get("report_code")
    if encounters and isinstance(report_code, str):
        await _send(ws, EncountersFrame(report_code=report_code, encounters=encounters))


async def _persist_partial(session, conv_id, tokens: list[str], tenant_id) -> None:
    """Persist whatever streamed so far as a `partial` agent message (US2/FR-009).

    Never presents a partial answer as complete; no silent loss on interruption.
    """
    text = "".join(tokens)
    if not text:
        return
    await repo.add_message(session, conv_id, "agent", text, status="partial", tenant_id=tenant_id)
    await session.commit()


async def _handle_turn(ws: WebSocket, turn: ChatTurn, identity: RequestIdentity) -> None:
    tenant_id = identity.tenant_id
    # Tenant-scoped transaction: app.tenant_id is set so RLS agrees with the app predicate.
    async with tenant_scope(tenant_id, user_id=identity.user_id) as session:
        # Resolve or create the conversation (scoped — a foreign id reads as not-found).
        if turn.conversation_id is not None:
            conv = await repo.get_conversation(session, turn.conversation_id, tenant_id=tenant_id)
            if conv is None:
                await _send(ws, ErrorFrame(code="not_found", message="Conversation not found."))
                return
        else:
            conv = await repo.create_conversation(session, model=turn.model, tenant_id=tenant_id)
        conv_id = conv.id

        # Persist the user message, then announce the turn.
        user_msg = await repo.add_message(
            session, conv_id, "user", turn.content, tenant_id=tenant_id
        )
        await session.commit()
        await apply_tenant_scope(session, identity)  # re-scope after commit
        await _send(ws, MetaFrame(conversation_id=conv_id, seq=user_msg.seq))

        # US1: build the (non-persisted) KNOWN PLAYER CONTEXT preamble from the tenant's
        # profile. Empty string when no profile exists, so behavior is unchanged (FR-006).
        self_char, friends, guild = await repo.get_profile(session, tenant_id=tenant_id)
        # US1 (feature 007): also surface recency-capped captured metadata so follow-ups
        # across the user's conversations reuse known raids/players/encounters/guilds
        # instead of re-querying Warcraft Logs. Empty everywhere ⇒ preamble unchanged.
        known_raids = await repo.list_tracked_raids(session, tenant_id=tenant_id)
        known_players = await repo.list_recent_known_players(session, tenant_id=tenant_id)
        known_encounters = await repo.list_recent_known_encounters(session, tenant_id=tenant_id)
        known_guilds = await repo.list_recent_known_guilds(session, tenant_id=tenant_id)
        # US3 (feature 008): each profile character's guide now lives in the GLOBAL
        # spec_guides library, keyed by its resolved (class, spec). Fetch the ready guides
        # for the profile's specs and pass a (class, spec) → markdown map to the preamble.
        # (spec_guides has no RLS, so reading it on the tenant session is fine.)
        profile_chars = ([self_char] if self_char else []) + list(friends)
        spec_pairs = [
            (c.class_name, c.active_spec)
            for c in profile_chars
            if c.class_name and c.active_spec
        ]
        guide_rows = await repo.get_spec_guides_for(session, spec_pairs)
        spec_guides = {
            key: g.guide_markdown
            for key, g in guide_rows.items()
            if g.status == "ready" and g.guide_markdown
        }
        preamble = build_preamble(
            self_char,
            friends,
            guild,
            known_raids=known_raids[:10],
            known_players=known_players,
            known_encounters=known_encounters,
            known_guilds=known_guilds,
            spec_guides=spec_guides,
        )

        # Scope the WCL result cache to this tenant (FR-019) for the turn's tool calls.
        set_cache_scope(str(tenant_id))

        # Stream the agent response, accumulating tokens into the final content.
        # US2: a per-turn scratch store holds each tool's full output on disk so large
        # concurrent results are preserved and picked up after every call completes.
        tokens: list[str] = []
        scratch = TurnScratch(str(conv_id))
        try:
            async for record in stream_response(
                turn.model,
                str(conv_id),
                turn.content,
                scratch,
                context_preamble=preamble or None,
                # ADK session state is isolated per tenant (feature 006, websocket.md).
                user_id=str(identity.tenant_id),
            ):
                kind = record.get("type")
                if kind == "token":
                    tokens.append(record["text"])
                    await ws.send_json(record)
                elif kind == "tool_start":
                    await _forward_tool_start(ws, record)
                elif kind == "tool_end":
                    await _handle_tool_end(ws, session, record, conv_id, identity)
                elif kind == "grounding":
                    await ws.send_json(record)
        except WebSocketDisconnect:
            # Client vanished mid-reply: keep what we have, can't send anything.
            await _persist_partial(session, conv_id, tokens, tenant_id)
            raise
        except Exception as exc:  # noqa: BLE001 - surface failure to the client
            await _persist_partial(session, conv_id, tokens, tenant_id)
            try:
                await _send(ws, ErrorFrame(code="agent_error", message=str(exc)))
            except Exception:  # noqa: BLE001 - socket may already be gone
                pass
            return
        finally:
            scratch.cleanup()

        final_text = "".join(tokens) or "(no response)"
        agent_msg = await repo.add_message(
            session, conv_id, "agent", final_text, tenant_id=tenant_id
        )
        # US2/US5: link this turn's captures (artifacts + graphs) to the agent message
        # so per-message reports and reload-time rendering can scope them correctly.
        await repo.assign_message_seq_to_turn_captures(
            session, conv_id, agent_msg.seq, tenant_id=tenant_id
        )
        await session.commit()

        # US1: predict up to 3 follow-up questions and emit them just before `done`.
        # Best-effort and non-blocking — never block or fail the turn over suggestions.
        suggestions = await generate_followups(turn.model, turn.content, final_text)
        if suggestions:
            await _send(ws, SuggestionsFrame(suggestions=suggestions))

        await _send(ws, DoneFrame(message_id=agent_msg.id))


@router.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    # Authenticate the handshake BEFORE accept (feature 006, websocket.md): validate the
    # Origin (WS analogue of CSRF) and the __Host-session cookie. No token is ever read
    # from the query string or a frame. Reject with a policy-violation close on failure.
    if not origin_matches(ws.headers.get("origin")):
        await ws.close(code=1008)
        return
    identity = await authenticate_session(ws.cookies.get(settings.session_cookie_name))
    if identity is None or identity.tenant_id is None:
        await ws.close(code=1008)
        return

    await ws.accept()
    try:
        while True:
            raw = await ws.receive_json()
            # Re-validate every turn so a revoked session / disabled user / tenant takes
            # effect mid-connection (FR-023). Cheap: one indexed session lookup.
            identity = await authenticate_session(ws.cookies.get(settings.session_cookie_name))
            if identity is None or identity.tenant_id is None:
                await _send(ws, ErrorFrame(code="unauthorized", message="Session is no longer valid."))
                await ws.close(code=1008)
                return
            try:
                turn = ChatTurn(**raw)
            except ValidationError:
                await _send(ws, ErrorFrame(code="empty_message", message="Invalid or empty message."))
                continue
            if not is_valid_model(ws.app, turn.model):
                await _send(ws, ErrorFrame(code="invalid_model", message=f"Unknown model '{turn.model}'."))
                continue
            await _handle_turn(ws, turn, identity)
    except WebSocketDisconnect:
        return
