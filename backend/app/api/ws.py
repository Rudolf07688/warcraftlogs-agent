"""WebSocket: streaming chat turns (see contracts/websocket.md).

One turn is processed at a time per socket (the receive loop awaits each turn to
completion), so turns on a single socket are naturally serialized rather than
racing. Across sockets, one turn at a time per chat (sc-511, :class:`_ChatTurn`).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from wcl_agent.cache.cache import abandon_turn, set_refresh_actor

from wcl_agent.llm.model_retry import ModelRateLimited
from wcl_agent.llm.models import class_label

from ..agent_runner import stream_response
from ..auth.csrf import origin_matches
from ..auth.dependencies import authenticate_session
from ..config import settings
from ..db import repository as repo
from ..kb import indexer as kb_indexer
from ..kb.chat_chunker import ExchangeJob
from ..repositories import profile_proposals as proposal_rows
from ..model_state import fallback_model_for, resolve_chat_model
from ..scratch import TurnScratch
from ..tenancy.context import RequestIdentity, apply_tenant_scope, current_identity, tenant_scope
from ..schemas import (
    ArtifactFrame,
    ChatTurn,
    ConversationTitleFrame,
    DoneFrame,
    EncountersFrame,
    ErrorFrame,
    MetaFrame,
    ModelFallbackFrame,
    ModelRetryFrame,
    ProposalFrame,
    RaidTrackedFrame,
    SuggestionsFrame,
)
from ..suggestions import generate_followups
from ..telemetry import chat_turn_span
from ..services import conversation_titles
from ..services import graphs as graphs_service
from ..services import known_entities
from ..services import profile_proposals
from ..services import raids as raids_service
from ..services.artifacts import capture_artifact_from_tool
from ..services.charts import chart_spec_to_plotly
from ..services.encounters import encounters_from_tool
from ..services.guide import briefs_for_turn
from ..services.profile_context import build_preamble
from ..services.tool_summary import summarize_tool_result

router = APIRouter()
logger = logging.getLogger(__name__)

# Feature 011 / FR-004: the only wording a player sees for an exhausted retry budget.
RATE_LIMITED_MESSAGE = (
    "The model is rate-limited right now. Please try again in about a minute."
)
# Feature 021: the turn already switched to the same-class sibling, which is busy too, so
# switching models by hand won't help either.
BOTH_RATE_LIMITED_MESSAGE = (
    "Both {label} models are rate-limited right now. Please try again in about a minute."
)
# sc-511 / decision scope:076:two-tabs: a newer turn on the same chat ended this one.
SUPERSEDED_MESSAGE = "This chat continued in another window. The answer so far is saved."
# sc-511: how long a newer turn waits for the one it superseded to save its partial and end.
SUPERSEDE_WAIT_S = 5.0
# QA SEC-001: any other failure. Provider, database and WCL errors can carry internal
# details (project ids, SQL), so the player gets this plus a reference to the log line.
AGENT_ERROR_MESSAGE = (
    "Something went wrong while answering. Please try again. If it keeps happening, "
    "mention reference {ref}."
)


class _TurnSocket:
    """Per-socket state for the receive loop (PERF-102).

    Follow-up suggestions are produced by a background task after ``done``, so they can
    overlap the next turn's sends. ``send_json`` serializes all sends on the socket, and the
    pending suggestions task is cancelled when the next turn starts.
    """

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self._lock = asyncio.Lock()
        self.suggestions: asyncio.Task | None = None

    async def send_json(self, payload) -> None:
        async with self._lock:
            await self.ws.send_json(payload)

    def cancel_suggestions(self) -> None:
        if self.suggestions is not None and not self.suggestions.done():
            self.suggestions.cancel()
        self.suggestions = None


class _ChatTurn:
    """sc-511: the turn in flight on one chat, across all sockets.

    A dropped socket is noticed only when a send fails, so its turn can still be in a tool
    round when the player asks again on a new socket. The newer turn supersedes it: it cancels
    the old turn while that one is in setup or streaming (its save is short and is awaited),
    then waits at most :data:`SUPERSEDE_WAIT_S` for it to end. The old turn saves its partial
    first, so a chat's messages stay in turn order and each turn's charts stay with its answer.
    Past the wait the newer turn goes on, and the old one, no longer holding the chat, saves no
    partial when it ends.

    The key is (tenant, conversation) from the row the ownership check returned, never the id
    in the frame, so another workspace can't touch a chat's turn.
    """

    turns: dict[tuple[uuid.UUID, uuid.UUID], _ChatTurn] = {}

    def __init__(self) -> None:
        self.key: tuple[uuid.UUID, uuid.UUID] | None = None
        self.task = asyncio.current_task()
        self.cancellable = True
        self.superseded = False

    async def claim(self, tenant_id: uuid.UUID, conv_id: uuid.UUID) -> None:
        """Become the chat's turn; call only after the chat's ownership is verified."""
        key = (tenant_id, conv_id)
        while (old := self.turns.get(key)) is not None:
            old.superseded = True
            if old.cancellable:
                old.task.cancel()
            await asyncio.wait({old.task}, timeout=SUPERSEDE_WAIT_S)
            if self.turns.get(key) is old:
                logger.warning("superseded turn still running after %ss", SUPERSEDE_WAIT_S)
                break
        self.key = key
        self.turns[key] = self

    def holds_chat(self) -> bool:
        return self.key is not None and self.turns.get(self.key) is self

    def release(self) -> None:
        if self.holds_chat():
            del self.turns[self.key]


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
    ws: WebSocket, record: dict, conv_id, identity: RequestIdentity
) -> uuid.UUID | None:
    """Forward a user-safe tool_end and route the full record to capture services.

    Captures run in their own short tenant-scoped transaction (PERF-006): no DB connection
    is held while the model streams. Returns the id of a proposal sent as a frame (031), so
    the turn can link it to its answer at ``done``.
    """
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

    # Every capture is a no-op for a failed call, so only open a transaction on success.
    # The transaction commits on exit, so a later stream error can't lose what we pulled.
    raid = artifact = spec = proposal = None
    raid_is_new = False
    if ok:
        async with tenant_scope(tenant_id, user_id=identity.user_id) as session:
            # US1: upsert a tracked raid on a successful report retrieval (also merges the
            # distinct boss list from a successful get_report_fights).
            raid, raid_is_new = await raids_service.capture_raid(
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
            if name == "propose_profile_changes":
                proposal = await _stored_proposal(session, result, identity)
    # Announce only newly tracked raids (PERF-013); re-references refresh on `done`.
    if raid is not None and raid_is_new:
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

    if proposal is not None:
        await _send(ws, ProposalFrame(proposal=proposal))
        return proposal.id
    return None


async def _stored_proposal(session, result: dict, identity: RequestIdentity):
    """Feature 031: the stored proposal (not the tool result the model saw) for the
    confirmation card, read in the capture's transaction (sc-225) and scoped to this user, so
    an id from another tenant gives ``None`` and no frame."""
    try:
        proposal_id = uuid.UUID(str((result.get("proposal") or {})["id"]))
        return await profile_proposals.get_proposal(identity, proposal_id, db=session)
    except (KeyError, TypeError, ValueError, profile_proposals.ProposalError) as exc:
        logger.warning("proposal frame skipped: %r", exc)
        return None


async def _persist_partial(
    conv_id, tokens: list[str], identity: RequestIdentity, user_seq: int
) -> None:
    """Persist whatever streamed so far as a `partial` agent message (US2/FR-009).

    Never presents a partial answer as complete; no silent loss on interruption. The turn's
    charts are linked to that message, so they come back under it on reload. With nothing
    streamed there is no message to show them under, so they anchor to the turn's user
    message (``user_seq``): they stay out of later answers, and were never shown live either
    (the chat shows a turn's charts only when its answer completes).
    """
    text = "".join(tokens)
    async with tenant_scope(identity.tenant_id, user_id=identity.user_id) as session:
        seq = user_seq
        if text:
            msg = await repo.add_message(
                session, conv_id, "agent", text, status="partial", tenant_id=identity.tenant_id
            )
            seq = msg.seq
        # Every way a turn ends links its charts and graphs (sc-213, SPEC-002): the repo call
        # takes all of a chat's unlinked ones, so one left behind would show up under a later
        # answer.
        await repo.assign_message_seq_to_turn_captures(
            session, conv_id, seq, tenant_id=identity.tenant_id
        )


async def _handle_turn(
    ws: WebSocket,
    turn: ChatTurn,
    identity: RequestIdentity,
    *,
    fallback_model: str | None = None,
) -> asyncio.Task | None:
    """Run one chat turn, holding its chat from the ownership check to the end (sc-511)."""
    chat_turn = _ChatTurn()
    try:
        return await _run_chat_turn(ws, turn, identity, chat_turn, fallback_model=fallback_model)
    except asyncio.CancelledError:
        if chat_turn.superseded:  # tell this socket, if it is still there (scope:076:two-tabs)
            try:
                await _send(ws, ErrorFrame(code="superseded", message=SUPERSEDED_MESSAGE))
            except Exception:  # noqa: BLE001 - socket may already be gone
                pass
        raise
    finally:
        chat_turn.release()


async def _run_chat_turn(
    ws: WebSocket,
    turn: ChatTurn,
    identity: RequestIdentity,
    chat_turn: _ChatTurn,
    *,
    fallback_model: str | None = None,
) -> asyncio.Task | None:
    """Run one chat turn. Returns the follow-up suggestions task when the turn finished with
    an answer, else ``None``; the caller owns it (and cancels it when the next turn starts).

    ``fallback_model`` is the same-class sibling the turn may switch to once when its
    model stays rate limited (feature 021).
    """
    tenant_id = identity.tenant_id
    # PERF-006: one short tenant-scoped transaction to set the turn up. It closes (commits
    # and returns its connection to the pool) before the model streams; captures and the
    # final save open their own short transactions.
    try:
        async with tenant_scope(tenant_id, user_id=identity.user_id) as session:
            # Resolve or create the conversation (scoped — a foreign id reads as not-found).
            if turn.conversation_id is not None:
                conv = await repo.get_conversation_row(
                    session, turn.conversation_id, tenant_id=tenant_id
                )
                if conv is None:
                    await _send(ws, ErrorFrame(code="not_found", message="Conversation not found."))
                    return None
            else:
                conv = await repo.create_conversation(
                    session, model=turn.model, tenant_id=tenant_id
                )
            conv_id = conv.id
            # sc-511: wait for (and cut short) a turn still running on this chat before this
            # turn writes anything.
            await chat_turn.claim(tenant_id, conv_id)
            # Feature 019 / sc-155: only a default-named chat gets a generated title.
            title_eligible = conv.title_source == "auto"

            # Persist the user message, then announce the turn.
            user_msg = await repo.add_message(
                session, conv_id, "user", turn.content, tenant_id=tenant_id
            )
            await session.commit()
            await apply_tenant_scope(session, identity)  # re-scope after commit
            user_seq = user_msg.seq
            await _send(ws, MetaFrame(conversation_id=conv_id, seq=user_seq))

            # WCL data is public and cached for every tenant alike (feature 014 supersedes
            # FR-019); only the forced-refresh limit is per user, for this turn (US4). The turn
            # opens before its preamble, so WCL calls made building it count for it (047 sc-326).
            # Cleared with the identity (sc-276), so the follow-up suggestions task never acts as
            # this turn's user.
            set_refresh_actor(str(identity.user_id))
            preamble = await _build_turn_preamble(session, tenant_id, turn.content)
        # US2: a per-turn scratch store holds each tool's full output on disk so large
        # concurrent results are preserved and picked up after every call completes. Last in
        # the setup: nothing between it and the stream's ``finally`` (which removes it) can fail.
        scratch = TurnScratch(str(conv_id))
    except BaseException:
        # 052 sc-357: setup failed or was cancelled (the preamble, this transaction's commit or
        # the scratch folder) after the turn may have opened: close it uncounted, clear its user.
        abandon_turn()
        raise

    # Stream the agent response, accumulating tokens into the final content.
    tokens: list[str] = []
    empty = False  # 048: the turn ended with the runner's no-answer message, not model text
    proposal_ids: list[uuid.UUID] = []  # feature 031: proposals sent this turn
    switched = False  # feature 021: the turn moved to the sibling model
    # Backend agent tools act as this user (029, C7), for this turn only (sc-222): the token
    # is reset when the stream ends, so later tasks on this socket never see the identity.
    identity_token = current_identity.set(identity)
    try:
        try:
            async for record in stream_response(
                turn.model,
                str(conv_id),
                turn.content,
                scratch,
                context_preamble=preamble or None,
                # ADK session state is isolated per tenant (feature 006, websocket.md).
                user_id=str(identity.tenant_id),
                fallback_model=fallback_model,
            ):
                kind = record.get("type")
                if kind == "token":
                    empty = record.pop("empty", False) or empty
                    tokens.append(record["text"])
                    await ws.send_json(record)
                elif kind == "tool_start":
                    await _forward_tool_start(ws, record)
                elif kind == "tool_end":
                    proposal_id = await _handle_tool_end(ws, record, conv_id, identity)
                    if proposal_id is not None:
                        proposal_ids.append(proposal_id)
                elif kind == "grounding":
                    await ws.send_json(record)
                elif kind == "model_retry":
                    # Feature 011 / FR-003: the model is rate-limited; show "retrying".
                    await _send(ws, ModelRetryFrame(**record))
                elif kind == "model_fallback":
                    # Feature 021: the turn moved to the same-class sibling; show which.
                    switched = True
                    await _send(ws, ModelFallbackFrame(**record))
        finally:
            chat_turn.cancellable = False  # from here the turn only saves: a newer one waits
    except asyncio.CancelledError:
        # sc-511: a newer turn on this chat superseded this one (a drop not noticed yet, or a
        # second tab). Its partial goes right after its own question, before the newer one's.
        if chat_turn.superseded and chat_turn.holds_chat():
            await _persist_partial(conv_id, tokens, identity, user_seq)
        raise
    except WebSocketDisconnect:
        # Client vanished mid-reply: keep what we have, can't send anything.
        await _persist_partial(conv_id, tokens, identity, user_seq)
        raise
    except ModelRateLimited as exc:
        # Feature 011 / FR-004, FR-005: the retry budget is spent. Plain-language error,
        # no provider wording, and no partial reply persisted (the user message stays,
        # so the player can simply resend). Charts made before it ran out anchor to that
        # user message (sc-213).
        logger.warning("turn failed on model rate limit: %s", exc)
        async with tenant_scope(tenant_id, user_id=identity.user_id) as session:
            await repo.assign_message_seq_to_turn_captures(
                session, conv_id, user_seq, tenant_id=tenant_id
            )
        label = class_label(turn.model) if switched else None
        message = BOTH_RATE_LIMITED_MESSAGE.format(label=label) if label else RATE_LIMITED_MESSAGE
        try:
            await _send(ws, ErrorFrame(code="rate_limited", message=message))
        except Exception:  # noqa: BLE001 - socket may already be gone
            pass
        return None
    except Exception:  # noqa: BLE001 - surface failure to the client
        ref = uuid.uuid4().hex[:8]
        logger.exception("turn failed (ref %s)", ref)
        await _persist_partial(conv_id, tokens, identity, user_seq)
        await _send_agent_error(ws, ref)
        return None
    finally:
        current_identity.reset(identity_token)
        set_refresh_actor(None)
        scratch.cleanup()

    final_text = "".join(tokens) or "(no response)"
    try:
        agent_msg_id, agent_seq = await _save_answer(identity, conv_id, final_text, proposal_ids)
    except Exception:  # noqa: BLE001 - a card lock or the DB: the turn still ends (052 sc-357)
        ref = uuid.uuid4().hex[:8]
        logger.exception("turn failed: answer not saved (ref %s)", ref)
        try:  # keep what streamed and link the turn's captures here, not to a later answer
            await _persist_partial(conv_id, tokens, identity, user_seq)
        except Exception:  # noqa: BLE001 - the store is likely what failed
            logger.warning("partial answer not saved either (ref %s)", ref)
        await _send_agent_error(ws, ref)
        return None

    # Feature 043: the saved exchange becomes a workspace chat chunk in the background (enqueue
    # only). Only the streamed answer goes in: tool results never reach ``tokens``. A no-answer
    # turn (048) is saved for the user but never indexed, titled or given follow-ups.
    if tokens and not empty:
        kb_indexer.offer_exchange(
            ExchangeJob(tenant_id, conv_id, agent_seq, turn.content, final_text, datetime.now(UTC))
        )

    # PERF-005: the turn is done as soon as the answer is saved; the composer unlocks now.
    await _send(ws, DoneFrame(message_id=agent_msg_id))

    # Feature 019 / sc-155: name the chat from this first complete exchange, in the
    # background; the next turn doesn't cancel it, and the frame shares the socket lock.
    if title_eligible and not empty:

        async def notify_title(title: str) -> None:
            await _send(ws, ConversationTitleFrame(conversation_id=conv_id, title=title))

        conversation_titles.schedule_title(
            conv_id, identity, turn.content, final_text, notify_title
        )

    # US1: predict up to 3 follow-up questions in the background (PERF-102), so the socket
    # can read the player's next message straight away; that next turn cancels this task.
    if empty:
        return None
    return asyncio.create_task(_send_suggestions(ws, turn, final_text, agent_msg_id))


async def _send_agent_error(ws: WebSocket, ref: str) -> None:
    """Tell the client its turn failed (with the log reference), if the socket is still there."""
    try:
        await _send(ws, ErrorFrame(code="agent_error", message=AGENT_ERROR_MESSAGE.format(ref=ref)))
    except Exception:  # noqa: BLE001 - socket may already be gone
        pass


async def _send_suggestions(ws, turn: ChatTurn, final_text: str, message_id) -> None:
    """Best-effort and time-boxed: never fail anything over suggestions."""
    try:
        suggestions = await generate_followups(turn.model, turn.content, final_text)
        if suggestions:
            await _send(ws, SuggestionsFrame(message_id=message_id, suggestions=suggestions))
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - e.g. the socket closed meanwhile
        logger.debug("follow-up suggestions not sent", exc_info=True)


async def _start_turn(
    sock: _TurnSocket,
    turn: ChatTurn,
    identity: RequestIdentity,
    *,
    fallback_model: str | None = None,
) -> None:
    """Start a turn on this socket: drop the previous turn's pending suggestions first.

    The turn runs as its own task, so a newer turn on the same chat can cancel it (sc-511)
    without closing this socket.
    """
    sock.cancel_suggestions()
    task = asyncio.create_task(_handle_turn(sock, turn, identity, fallback_model=fallback_model))
    try:
        sock.suggestions = await task
    except asyncio.CancelledError:
        if asyncio.current_task().cancelling():
            raise  # this socket is closing
        sock.suggestions = None  # superseded by a newer turn on the same chat


async def _save_answer(
    identity: RequestIdentity, conv_id: uuid.UUID, final_text: str, proposal_ids: list[uuid.UUID]
) -> tuple[uuid.UUID, int]:
    """Save the turn's answer and link its captures and cards to it; returns (id, seq)."""
    tenant_id = identity.tenant_id
    async with tenant_scope(tenant_id, user_id=identity.user_id) as session:
        # Lock this turn's cards before add_message locks the conversation: the order a card
        # decision takes them (approve/cancel lock the card, then save their line), so a click
        # during this save waits instead of deadlocking (047 P7 SEC-005).
        for proposal_id in sorted(proposal_ids):
            await proposal_rows.get_proposal_row(
                session, proposal_id, tenant_id=tenant_id, user_id=identity.user_id, for_update=True
            )
        agent_msg = await repo.add_message(
            session, conv_id, "agent", final_text, tenant_id=tenant_id
        )
        # US2/US5: link this turn's captures (artifacts + graphs) to the agent message
        # so per-message reports and reload-time rendering can scope them correctly.
        await repo.assign_message_seq_to_turn_captures(
            session, conv_id, agent_msg.seq, tenant_id=tenant_id
        )
        # Feature 031: this turn's confirmation cards belong under this answer too.
        await proposal_rows.set_message_seq(
            session, proposal_ids, agent_msg.seq, tenant_id=tenant_id, user_id=identity.user_id
        )
        return agent_msg.id, agent_msg.seq


async def _build_turn_preamble(session, tenant_id, user_text: str = "") -> str:
    """The (non-persisted) KNOWN PLAYER CONTEXT preamble for this turn (US1).

    Empty string when no profile exists, so behavior is unchanged (FR-006).
    """
    own, friends, guild = await repo.get_profile(session, tenant_id=tenant_id)
    # US1 (feature 007): also surface recency-capped captured metadata so follow-ups
    # across the user's conversations reuse known raids/players/encounters/guilds
    # instead of re-querying Warcraft Logs. Empty everywhere ⇒ preamble unchanged.
    known_raids = await repo.list_tracked_raids(session, tenant_id=tenant_id, limit=10)
    known_players = await repo.list_recent_known_players(session, tenant_id=tenant_id)
    known_encounters = await repo.list_recent_known_encounters(session, tenant_id=tenant_id)
    known_guilds = await repo.list_recent_known_guilds(session, tenant_id=tenant_id)
    # Feature 030 (D5): candidates for "the dungeon / the raid", from rows already stored.
    recent_raids = await repo.list_recent_raids(session, tenant_id=tenant_id, limit=5)
    recent_mplus = await repo.list_recent_mplus_runs(session, tenant_id=tenant_id, limit=5)
    # Feature 015 / US2: whole coaching briefs of the content type this turn is about,
    # for each profile character's resolved spec (published briefs only, never drafts).
    profile_chars = list(own) + list(friends)
    specs = [(c.class_name, c.active_spec) for c in profile_chars if c.class_name and c.active_spec]
    turn = None
    if specs:
        recent_zone = next((r.zone for r in known_raids if r.zone), None)
        try:
            turn = await briefs_for_turn(specs, user_text, recent_zone)
        except Exception:  # noqa: BLE001 - QA BUG-001: a turn without briefs, never a dead socket
            logger.exception("coaching briefs unavailable for this turn")
    return build_preamble(
        own,
        friends,
        guild,
        known_raids=known_raids,
        known_players=known_players,
        known_encounters=known_encounters,
        known_guilds=known_guilds,
        recent_raids=[raid for raid, _ in recent_raids],
        recent_mplus_runs=[run for run, _ in recent_mplus],
        briefs=turn.briefs if turn else {},
        available=turn.available if turn else {},
        content_type=turn.content_type if turn else "raid",
        content_type_note=turn.note if turn else None,
    )


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
    sock = _TurnSocket(ws)
    try:
        while True:
            raw = await ws.receive_json()
            # Re-validate every turn so a revoked session / disabled user / tenant takes
            # effect mid-connection (FR-023). Cheap: one indexed session lookup.
            identity = await authenticate_session(ws.cookies.get(settings.session_cookie_name))
            if identity is None or identity.tenant_id is None:
                await _send(sock, ErrorFrame(code="unauthorized", message="Session is no longer valid."))
                await ws.close(code=1008)
                return
            try:
                turn = ChatTurn(**raw)
            except ValidationError:
                await _send(sock, ErrorFrame(code="empty_message", message="Invalid or empty message."))
                continue
            # Feature 032 (D4): an unserved model (say, after a provider switch) continues on
            # the default instead of failing the turn.
            turn = turn.model_copy(update={"model": resolve_chat_model(ws.app, turn.model)})
            # 054: each turn is the root of its own trace; 057: or the browser's span's child
            with chat_turn_span(raw.get("traceparent"), raw.get("faro_session_id")):
                await _start_turn(
                    sock, turn, identity, fallback_model=fallback_model_for(ws.app, turn.model)
                )
    except WebSocketDisconnect:
        return
    finally:
        sock.cancel_suggestions()
