"""google-genai deferred-serializer shim (prevents the ADK state_delta crash)."""

from __future__ import annotations

import inspect

from pydantic import BaseModel
from pydantic_core import SchemaSerializer

from wcl_agent.genai_compat import ensure_genai_serializers_built


def test_all_genai_serializers_are_built_after_shim():
    ensure_genai_serializers_built()
    from google.genai import types as gt

    unbuilt = [
        name
        for name, obj in vars(gt).items()
        if inspect.isclass(obj)
        and issubclass(obj, BaseModel)
        and (ser := obj.__dict__.get("__pydantic_serializer__")) is not None
        and not isinstance(ser, SchemaSerializer)
    ]
    assert unbuilt == [], f"genai models still unbuilt: {unbuilt[:10]}"


def test_adk_event_actions_serializes_nested_genai_model():
    # Reproduces the crash path: a genai model nested in EventActions.state_delta being
    # model_dump()'d while merging parallel function-call responses.
    ensure_genai_serializers_built()
    from google.adk.events.event_actions import EventActions
    from google.genai import types as gt

    actions = EventActions(state_delta={"content": gt.Content(parts=[gt.Part(text="hi")])})
    dumped = actions.model_dump(exclude_none=True, by_alias=True)
    assert dumped["stateDelta"]["content"]["parts"][0]["text"] == "hi"


def test_shim_is_idempotent():
    # Second call is a no-op (work already done once per process) and must not raise.
    ensure_genai_serializers_built()
    assert ensure_genai_serializers_built() == 0
