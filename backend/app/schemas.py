"""Pydantic contracts for the WebSocket frames and REST bodies."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from wcl_agent.constants import role_for_spec

# --- WebSocket: client -> server ---------------------------------------------


class ChatTurn(BaseModel):
    conversation_id: uuid.UUID | None = None
    model: str
    content: str = Field(min_length=1)


# --- WebSocket: server -> client frames --------------------------------------


class MetaFrame(BaseModel):
    type: Literal["meta"] = "meta"
    conversation_id: uuid.UUID
    seq: int


class ToolStartFrame(BaseModel):
    type: Literal["tool_start"] = "tool_start"
    name: str


class ToolEndFrame(BaseModel):
    type: Literal["tool_end"] = "tool_end"
    name: str
    ok: bool = True
    # US6: optional telemetry for resolved spell chips. Additive — older clients ignore them.
    summary: str | None = None  # short human-readable result summary (≤140 chars)
    ms: int | None = None  # elapsed duration of the tool call, in milliseconds


class ToolProgressFrame(BaseModel):
    """US6 (optional): upgrade a cast bar from indeterminate to determinate.

    Only emitted by tools that can report progress; clients that ignore it still work.
    """

    type: Literal["tool_progress"] = "tool_progress"
    id: str  # correlates to the tool call
    done: int
    total: int
    note: str | None = None


class TokenFrame(BaseModel):
    type: Literal["token"] = "token"
    text: str


class DoneFrame(BaseModel):
    type: Literal["done"] = "done"
    message_id: uuid.UUID


class ErrorFrame(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


class RaidTrackedFrame(BaseModel):
    """Emitted after a raid is upserted so the UI can refresh its Raids list."""

    type: Literal["raid_tracked"] = "raid_tracked"
    report_code: str
    label: str


class GroundingSource(BaseModel):
    title: str | None = None
    uri: str | None = None


class GroundingFrame(BaseModel):
    """Emitted once per turn when the model used native web grounding (US3/FR-011)."""

    type: Literal["grounding"] = "grounding"
    used: bool = True
    sources: list[GroundingSource] = []


class SuggestionsFrame(BaseModel):
    """Up to 3 predicted follow-up questions, emitted just before `done` (US1).

    Omitted entirely when there are no useful suggestions.
    """

    type: Literal["suggestions"] = "suggestions"
    suggestions: list[str] = Field(default_factory=list, max_length=3)


class EncounterOut(BaseModel):
    """A distinct boss encounter from a report's fight list (US2 display + US4 picker)."""

    encounter_id: int
    name: str
    difficulty: int | None = None
    kill: bool | None = None


class EncountersFrame(BaseModel):
    """Emitted after a successful `get_report_fights` when the report has distinct bosses (US4).

    `encounters` is deduped by `encounter_id`; omitted entirely when empty.
    """

    type: Literal["encounters"] = "encounters"
    report_code: str
    encounters: list[EncounterOut] = []


# --- REST --------------------------------------------------------------------


class ModelsResponse(BaseModel):
    models: list[str]
    default: str
    degraded: bool = False


class ConversationCreate(BaseModel):
    model: str
    title: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    content: str
    seq: int
    status: str = "complete"
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    model: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []
    # US2/FR-011: persisted charts, so reopening a conversation re-renders them.
    artifacts: list["ArtifactOut"] = []


class ConversationListResponse(BaseModel):
    conversations: list[ConversationOut]


# --- Tracked raids (US1) -----------------------------------------------------


class RaidOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    report_code: str
    label: str
    zone: str | None = None
    guild: str | None = None
    report_started_at: datetime | None = None
    last_asked_at: datetime
    first_seen_at: datetime
    # US2: distinct boss(es) for this report, for the sidebar summary. Defaults empty.
    encounters: list[EncounterOut] = []

    @field_validator("encounters", mode="before")
    @classmethod
    def _none_encounters_to_empty(cls, v):
        # The DB column is nullable; rows predating the migration read back as None.
        return v or []


class RaidListResponse(BaseModel):
    raids: list[RaidOut]


class InvestigateRequest(BaseModel):
    model: str | None = None


class InvestigateResponse(BaseModel):
    conversation_id: uuid.UUID
    model: str
    kickoff_prompt: str


class GreetingResponse(BaseModel):
    """Warm Barnaby greeting for a new chat (US5). Empty string on generation failure."""

    greeting: str = ""


# --- Profile (feature 005 / US1) ---------------------------------------------


RaidRole = Literal["tank", "healer", "dps"]


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    server: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=8)
    # US4: optional user override of the raid role; null = unset (inferred from spec).
    # Any value outside the Literal ⇒ 422 with the character unchanged (FR-027).
    raid_role: RaidRole | None = None


class FriendPatchIn(BaseModel):
    """PATCH body for updating a friend's raid role in place (US4 / FR-026, FR-028)."""

    # `null` clears the override, reverting the character to its inferred default.
    raid_role: RaidRole | None = None


class CharacterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    role: str
    name: str
    server: str
    region: str
    class_name: str | None = None
    active_spec: str | None = None
    # US4: the stored user override, plus the computed effective role (override or
    # spec-inferred). The UI treats effective_role set + raid_role null as "inferred".
    raid_role: RaidRole | None = None
    # Feature 008 / US3 (FR-016): guide status is **derived** from the shared spec-guide
    # library (keyed by this character's resolved (class_name, active_spec)), not stored on
    # the character. Defaults to "none" when the spec is unresolved or has no guide row.
    guide_status: str = "none"
    guide_updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_role(self) -> RaidRole | None:
        return self.raid_role or role_for_spec(self.active_spec)

    @classmethod
    def from_character(cls, char: object, guide: object | None = None) -> "CharacterOut":
        """Build from a ``UserCharacter`` with guide status derived from its spec guide.

        ``guide`` is the matching ``SpecGuide`` (or ``None`` ⇒ status "none"). Used by every
        character response so the UI badge reflects the shared library (F1 / FR-016).
        """
        out = cls.model_validate(char)
        if guide is not None:
            out.guide_status = guide.status
            out.guide_updated_at = guide.updated_at
        else:
            out.guide_status = "none"
            out.guide_updated_at = None
        return out


class GuildIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    server: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=8)


class GuildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    server: str
    region: str
    summary_status: str = "none"


class ProfileOut(BaseModel):
    # Field name intentionally "self" (the user's own character); not a method arg here.
    self_character: CharacterOut | None = Field(default=None, serialization_alias="self")
    friends: list[CharacterOut] = []
    guild: GuildOut | None = None

    model_config = ConfigDict(populate_by_name=True)


# --- Spec guides (feature 008 / US2) — the GLOBAL shared library ---------------

# "none" = no row (not downloaded); the others mirror SpecGuide.status.
GuideStatus = Literal["none", "pending", "ready", "failed"]


class GuideListItem(BaseModel):
    class_name: str  # WCL filter value, e.g. "Paladin"
    class_display: str  # display name, e.g. "Death Knight"
    spec: str  # e.g. "Protection"
    status: GuideStatus
    updated_at: datetime | None = None


class GuideListOut(BaseModel):
    guides: list[GuideListItem]  # full roster (every class+spec), status-merged


class GuideOut(BaseModel):
    class_name: str
    spec: str
    status: GuideStatus
    guide_markdown: str | None = None  # present only when status == "ready"
    updated_at: datetime | None = None


class GuideGenerateIn(BaseModel):
    force: bool = False  # true = regenerate/refresh even if already ready


# --- Charts & artifacts (feature 005 / US2) ----------------------------------

CHART_KINDS = {"line", "bar", "scatter", "area"}


class ChartSeries(BaseModel):
    name: str
    y: list[float] = Field(min_length=1)
    x: list[float | int | str] | None = None

    @field_validator("x")
    @classmethod
    def _x_matches_y(cls, v, info):
        y = info.data.get("y")
        if v is not None and y is not None and len(v) != len(y):
            raise ValueError("series 'x' length must match 'y' length")
        return v


class ChartSpec(BaseModel):
    """Single source of truth for both the Plotly (UI) and matplotlib (PDF) renderers."""

    kind: str
    title: str
    x_label: str = ""
    y_label: str = ""
    series: list[ChartSeries] = Field(min_length=1)
    source_url: str = ""

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v):
        if v not in CHART_KINDS:
            raise ValueError(f"kind must be one of {sorted(CHART_KINDS)}")
        return v


class ArtifactOut(BaseModel):
    id: uuid.UUID
    message_seq: int | None = None
    kind: str
    title: str
    figure: dict  # {data, layout} — rebuilt from the stored ChartSpec on read


class ArtifactFrame(BaseModel):
    type: Literal["artifact"] = "artifact"
    artifact_id: uuid.UUID
    kind: str
    title: str
    figure: dict  # Plotly figure JSON: {"data": [...], "layout": {...}}


# --- Auth / tenancy (feature 006) --------------------------------------------
# The error envelope every failure is serialized into (contracts/auth-api.md).

Role = Literal["tenant_admin", "member"]


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class LoginIn(BaseModel):
    # Email is validated loosely (not EmailStr, to avoid the email-validator dep);
    # it is normalized to lowercase server-side.
    email: str = Field(min_length=3, max_length=320)
    # Password carries NO length constraint here on purpose: policy is enforced in the
    # service so 422 validation errors never echo the secret (FR-002).
    password: str


class AcceptInvitationIn(BaseModel):
    token: str = Field(min_length=1)
    password: str
    password_confirmation: str


class ForgotPasswordIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=1)
    password: str
    password_confirmation: str


class TenantRef(BaseModel):
    id: uuid.UUID
    name: str


class MembershipRef(BaseModel):
    tenant_id: uuid.UUID
    name: str
    role: Role


class MeOut(BaseModel):
    user_id: uuid.UUID
    email: str
    is_platform_admin: bool
    active_tenant: TenantRef | None = None
    memberships: list[MembershipRef] = []
    csrf_token: str


class InvitationIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Role = "tenant_admin"


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    status: str  # "open" | "accepted" | "revoked" | "expired"
    expires_at: datetime
    # Returned ONCE on create/resend only, never on list views (admin-api.md).
    invite_link: str | None = None


class InvitationListResponse(BaseModel):
    invitations: list[InvitationOut]


class MembershipIn(BaseModel):
    """Retained for future multi-member workspaces; v1 endpoints are deferred."""

    role: Role = "member"


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    status: str
    last_login_at: datetime | None = None
    memberships: list[MembershipRef] = []


class AdminUserListResponse(BaseModel):
    users: list[AdminUserOut]
    next_cursor: str | None = None


class AdminUserPatchIn(BaseModel):
    status: Literal["active", "disabled"]


class ResetLinkOut(BaseModel):
    reset_link: str


class ActionMessageOut(BaseModel):
    """Generic message envelope for actions with no resource body (e.g. reset-password)."""

    message: str
